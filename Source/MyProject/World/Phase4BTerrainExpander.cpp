// Copyright Epic Games, Inc. All Rights Reserved.
#include "World/Phase4BTerrainExpander.h"

#include "Engine/Engine.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "HAL/FileManager.h"
#include "Landscape.h"
#include "LandscapeComponent.h"
#include "LandscapeDataAccess.h"
#include "LandscapeEdit.h"
#include "LandscapeEditLayer.h"
#include "LandscapeInfo.h"
#include "LandscapeStreamingProxy.h"
#include "LandscapeSubsystem.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"

namespace Phase4BTerrainExpansion
{
	/** The landscape actor the project builds on (Phase 4A label). */
	static const TCHAR* const LandscapeLabel = TEXT("Landscape");

	/** The reference world size of the Phase 4B master pass (metres). */
	static constexpr int32 TargetWorldSizeM = 4032;

	/** Width of the band where the new area blends into the original block (metres). */
	static constexpr float BlendBandM = 420.f;

	/** Heightmap helpers: raw 16 bit value <-> world metres. */
	static float RawToMeters(uint16 Raw, float ZScale)
	{
		return ((static_cast<float>(Raw) - 32768.f) * ZScale) / (100.f * 128.f);
	}

	static uint16 MetersToRaw(float HeightM, float ZScale)
	{
		const float Pixels = 32768.f + (HeightM * 100.f * 128.f) / FMath::Max(0.01f, ZScale);
		return static_cast<uint16>(FMath::Clamp(FMath::RoundToInt(Pixels), 0, 65535));
	}

	/** Smooth 1 -> 0 falloff (1 inside Inner, 0 beyond Outer). */
	static float Falloff(float Distance, float Inner, float Outer)
	{
		if (Outer <= Inner)
		{
			return Distance <= Inner ? 1.f : 0.f;
		}
		return 1.f - FMath::SmoothStep(Inner, Outer, Distance);
	}

	/** Fractal value in about [-1, 1] built from Perlin noise. */
	static float Fbm(const FVector2D& Position, int32 Octaves, float Lacunarity = 2.f, float Gain = 0.5f)
	{
		float Sum = 0.f;
		float Amplitude = 1.f;
		float Frequency = 1.f;
		float Normalizer = 0.f;
		for (int32 Index = 0; Index < Octaves; ++Index)
		{
			Sum += Amplitude * FMath::PerlinNoise2D(Position * Frequency);
			Normalizer += Amplitude;
			Amplitude *= Gain;
			Frequency *= Lacunarity;
		}
		return Normalizer > 0.f ? Sum / Normalizer : 0.f;
	}

	/** Ridged noise in [0, 1] used for the mountain ridgelines. */
	static float Ridged(const FVector2D& Position, int32 Octaves)
	{
		return 1.f - FMath::Abs(Fbm(Position, Octaves));
	}

	/**
	 * Relief for the world outside the original block: a mature mixed mountain forest
	 * landscape. The home shoulder stays high, the land runs down to the south-west and
	 * climbs into a mountain range towards the north-east, with rolling hills, ridgelines
	 * and shallow drainage draws in between.
	 */
	static float OuterHeightM(const FVector2D& WorldM)
	{
		const FVector2D Home(750.f, 750.f);
		const FVector2D WorldCentre(630.f, 630.f);
		const FVector2D Offset = WorldM - WorldCentre;
		const float DistHome = FVector2D::Distance(WorldM, Home);

		const float NorthEast = FVector2D::DotProduct(Offset, FVector2D(0.7071f, 0.7071f));
		const float SouthWest = FVector2D::DotProduct(Offset, FVector2D(-0.7071f, -0.7071f));

		// A mature forest basin that always stays well above the river plain, the home
		// shoulder, and a mountain range that climbs towards the north-east.
		float Height = 58.f;
		Height += 96.f * Falloff(DistHome, 300.f, 2300.f);
		Height += 62.f * FMath::SmoothStep(0.f, 1600.f, NorthEast);
		Height -= 26.f * FMath::SmoothStep(200.f, 2200.f, SouthWest);

		// Mountain ridgelines, strongest in the far north-east.
		const float RangeMask = FMath::SmoothStep(400.f, 2500.f, NorthEast);
		const float Ridge = Ridged(WorldM * (1.f / 1250.f) + FVector2D(41.f, -77.f), 4);
		Height += 150.f * Ridge * RangeMask;

		// Rolling hills / minor ridges everywhere, strong enough that no flat basin
		// appears anywhere near the world edge.
		Height += Fbm(WorldM * (1.f / 780.f) + FVector2D(37.5f, -12.5f), 4) * (24.f + 26.f * Ridge);
		Height += Fbm(WorldM * (1.f / 275.f) + FVector2D(-11.f, 23.f), 3) * (7.f + 6.f * Ridge);

		// Shallow meandering drainage draws.
		const float Draw = FMath::Max(0.f, Fbm(WorldM * (1.f / 540.f) + FVector2D(-73.f, 51.f), 3));
		Height -= Draw * (6.f + 16.f * Ridge);

		return FMath::Clamp(Height, 8.f, 360.f);
	}
}

#if WITH_EDITOR
namespace Phase4BTerrainExpansion
{
	/** Finds the project landscape plus every proxy that belongs to it. */
	static ALandscape* FindLandscape(UWorld* World, ULandscapeInfo*& OutInfo, TArray<ALandscapeProxy*>& OutProxies)
	{
		ALandscape* Landscape = nullptr;
		for (TActorIterator<ALandscape> It(World); It; ++It)
		{
			ALandscape* Candidate = *It;
			if (IsValid(Candidate) && Candidate->GetActorLabel() == LandscapeLabel)
			{
				Landscape = Candidate;
				break;
			}
		}
		if (Landscape == nullptr)
		{
			for (TActorIterator<ALandscape> It(World); It; ++It)
			{
				Landscape = *It;
				break;
			}
		}
		if (Landscape == nullptr)
		{
			return nullptr;
		}

		OutInfo = Landscape->GetLandscapeInfo();
		if (OutInfo == nullptr)
		{
			return nullptr;
		}

		OutProxies.Reset();
		for (TActorIterator<ALandscapeProxy> It(World); It; ++It)
		{
			ALandscapeProxy* Proxy = *It;
			if (IsValid(Proxy) && (Proxy == Landscape || Proxy->GetLandscapeActor() == Landscape))
			{
				OutProxies.Add(Proxy);
			}
		}
		return Landscape;
	}

	/** Reads the merged (edit layer aware) heightfield of a vertex rect. */
	static bool ReadHeightmapRegion(ULandscapeInfo* Info, int32 X1, int32 Y1, int32 X2, int32 Y2, TArray<uint16>& OutHeights)
	{
		if (X2 < X1 || Y2 < Y1)
		{
			return false;
		}
		OutHeights.SetNumUninitialized((X2 - X1 + 1) * (Y2 - Y1 + 1));
		FLandscapeEditDataInterface Edit(Info);
		int32 MinX = X1;
		int32 MinY = Y1;
		int32 MaxX = X2;
		int32 MaxY = Y2;
		Edit.GetHeightData(MinX, MinY, MaxX, MaxY, OutHeights.GetData(), /*Stride = */0);
		return true;
	}

	/** Loads a raw uint16 heightfield backup written by SaveBackup(). */
	static bool LoadHeightmapFile(const FString& Path, TArray<uint16>& OutHeights)
	{
		TArray<uint8> Blob;
		if (!FFileHelper::LoadFileToArray(Blob, *Path) || Blob.Num() == 0 || (Blob.Num() % 2) != 0)
		{
			return false;
		}
		OutHeights.SetNumUninitialized(Blob.Num() / 2);
		FMemory::Memcpy(OutHeights.GetData(), Blob.GetData(), static_cast<SIZE_T>(Blob.Num()));
		return true;
	}

	/** Saves the raw uint16 grid plus a small metadata sidecar. */
	static bool SaveBackup(const FString& Path, const TArray<uint16>& Heights, int32 MinX, int32 MinY, int32 MaxX,
	                       int32 MaxY, float ZScale, int32 ComponentSizeQuads, int32 NumSubsections,
	                       int32 SubsectionSizeQuads, int32& OutBytes)
	{
		OutBytes = 0;
		if (Path.IsEmpty())
		{
			return false;
		}
		FString Directory = FPaths::GetPath(Path);
		if (!Directory.IsEmpty())
		{
			IFileManager::Get().MakeDirectory(*Directory, /*Tree = */true);
		}

		const uint8* Raw = reinterpret_cast<const uint8*>(Heights.GetData());
		const int64 NumBytes = static_cast<int64>(Heights.Num()) * sizeof(uint16);
		TArray<uint8> Blob(Raw, static_cast<int32>(NumBytes));
		const bool bSaved = FFileHelper::SaveArrayToFile(Blob, *Path);
		OutBytes = bSaved ? static_cast<int32>(NumBytes) : 0;

		const FString Meta =
			FString::Printf(TEXT("min_x=%d\nmin_y=%d\nmax_x=%d\nmax_y=%d\nsize_x=%d\nsize_y=%d\n"
			                     "component_size_quads=%d\nnum_subsections=%d\nsubsection_size_quads=%d\n"
			                     "z_scale=%.4f\nuint16_values=%d\n"),
			                MinX, MinY, MaxX, MaxY, MaxX - MinX + 1, MaxY - MinY + 1, ComponentSizeQuads,
			                NumSubsections, SubsectionSizeQuads, ZScale, Heights.Num());
		FFileHelper::SaveStringToFile(Meta, *(Path + TEXT(".txt")));
		return bSaved;
	}

	/**
	 * Reads the extent that must keep its exact heights from the backup sidecar written by
	 * SaveBackup(). Taking it from the file (instead of the current landscape extent) makes
	 * ExpandWorldTo4032() re-runnable: a second pass regenerates only the outer relief.
	 */
	static bool LoadPreservedExtent(const FString& MetaPath, int32& OutMinX, int32& OutMinY, int32& OutMaxX,
	                                int32& OutMaxY)
	{
		FString Text;
		if (!FFileHelper::LoadFileToString(Text, *MetaPath))
		{
			return false;
		}

		TMap<FString, int32> Values;
		TArray<FString> Lines;
		Text.ParseIntoArrayLines(Lines);
		for (const FString& Line : Lines)
		{
			FString Key;
			FString Value;
			if (Line.Split(TEXT("="), &Key, &Value))
			{
				Values.Add(Key.TrimStartAndEnd(), FCString::Atoi(*Value.TrimStartAndEnd()));
			}
		}

		const int32* MinX = Values.Find(TEXT("min_x"));
		const int32* MinY = Values.Find(TEXT("min_y"));
		const int32* MaxX = Values.Find(TEXT("max_x"));
		const int32* MaxY = Values.Find(TEXT("max_y"));
		if (MinX == nullptr || MinY == nullptr || MaxX == nullptr || MaxY == nullptr)
		{
			return false;
		}

		OutMinX = *MinX;
		OutMinY = *MinY;
		OutMaxX = *MaxX;
		OutMaxY = *MaxY;
		return true;
	}

	/** Reads a single height sample (metres) using the merged heightfield. */
	static bool SampleHeightM(ULandscapeInfo* Info, const FVector2D& Vertex, float ZScale, float& OutHeightM)
	{
		FLandscapeEditDataInterface Edit(Info);
		uint16 Value = 0;
		int32 X1 = FMath::RoundToInt(Vertex.X);
		int32 Y1 = FMath::RoundToInt(Vertex.Y);
		int32 X2 = X1;
		int32 Y2 = Y1;
		Edit.GetHeightData(X1, Y1, X2, Y2, &Value, /*Stride = */0);
		if (X2 < X1 || Y2 < Y1)
		{
			return false;
		}
		OutHeightM = RawToMeters(Value, ZScale);
		return true;
	}
}
#endif

FPhase4BTerrainExpansionResult UPhase4BTerrainExpander::BackupLandscapeRegion(UObject* WorldContextObject,
                                                                              FIntPoint MinVertex, FIntPoint MaxVertex,
                                                                              const FString& BackupPath)
{
	FPhase4BTerrainExpansionResult Result;

#if WITH_EDITOR
	using namespace Phase4BTerrainExpansion;

	UWorld* World = GEngine ? GEngine->GetWorldFromContextObject(WorldContextObject, EGetWorldErrorMode::LogAndReturnNull) : nullptr;
	if (World == nullptr)
	{
		Result.Message = TEXT("no valid editor world");
		return Result;
	}

	ULandscapeInfo* Info = nullptr;
	TArray<ALandscapeProxy*> Proxies;
	ALandscape* Landscape = FindLandscape(World, Info, Proxies);
	if (Landscape == nullptr || Info == nullptr)
	{
		Result.Message = TEXT("no ALandscape / ULandscapeInfo in the level");
		return Result;
	}

	int32 MinX = FMath::Min(MinVertex.X, MaxVertex.X);
	int32 MinY = FMath::Min(MinVertex.Y, MaxVertex.Y);
	int32 MaxX = FMath::Max(MinVertex.X, MaxVertex.X);
	int32 MaxY = FMath::Max(MinVertex.Y, MaxVertex.Y);
	TArray<uint16> Heights;
	if (!ReadHeightmapRegion(Info, MinX, MinY, MaxX, MaxY, Heights))
	{
		Result.Message = TEXT("could not read the requested landscape region");
		return Result;
	}
	if (Heights.Num() != (MaxX - MinX + 1) * (MaxY - MinY + 1))
	{
		Result.Message = TEXT("the requested region is not fully present in the landscape");
		return Result;
	}

	Result.OldVertexMin = FIntPoint(MinX, MinY);
	Result.OldVertexMax = FIntPoint(MaxX, MaxY);
	Result.OldComponentCount = Info->XYtoComponentMap.Num();
	Result.ComponentSizeQuads = Info->ComponentSizeQuads;
	Result.NumSubsections = Proxies.Num() > 0 ? Proxies[0]->NumSubsections : 0;
	Result.SubsectionSizeQuads = Proxies.Num() > 0 ? Proxies[0]->SubsectionSizeQuads : 0;
	Result.StreamingProxiesAfter = Info->GetLandscapeProxy() == Landscape ? Proxies.Num() - 1 : Proxies.Num();
	Result.HeightmapZScale = Landscape->GetActorScale3D().Z;
	Result.HeightmapBackupPath = BackupPath;

	const FVector Location = Landscape->GetActorLocation();
	const float MPerVertex = FMath::Max(0.01f, static_cast<float>(Landscape->GetActorScale3D().X) / 100.f);
	Result.OldWorldMinM = FVector2D(Location.X / 100.f + MinX * MPerVertex,
	                                Location.Y / 100.f + MinY * MPerVertex);
	Result.OldWorldMaxM = FVector2D(Location.X / 100.f + MaxX * MPerVertex,
	                                Location.Y / 100.f + MaxY * MPerVertex);

	SaveBackup(BackupPath, Heights, MinX, MinY, MaxX, MaxY, Result.HeightmapZScale, Result.ComponentSizeQuads,
	           Result.NumSubsections, Result.SubsectionSizeQuads, Result.BackupBytes);

	Result.bSuccess = Result.BackupBytes > 0;
	Result.Message = FString::Printf(TEXT("landscape %d x %d vertices (%d components, %d proxies), backup %d bytes"),
	                                 MaxX - MinX + 1, MaxY - MinY + 1, Result.OldComponentCount,
	                                 Result.StreamingProxiesAfter, Result.BackupBytes);
	Result.Steps.Add(Result.Message);
#else
	Result.Message = TEXT("Phase 4B terrain expansion is editor only");
#endif

	return Result;
}

FPhase4BTerrainExpansionResult UPhase4BTerrainExpander::ExpandWorldTo4032(UObject* WorldContextObject, const FString& BackupPath)
{
	FPhase4BTerrainExpansionResult Result;

#if WITH_EDITOR
	using namespace Phase4BTerrainExpansion;

	UWorld* World = GEngine ? GEngine->GetWorldFromContextObject(WorldContextObject, EGetWorldErrorMode::LogAndReturnNull) : nullptr;
	if (World == nullptr)
	{
		Result.Message = TEXT("no valid editor world");
		return Result;
	}

	ULandscapeInfo* Info = nullptr;
	TArray<ALandscapeProxy*> Proxies;
	ALandscape* Landscape = FindLandscape(World, Info, Proxies);
	if (Landscape == nullptr || Info == nullptr)
	{
		Result.Message = TEXT("no ALandscape / ULandscapeInfo in the level");
		return Result;
	}

	// ------------------------------------------------------------------ source data
	// The block that must keep its exact heights comes from the backup sidecar and its
	// heightfield is read from the backup file: the helper must not depend on which World
	// Partition cells happen to be loaded at that moment.
	const FString MetaPath = BackupPath + TEXT(".txt");
	int32 PreservedMinX = 0;
	int32 PreservedMinY = 0;
	int32 PreservedMaxX = 0;
	int32 PreservedMaxY = 0;
	if (BackupPath.IsEmpty() || !LoadPreservedExtent(MetaPath, PreservedMinX, PreservedMinY, PreservedMaxX, PreservedMaxY))
	{
		Result.Message = FString::Printf(TEXT("no usable heightmap backup sidecar (%s) - refusing to expand"), *MetaPath);
		return Result;
	}

	TArray<uint16> PreservedHeights;
	if (!LoadHeightmapFile(BackupPath, PreservedHeights))
	{
		Result.Message = FString::Printf(TEXT("could not read the heightmap backup (%s)"), *BackupPath);
		return Result;
	}
	const int32 PreservedSizeX = PreservedMaxX - PreservedMinX + 1;
	const int32 PreservedSizeY = PreservedMaxY - PreservedMinY + 1;
	if (PreservedHeights.Num() != PreservedSizeX * PreservedSizeY)
	{
		Result.Message = FString::Printf(TEXT("heightmap backup size mismatch: %d values for a %d x %d block"),
		                                 PreservedHeights.Num(), PreservedSizeX, PreservedSizeY);
		return Result;
	}
	Result.Steps.Add(FString::Printf(
		TEXT("preserved block loaded from the backup: %d x %d vertices (%d,%d)-(%d,%d)"),
		PreservedSizeX, PreservedSizeY, PreservedMinX, PreservedMinY, PreservedMaxX, PreservedMaxY));

	// Current landscape grid, for the record only: World Partition keeps only the loaded
	// cells, so this value is never used for the maths below.
	const FIntRect CompleteExtent = Info->GetCompleteLandscapeExtent();
	Result.OldVertexMin = CompleteExtent.Min;
	Result.OldVertexMax = CompleteExtent.Max;
	Result.OldComponentCount = Info->XYtoComponentMap.Num();
	Result.ComponentSizeQuads = Info->ComponentSizeQuads;
	Result.NumSubsections = Proxies.Num() > 0 ? Proxies[0]->NumSubsections : 0;
	Result.SubsectionSizeQuads = Proxies.Num() > 0 ? Proxies[0]->SubsectionSizeQuads : 0;
	Result.HeightmapZScale = Landscape->GetActorScale3D().Z;
	Result.HeightmapBackupPath = BackupPath;
	Result.BackupBytes = PreservedHeights.Num() * static_cast<int32>(sizeof(uint16));
	const float ZScale = Result.HeightmapZScale;

	const FVector Location = Landscape->GetActorLocation();
	const float MPerVertex = FMath::Max(0.01f, static_cast<float>(Landscape->GetActorScale3D().X) / 100.f);
	const float OriginXM = Location.X / 100.f;
	const float OriginYM = Location.Y / 100.f;
	Result.OldWorldMinM = FVector2D(OriginXM + CompleteExtent.Min.X * MPerVertex,
	                                OriginYM + CompleteExtent.Min.Y * MPerVertex);
	Result.OldWorldMaxM = FVector2D(OriginXM + CompleteExtent.Max.X * MPerVertex,
	                                OriginYM + CompleteExtent.Max.Y * MPerVertex);

	// ------------------------------------------------------------------ target grid
	const int32 QuadsPerComponent = FMath::Max(1, Info->ComponentSizeQuads);
	const int32 ComponentsPerAxis = FMath::Max(1, TargetWorldSizeM / QuadsPerComponent);
	const int32 BlocksPerAxis = FMath::Max(1, (PreservedMaxX - PreservedMinX) / QuadsPerComponent);
	const int32 ExtraComponents = FMath::Max(0, ComponentsPerAxis - BlocksPerAxis);
	const int32 LowerExtra = ExtraComponents / 2;
	const int32 LowerVertex = PreservedMinX - LowerExtra * QuadsPerComponent;
	const int32 UpperVertex = LowerVertex + ComponentsPerAxis * QuadsPerComponent;

	Result.NewVertexMin = FIntPoint(LowerVertex, LowerVertex);
	Result.NewVertexMax = FIntPoint(UpperVertex, UpperVertex);
	Result.NewComponentCount = FIntPoint(ComponentsPerAxis, ComponentsPerAxis);
	Result.NewWorldMinM = FVector2D(OriginXM + LowerVertex * MPerVertex, OriginYM + LowerVertex * MPerVertex);
	Result.NewWorldMaxM = FVector2D(OriginXM + UpperVertex * MPerVertex, OriginYM + UpperVertex * MPerVertex);
	Result.NewWorldSizeM = Result.NewWorldMaxM.X - Result.NewWorldMinM.X;
	Result.Steps.Add(FString::Printf(
		TEXT("grid: %d x %d components, vertices %d..%d, world %.1f..%.1f m (%.1f x %.1f m)"),
		ComponentsPerAxis, ComponentsPerAxis, LowerVertex, UpperVertex, Result.NewWorldMinM.X, Result.NewWorldMaxM.X,
		Result.NewWorldSizeM, Result.NewWorldMaxM.Y - Result.NewWorldMinM.Y));

	const int32 NewSize = UpperVertex - LowerVertex + 1;

	const FVector2D PreservedWorldMinM(OriginXM + PreservedMinX * MPerVertex, OriginYM + PreservedMinY * MPerVertex);
	const FVector2D PreservedWorldMaxM(OriginXM + PreservedMaxX * MPerVertex, OriginYM + PreservedMaxY * MPerVertex);

	// ------------------------------------------------------------------ heightfield
	TArray<uint16> NewHeights;
	NewHeights.SetNumUninitialized(NewSize * NewSize);
	for (int32 Y = 0; Y < NewSize; ++Y)
	{
		const float WorldYM = Result.NewWorldMinM.Y + Y * MPerVertex;
		for (int32 X = 0; X < NewSize; ++X)
		{
			const float WorldXM = Result.NewWorldMinM.X + X * MPerVertex;
			const int32 VertexX = LowerVertex + X;
			const int32 VertexY = LowerVertex + Y;
			const int32 SourceX = VertexX - PreservedMinX;
			const int32 SourceY = VertexY - PreservedMinY;
			const bool bInsidePreserved = (SourceX >= 0) && (SourceX < PreservedSizeX)
			                              && (SourceY >= 0) && (SourceY < PreservedSizeY);
			if (bInsidePreserved)
			{
				// the original block keeps the heights it was built with
				NewHeights[Y * NewSize + X] = PreservedHeights[SourceY * PreservedSizeX + SourceX];
				continue;
			}

			// new area: the preserved block edge heights blend into the Phase 4B relief
			const uint16 EdgeValue = PreservedHeights[FMath::Clamp(SourceY, 0, PreservedSizeY - 1) * PreservedSizeX
			                                           + FMath::Clamp(SourceX, 0, PreservedSizeX - 1)];
			const float EdgeM = RawToMeters(EdgeValue, ZScale);
			const float OutsideX = FMath::Max(0.f, FMath::Max(PreservedWorldMinM.X - WorldXM, WorldXM - PreservedWorldMaxM.X));
			const float OutsideY = FMath::Max(0.f, FMath::Max(PreservedWorldMinM.Y - WorldYM, WorldYM - PreservedWorldMaxM.Y));
			const float Distance = FMath::Sqrt(OutsideX * OutsideX + OutsideY * OutsideY);
			const float Blend = Falloff(Distance, 0.f, BlendBandM);
			NewHeights[Y * NewSize + X] = MetersToRaw(FMath::Lerp(OuterHeightM(FVector2D(WorldXM, WorldYM)), EdgeM, Blend), ZScale);
		}
	}

	// ------------------------------------------------------------------ add components
	ULandscapeSubsystem* Subsystem = World->GetSubsystem<ULandscapeSubsystem>();
	if (Subsystem == nullptr)
	{
		Result.Message = TEXT("no ULandscapeSubsystem in the world");
		return Result;
	}

	Info->Modify();
	Landscape->Modify();

	int32 CompIndexX1 = 0;
	int32 CompIndexY1 = 0;
	int32 CompIndexX2 = 0;
	int32 CompIndexY2 = 0;
	ALandscape::CalcComponentIndicesNoOverlap(LowerVertex, LowerVertex, UpperVertex, UpperVertex, QuadsPerComponent,
	                                          CompIndexX1, CompIndexY1, CompIndexX2, CompIndexY2);

	TArray<const ULandscapeEditLayerBase*> PersistentLayers;
	for (const ULandscapeEditLayerBase* Layer : Landscape->GetEditLayersConst())
	{
		if (Layer != nullptr && Layer->NeedsPersistentTextures())
		{
			PersistentLayers.Add(Layer);
		}
	}

	for (int32 ComponentIndexY = CompIndexY1; ComponentIndexY <= CompIndexY2; ++ComponentIndexY)
	{
		for (int32 ComponentIndexX = CompIndexX1; ComponentIndexX <= CompIndexX2; ++ComponentIndexX)
		{
			const FIntPoint Key(ComponentIndexX, ComponentIndexY);
			if (Info->XYtoComponentMap.Contains(Key))
			{
				continue;
			}

			const FIntPoint ComponentBase = Key * QuadsPerComponent;
			ALandscapeProxy* Proxy = Subsystem->FindOrAddLandscapeProxy(Info, ComponentBase);
			if (Proxy == nullptr)
			{
				continue;
			}

			ULandscapeComponent* Component = NewObject<ULandscapeComponent>(Proxy, NAME_None, RF_Transactional);
			Component->Init(ComponentBase.X, ComponentBase.Y, Proxy->ComponentSizeQuads, Proxy->NumSubsections,
			                Proxy->SubsectionSizeQuads);
			Info->XYtoComponentMap.Add(Key, Component);
			Info->XYtoAddCollisionMap.Remove(Key);

			const int32 ComponentVerts = (Component->SubsectionSizeQuads + 1) * Component->NumSubsections;
			TArray<FColor> EmptyHeightmap;
			EmptyHeightmap.AddZeroed(FMath::Square(ComponentVerts));
			Component->InitHeightmapData(EmptyHeightmap, /*bUpdateCollision = */false);

			TMap<UTexture2D*, UTexture2D*> CreatedTextures;
			for (const ULandscapeEditLayerBase* Layer : PersistentLayers)
			{
				Component->AddDefaultLayerData(Layer->GetGuid(), { Component }, CreatedTextures);
			}

			Component->UpdateMaterialInstances();
			Component->UpdateCachedBounds();
			Component->UpdateBounds();
			Component->RegisterComponent();
			Component->UpdateCollisionData();
			++Result.ComponentsCreated;
		}
	}
	Result.Steps.Add(FString::Printf(TEXT("components created: %d"), Result.ComponentsCreated));

	// ------------------------------------------------------------------ write the new area
	// Only the ring outside the original block is written (the original components keep
	// their own heightmaps); the strips also overlap where they meet, which is harmless.
	TArray<FIntRect> Strips;
	Strips.Add(FIntRect(LowerVertex, LowerVertex, PreservedMinX - 1, UpperVertex));
	Strips.Add(FIntRect(PreservedMaxX + 1, LowerVertex, UpperVertex, UpperVertex));
	Strips.Add(FIntRect(PreservedMinX, LowerVertex, PreservedMaxX, PreservedMinY - 1));
	Strips.Add(FIntRect(PreservedMinX, PreservedMaxY + 1, PreservedMaxX, UpperVertex));

	for (const FIntRect& Strip : Strips)
	{
		const int32 X1 = Strip.Min.X;
		const int32 Y1 = Strip.Min.Y;
		const int32 X2 = Strip.Max.X;
		const int32 Y2 = Strip.Max.Y;
		if (X2 < X1 || Y2 < Y1)
		{
			continue;
		}
		const int32 StripSizeX = X2 - X1 + 1;
		const int32 StripSizeY = Y2 - Y1 + 1;
		TArray<uint16> StripHeights;
		StripHeights.SetNumUninitialized(StripSizeX * StripSizeY);
		for (int32 Y = 0; Y < StripSizeY; ++Y)
		{
			for (int32 X = 0; X < StripSizeX; ++X)
			{
				const int32 SourceX = (X1 + X) - LowerVertex;
				const int32 SourceY = (Y1 + Y) - LowerVertex;
				StripHeights[Y * StripSizeX + X] = NewHeights[SourceY * NewSize + SourceX];
			}
		}
		FLandscapeEditDataInterface WriteEdit(Info);
		WriteEdit.SetHeightData(X1, Y1, X2, Y2, StripHeights.GetData(), /*InStride = */0, /*InCalcNormals = */true);
		WriteEdit.Flush();
		++Result.StripsWritten;
		Result.Steps.Add(FString::Printf(TEXT("strip written: vertices (%d,%d)-(%d,%d) = %d x %d"), X1, Y1, X2, Y2,
		                                 StripSizeX, StripSizeY));
	}

	// ------------------------------------------------------------------ finish the edit
	Landscape->ForceLayersFullUpdate();
	Landscape->RequestSplineLayerUpdate();
	Landscape->RequestLayersInitialization();
	if (GEngine != nullptr)
	{
		GEngine->BroadcastOnActorMoved(Landscape);
	}

	Result.StreamingProxiesAfter = 0;
	for (TActorIterator<ALandscapeStreamingProxy> It(World); It; ++It)
	{
		++Result.StreamingProxiesAfter;
	}

	// ------------------------------------------------------------------ samples
	const TArray<TPair<FString, FVector2D>> InnerSamples = {
		TPair<FString, FVector2D>(TEXT("home_pad"), FVector2D(750.f, 750.f)),
		TPair<FString, FVector2D>(TEXT("house"), FVector2D(760.f, 783.f)),
		TPair<FString, FVector2D>(TEXT("road_start"), FVector2D(750.f, 665.f)),
		TPair<FString, FVector2D>(TEXT("road_mid"), FVector2D(222.f, 215.f)),
		TPair<FString, FVector2D>(TEXT("forest_belt"), FVector2D(450.f, 450.f)),
		TPair<FString, FVector2D>(TEXT("old_world_sw"), FVector2D(-1000.f, -1000.f)),
		TPair<FString, FVector2D>(TEXT("old_world_ne"), FVector2D(1000.f, 1000.f))};

	for (const TPair<FString, FVector2D>& Sample : InnerSamples)
	{
		const int32 VertexX = FMath::RoundToInt((Sample.Value.X - OriginXM) / MPerVertex);
		const int32 VertexY = FMath::RoundToInt((Sample.Value.Y - OriginYM) / MPerVertex);
		const int32 SourceX = VertexX - PreservedMinX;
		const int32 SourceY = VertexY - PreservedMinY;
		if (SourceX >= 0 && SourceX < PreservedSizeX && SourceY >= 0 && SourceY < PreservedSizeY)
		{
			Result.PreservedBeforeM.Add(Sample.Key,
			                            RawToMeters(PreservedHeights[SourceY * PreservedSizeX + SourceX], ZScale));
		}
		float HeightAfter = 0.f;
		if (SampleHeightM(Info, FVector2D(VertexX, VertexY), ZScale, HeightAfter))
		{
			Result.PreservedAfterM.Add(Sample.Key, HeightAfter);
		}
	}

	Result.MaxPreservedDeltaM = 0.f;
	for (const TPair<FString, float>& Pair : Result.PreservedBeforeM)
	{
		if (const float* After = Result.PreservedAfterM.Find(Pair.Key))
		{
			Result.MaxPreservedDeltaM = FMath::Max(Result.MaxPreservedDeltaM, FMath::Abs(*After - Pair.Value));
		}
	}

	const TArray<TPair<FString, FVector2D>> OuterSamples = {
		TPair<FString, FVector2D>(TEXT("outer_north_west"), FVector2D(-1500.f, 1800.f)),
		TPair<FString, FVector2D>(TEXT("outer_north"), FVector2D(200.f, 1900.f)),
		TPair<FString, FVector2D>(TEXT("outer_north_east"), FVector2D(1700.f, 1700.f)),
		TPair<FString, FVector2D>(TEXT("outer_east"), FVector2D(1900.f, 200.f)),
		TPair<FString, FVector2D>(TEXT("outer_south_east"), FVector2D(1600.f, -1600.f)),
		TPair<FString, FVector2D>(TEXT("outer_south"), FVector2D(0.f, -1900.f)),
		TPair<FString, FVector2D>(TEXT("outer_south_west"), FVector2D(-1800.f, -1800.f)),
		TPair<FString, FVector2D>(TEXT("outer_west"), FVector2D(-1900.f, -100.f)),
		TPair<FString, FVector2D>(TEXT("outer_blend_band"), FVector2D(-1300.f, 750.f))};

	float MinOuter = FLT_MAX;
	float MaxOuter = -FLT_MAX;
	for (const TPair<FString, FVector2D>& Sample : OuterSamples)
	{
		const int32 VertexX = FMath::RoundToInt((Sample.Value.X - OriginXM) / MPerVertex);
		const int32 VertexY = FMath::RoundToInt((Sample.Value.Y - OriginYM) / MPerVertex);
		const int32 GridX = VertexX - LowerVertex;
		const int32 GridY = VertexY - LowerVertex;
		if (GridX < 0 || GridX >= NewSize || GridY < 0 || GridY >= NewSize)
		{
			continue;
		}
		// sample the grid that was just written (independent of which cells are streamed in)
		const float Height = RawToMeters(NewHeights[GridY * NewSize + GridX], ZScale);
		Result.OuterSamplesM.Add(Sample.Key, Height);
		MinOuter = FMath::Min(MinOuter, Height);
		MaxOuter = FMath::Max(MaxOuter, Height);
	}
	Result.OuterReliefM.Add(TEXT("min"), MinOuter);
	Result.OuterReliefM.Add(TEXT("max"), MaxOuter);
	Result.OuterReliefM.Add(TEXT("spread"), MaxOuter - MinOuter);

	Result.bSuccess = Result.StripsWritten > 0;
	Result.Message = FString::Printf(
		TEXT("world is now %.1f x %.1f m (vertices %d..%d): %d components created, %d strips written, "
		     "%d streaming proxies, preserved-area max delta %.3f m"),
		Result.NewWorldSizeM, Result.NewWorldMaxM.Y - Result.NewWorldMinM.Y, LowerVertex, UpperVertex,
		Result.ComponentsCreated, Result.StripsWritten, Result.StreamingProxiesAfter, Result.MaxPreservedDeltaM);
	Result.Steps.Add(Result.Message);
#else
	Result.Message = TEXT("Phase 4B terrain expansion is editor only");
#endif

	return Result;
}
