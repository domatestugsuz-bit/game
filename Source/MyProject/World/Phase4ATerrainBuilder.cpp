// Copyright Epic Games, Inc. All Rights Reserved.
// Phase 4A - large-world terrain blockout builder (implementation).

#include "World/Phase4ATerrainBuilder.h"

#include "Components/SplineComponent.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Actor.h"
#include "Landscape.h"
#include "LandscapeComponent.h"
#include "LandscapeEdit.h"
#include "LandscapeInfo.h"
#include "LandscapeProxy.h"
#include "LandscapeSubsystem.h"
#include "Materials/MaterialInterface.h"

#if WITH_EDITOR
#include "Engine/Level.h"
#include "LandscapeDataAccess.h"
#endif

namespace Phase4ATerrain
{
	// ------------------------------------------------------------------
	// Landscape configuration (Phase 4A choice, see report for reasoning)
	// ------------------------------------------------------------------
	// 4032 quads per axis at 1 m per quad  ->  4032 m x 4032 m square world.
	// 63 quads per section, 4 sections per component -> 252 m components.
	// 16 x 16 components = 256 components (streamable, WP friendly).
	static constexpr int32 QuadsPerSection = 63;
	static constexpr int32 SectionsPerComponent = 4;
	static constexpr int32 ComponentCount = 16;
	static constexpr int32 QuadsPerAxis = ComponentCount * SectionsPerComponent * QuadsPerSection; // 4032
	static constexpr float QuadSizeCm = 100.f;      // 1 m
	static constexpr float LandscapeZScale = 100.f; // default: 65535 units -> ~+/-256 m
	static constexpr float HalfExtentM = QuadsPerAxis * 0.5f; // 2016 m: design reference extent

	static const FName LandscapeLabel(TEXT("Landscape_RuralBlockout"));

	// Field space: set up by BuildRuralTerrain from the landscape grid that actually
	// exists in the level (converts between vertex indices and world meters).
	static FVector2D FieldOriginM(0.f, 0.f);
	static float FieldStepM = 1.f;

	static int32 WorldToIndexX(float Meter) { return FMath::RoundToInt((Meter - FieldOriginM.X) / FieldStepM); }
	static int32 WorldToIndexY(float Meter) { return FMath::RoundToInt((Meter - FieldOriginM.Y) / FieldStepM); }
	static FVector2D IndexToWorld(int32 X, int32 Y) { return FieldOriginM + FVector2D(X * FieldStepM, Y * FieldStepM); }

	// ------------------------------------------------------------------
	// Design (all values in meters, world centered on the landscape origin)
	// ------------------------------------------------------------------
	struct FDesign
	{
		/** Layout scale relative to the reference 4032 m world (set by BuildRuralTerrain). */
		float Scale = 1.f;
		/** Vertical scale (so relief stays plausible in smaller worlds). */
		float HeightScale = 1.f;

		// Home property: near the north-east corner, 516 m in from both edges.
		FVector2D HomeCenter = FVector2D(1500.f, 1500.f);
		float HomeClearingHeightM = 0.f; // resolved from the field at build time
		static constexpr float HomeClearingRadiusM = 95.f;
		static constexpr float HomeClearingFalloffM = 175.f;

		// Forest hill mass to the north-east of the home; the home sits on its
		// south-western shoulder, well below the summit (not on a huge mountain).
		FVector2D HillCenter = FVector2D(1780.f, 1790.f);
		static constexpr float HillRiseM = 32.f;
		static constexpr float HillInnerM = 130.f;
		static constexpr float HillOuterM = 640.f;

		// Macro elevation: high around the home region, low in the countryside.
		static constexpr float LowlandHeightM = 6.f;
		static constexpr float HighlandHeightM = 162.f;
		static constexpr float HighlandInnerM = 420.f;
		static constexpr float HighlandOuterM = 2650.f;

		// Home shoulder.
		static constexpr float ShoulderRiseM = 16.f;
		static constexpr float ShoulderInnerM = 240.f;
		static constexpr float ShoulderOuterM = 980.f;

		// Road carving.
		static constexpr float RoadHalfWidthM = 4.5f;   // ~9 m wide dirt road
		static constexpr float RoadFalloffM = 16.f;
		static constexpr float RoadSampleStepM = 2.f;
		static constexpr float HomeRoadMaxGrade = 0.085f; // 8.5 % downhill limit
		static constexpr float MainRoadMaxGrade = 0.05f;  // 5 % for the future main road

		// Reserved flat areas for later gameplay locations.
		FVector2D TownCenter = FVector2D(-500.f, -1650.f);
		FVector2D TownHalfSize = FVector2D(700.f, 400.f);
		static constexpr float TownHeightM = 16.f;

		FVector2D MechanicCenter = FVector2D(400.f, -1250.f);
		FVector2D MechanicHalfSize = FVector2D(65.f, 50.f);

		FVector2D MarketCenter = FVector2D(1000.f, -1230.f);
		FVector2D MarketHalfSize = FVector2D(85.f, 65.f);
	};

	/** Smooth 1 -> 0 falloff: 1 inside Inner, 0 beyond Outer. */
	static float Falloff(float Distance, float Inner, float Outer)
	{
		if (Outer <= Inner)
		{
			return Distance <= Inner ? 1.f : 0.f;
		}
		return 1.f - FMath::SmoothStep(Inner, Outer, Distance);
	}

	/** Fractal value in ~[-1, 1] built from Unreal's Perlin noise. */
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

	/** Base elevation field: macro slope + rolling hills/ridges + shallow draws. */
	static float BaseHeightM(const FVector2D& Point, const FDesign& Design)
	{
		const float DistHome = FVector2D::Distance(Point, Design.HomeCenter);
		const float DistHill = FVector2D::Distance(Point, Design.HillCenter);

		// 1 = home highland, 0 = open countryside (all radii follow the world scale).
		const float Highland = 1.f - FMath::SmoothStep(FDesign::HighlandInnerM * Design.Scale,
			FDesign::HighlandOuterM * Design.Scale, DistHome);

		float Height = FDesign::LowlandHeightM + FDesign::HighlandHeightM * Design.HeightScale * Highland;

		// Rolling hills / ridges: pronounced around the home and along the upper road,
		// muted in the lower countryside so that farmland stays usable.
		Height += Fbm(Point * (1.f / 950.f), 4) * (9.f + 26.f * Highland);
		Height += Fbm(Point * (1.f / 310.f) + FVector2D(37.5f, -12.5f), 3) * (3.f + 8.f * Highland);

		// Shallow meandering valleys / drainage draws.
		const float Draw = FMath::Max(0.f, Fbm(Point * (1.f / 640.f) + FVector2D(-73.f, 51.f), 3));
		Height -= Draw * (3.f + 10.f * Highland);

		// Home shoulder and the forest hill mass north-east of the home.
		Height += FDesign::ShoulderRiseM * Design.HeightScale * Falloff(DistHome,
			FDesign::ShoulderInnerM * Design.Scale, FDesign::ShoulderOuterM * Design.Scale);
		Height += FDesign::HillRiseM * Design.HeightScale * Falloff(DistHill,
			FDesign::HillInnerM * Design.Scale, FDesign::HillOuterM * Design.Scale);

		return Height;
	}

	/** Landscape heightmap value (MidValue 32768 == 0 m, LANDSCAPE_ZSCALE = 1/128). */
	static uint16 HeightToLandscapeValue(float HeightM, float ZScale)
	{
		const float Pixels = 32768.f + (HeightM * 100.f * 128.f) / ZScale;
		return static_cast<uint16>(FMath::Clamp(FMath::RoundToInt(Pixels), 0, 65535));
	}

	// ------------------------------------------------------------------
	// World <-> heightmap helpers (1 m per quad, world centered on origin)
	// ------------------------------------------------------------------
	static float SampleField(const TArray<float>& Field, int32 SizeX, int32 SizeY, const FVector2D& WorldM)
	{
		const float CX = FMath::Clamp((WorldM.X - FieldOriginM.X) / FieldStepM, 0.f, static_cast<float>(SizeX - 1));
		const float CY = FMath::Clamp((WorldM.Y - FieldOriginM.Y) / FieldStepM, 0.f, static_cast<float>(SizeY - 1));
		const int32 X0 = FMath::FloorToInt(CX);
		const int32 Y0 = FMath::FloorToInt(CY);
		const int32 X1 = FMath::Min(X0 + 1, SizeX - 1);
		const int32 Y1 = FMath::Min(Y0 + 1, SizeY - 1);
		const float FX = CX - X0;
		const float FY = CY - Y0;
		const float A = FMath::Lerp(Field[Y0 * SizeX + X0], Field[Y0 * SizeX + X1], FX);
		const float B = FMath::Lerp(Field[Y1 * SizeX + X0], Field[Y1 * SizeX + X1], FX);
		return FMath::Lerp(A, B, FY);
	}

	/** Blends a circular area of the heightfield towards a target height. */
	static void FlattenCircle(TArray<float>& Field, int32 SizeX, int32 SizeY, const FVector2D& Center,
	                          float TargetHeightM, float InnerM, float OuterM)
	{
		const int32 MinX = FMath::Max(0, WorldToIndexX(Center.X - OuterM));
		const int32 MaxX = FMath::Min(SizeX - 1, WorldToIndexX(Center.X + OuterM));
		const int32 MinY = FMath::Max(0, WorldToIndexY(Center.Y - OuterM));
		const int32 MaxY = FMath::Min(SizeY - 1, WorldToIndexY(Center.Y + OuterM));
		for (int32 Y = MinY; Y <= MaxY; ++Y)
		{
			for (int32 X = MinX; X <= MaxX; ++X)
			{
				const FVector2D WorldM = IndexToWorld(X, Y);
				const float Weight = Falloff(FVector2D::Distance(WorldM, Center), InnerM, OuterM);
				if (Weight > 0.f)
				{
					float& Height = Field[Y * SizeX + X];
					Height = FMath::Lerp(Height, TargetHeightM, Weight);
				}
			}
		}
	}

	/** Blends a soft-edged rectangle of the heightfield towards a target height. */
	static void FlattenRectangle(TArray<float>& Field, int32 SizeX, int32 SizeY, const FVector2D& Center,
	                             const FVector2D& HalfSize, float TargetHeightM, float EdgeM)
	{
		const FVector2D Extent = HalfSize + FVector2D(EdgeM, EdgeM);
		const int32 MinX = FMath::Max(0, WorldToIndexX(Center.X - Extent.X));
		const int32 MaxX = FMath::Min(SizeX - 1, WorldToIndexX(Center.X + Extent.X));
		const int32 MinY = FMath::Max(0, WorldToIndexY(Center.Y - Extent.Y));
		const int32 MaxY = FMath::Min(SizeY - 1, WorldToIndexY(Center.Y + Extent.Y));
		for (int32 Y = MinY; Y <= MaxY; ++Y)
		{
			for (int32 X = MinX; X <= MaxX; ++X)
			{
				const FVector2D WorldM = IndexToWorld(X, Y);
				const float WeightX = Falloff(FMath::Abs(WorldM.X - Center.X), HalfSize.X, HalfSize.X + EdgeM);
				const float WeightY = Falloff(FMath::Abs(WorldM.Y - Center.Y), HalfSize.Y, HalfSize.Y + EdgeM);
				const float Weight = WeightX * WeightY;
				if (Weight > 0.f)
				{
					float& Height = Field[Y * SizeX + X];
					Height = FMath::Lerp(Height, TargetHeightM, Weight);
				}
			}
		}
	}

	// ------------------------------------------------------------------
	// Routes (world XY in meters). The home road leaves the home/garage area,
	// runs through the forest belt and descends into the lower countryside.
	// ------------------------------------------------------------------
	static const TArray<FVector2D>& HomeRoadPoints()
	{
		static const TArray<FVector2D> Points = {
			FVector2D(1500.f, 1330.f), FVector2D(1420.f, 1250.f), FVector2D(1330.f, 1180.f),
			FVector2D(1140.f, 1145.f), FVector2D(905.f, 1010.f), FVector2D(780.f, 930.f),
			FVector2D(620.f, 800.f), FVector2D(505.f, 620.f), FVector2D(445.f, 430.f),
			FVector2D(520.f, 250.f), FVector2D(700.f, 80.f), FVector2D(950.f, -95.f),
			FVector2D(1265.f, -300.f), FVector2D(1430.f, -560.f), FVector2D(1560.f, -830.f),
			FVector2D(1655.f, -1140.f), FVector2D(1710.f, -1450.f), FVector2D(1755.f, -1730.f),
			FVector2D(1785.f, -1950.f)
		};
		return Points;
	}

	static const TArray<FVector2D>& FutureMainRoadPoints()
	{
		static const TArray<FVector2D> Points = {
			FVector2D(-1960.f, -1180.f), FVector2D(-1200.f, -1160.f), FVector2D(-400.f, -1120.f),
			FVector2D(400.f, -1140.f), FVector2D(1180.f, -1125.f), FVector2D(1655.f, -1140.f)
		};
		return Points;
	}

	/** Resamples a polyline every StepM meters (world space). */
	static void ResamplePolyline(const TArray<FVector2D>& Points, float StepM, TArray<FVector2D>& OutSamples)
	{
		OutSamples.Reset();
		if (Points.Num() < 2)
		{
			return;
		}
		OutSamples.Add(Points[0]);
		float Carried = 0.f;
		for (int32 Index = 1; Index < Points.Num(); ++Index)
		{
			const FVector2D From = Points[Index - 1];
			const FVector2D To = Points[Index];
			const float Length = FVector2D::Distance(From, To);
			if (Length <= KINDA_SMALL_NUMBER)
			{
				continue;
			}
			const FVector2D Direction = (To - From) / Length;
			float Travelled = StepM - Carried;
			while (Travelled <= Length)
			{
				OutSamples.Add(From + Direction * Travelled);
				Travelled += StepM;
			}
			Carried = StepM - (Travelled - Length);
		}
		if (FVector2D::Distance(OutSamples.Last(), Points.Last()) > 0.5f)
		{
			OutSamples.Add(Points.Last());
		}
	}

	/**
	 * Carves a corridor into the heightfield along a route: the profile is smoothed,
	 * grade limited (and optionally forced to descend) so the road stays driveable,
	 * then stamped into the terrain with a natural falloff on both sides.
	 */
	static float CarveRoad(TArray<float>& Field, int32 SizeX, int32 SizeY, const FDesign& Design,
	                       const TArray<FVector2D>& RoutePoints, bool bForceDescent, float MaxGrade,
	                       float& OutStartHeightM, float& OutEndHeightM, float& OutMaxGrade,
	                       float& OutMaxRise, TArray<FVector>& OutSplinePoints)
	{
		TArray<FVector2D> Samples;
		ResamplePolyline(RoutePoints, FDesign::RoadSampleStepM, Samples);
		if (Samples.Num() < 2)
		{
			return 0.f;
		}

		TArray<float> Profile;
		Profile.SetNum(Samples.Num());
		for (int32 Index = 0; Index < Samples.Num(); ++Index)
		{
			Profile[Index] = SampleField(Field, SizeX, SizeY, Samples[Index]);
		}

		// Low pass so the road does not follow every terrain ripple.
		for (int32 Pass = 0; Pass < 4; ++Pass)
		{
			const TArray<float> Copy = Profile;
			for (int32 Index = 0; Index < Profile.Num(); ++Index)
			{
				float Sum = 0.f;
				int32 Count = 0;
				for (int32 Offset = -3; Offset <= 3; ++Offset)
				{
					const int32 Neighbour = Index + Offset;
					if (Neighbour >= 0 && Neighbour < Copy.Num())
					{
						Sum += Copy[Neighbour];
						++Count;
					}
				}
				Profile[Index] = Sum / FMath::Max(1, Count);
			}
		}

		// Grade limiting; the home road additionally never climbs.
		const float MaxDelta = MaxGrade * FDesign::RoadSampleStepM;
		for (int32 Index = 1; Index < Profile.Num(); ++Index)
		{
			Profile[Index] = FMath::Clamp(Profile[Index], Profile[Index - 1] - MaxDelta, Profile[Index - 1] + MaxDelta);
			if (bForceDescent)
			{
				Profile[Index] = FMath::Min(Profile[Index], Profile[Index - 1]);
			}
		}

		OutMaxGrade = 0.f;
		OutMaxRise = 0.f;
		for (int32 Index = 1; Index < Profile.Num(); ++Index)
		{
			OutMaxGrade = FMath::Max(OutMaxGrade,
				FMath::Abs(Profile[Index] - Profile[Index - 1]) / FDesign::RoadSampleStepM);
			OutMaxRise = FMath::Max(OutMaxRise, Profile[Index] - Profile[Index - 1]);
		}

		// Stamp the corridor (flat inside the half width, blending out over the falloff).
		const float Reach = FDesign::RoadHalfWidthM + FDesign::RoadFalloffM + 1.f;
		for (int32 Index = 0; Index < Samples.Num(); ++Index)
		{
			const FVector2D Sample = Samples[Index];
			const float Target = Profile[Index];
			const int32 MinX = FMath::Max(0, WorldToIndexX(Sample.X - Reach));
			const int32 MaxX = FMath::Min(SizeX - 1, WorldToIndexX(Sample.X + Reach));
			const int32 MinY = FMath::Max(0, WorldToIndexY(Sample.Y - Reach));
			const int32 MaxY = FMath::Min(SizeY - 1, WorldToIndexY(Sample.Y + Reach));
			for (int32 Y = MinY; Y <= MaxY; ++Y)
			{
				for (int32 X = MinX; X <= MaxX; ++X)
				{
					const FVector2D WorldM = IndexToWorld(X, Y);
					const float Distance = FVector2D::Distance(WorldM, Sample);
					const float Weight = Falloff(Distance, FDesign::RoadHalfWidthM,
						FDesign::RoadHalfWidthM + FDesign::RoadFalloffM);
					if (Weight > 0.f)
					{
						float& Height = Field[Y * SizeX + X];
						Height = FMath::Lerp(Height, Target, Weight);
					}
				}
			}
		}

		OutStartHeightM = Profile[0];
		OutEndHeightM = Profile.Last();

		OutSplinePoints.Reset();
		for (int32 Index = 0; Index < Samples.Num(); Index += 5)
		{
			OutSplinePoints.Add(FVector(Samples[Index].X * 100.f, Samples[Index].Y * 100.f, Profile[Index] * 100.f));
		}
		OutSplinePoints.Add(FVector(Samples.Last().X * 100.f, Samples.Last().Y * 100.f, Profile.Last() * 100.f));

		return (Samples.Num() - 1) * FDesign::RoadSampleStepM;
	}
}

int32 UPhase4ATerrainBuilder::ClearPreviousTerrain(UObject* WorldContextObject)
{
#if WITH_EDITOR
	UWorld* World = GEngine ? GEngine->GetWorldFromContextObject(WorldContextObject, EGetWorldErrorMode::LogAndReturnNull) : nullptr;
	if (!World)
	{
		return 0;
	}

	// Only remove what Phase 4A itself created previously: the route actors, a
	// previously built blockout landscape (matched by label) and leftover landscape
	// placeholders. The level's own landscape family is kept: it is the terrain that
	// BuildRuralTerrain shapes.
	TArray<AActor*> ToDestroy;
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		AActor* Actor = *It;
		if (!IsValid(Actor))
		{
			continue;
		}
		const FString ClassName = Actor->GetClass()->GetName();
		const FString Label = Actor->GetActorLabel();
		const bool bOurLandscape = (ClassName == TEXT("Landscape")) && (Label == Phase4ATerrain::LandscapeLabel.ToString());
		if (bOurLandscape || Label.StartsWith(TEXT("Road_Route_")) || ClassName.Contains(TEXT("Placeholder")))
		{
			ToDestroy.Add(Actor);
		}
	}

	int32 Removed = 0;
	for (AActor* Actor : ToDestroy)
	{
		if (IsValid(Actor))
		{
			World->DestroyActor(Actor, false, false);
			++Removed;
		}
	}

	// Deleting a landscape can leave a placeholder behind: clear those as well.
	TArray<AActor*> Leftovers;
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		if (IsValid(*It) && (*It)->GetClass()->GetName().Contains(TEXT("Placeholder")))
		{
			Leftovers.Add(*It);
		}
	}
	for (AActor* Actor : Leftovers)
	{
		World->DestroyActor(Actor, false, false);
		++Removed;
	}

	World->MarkPackageDirty();
	return Removed;
#else
	return 0;
#endif
}

FPhase4ATerrainBuildResult UPhase4ATerrainBuilder::BuildRuralTerrain(UObject* WorldContextObject, UMaterialInterface* LandscapeMaterial)
{
	FPhase4ATerrainBuildResult Result;
#if WITH_EDITOR
	UWorld* World = GEngine ? GEngine->GetWorldFromContextObject(WorldContextObject, EGetWorldErrorMode::LogAndReturnNull) : nullptr;
	if (!World)
	{
		Result.Message = TEXT("no valid editor world");
		return Result;
	}

	using namespace Phase4ATerrain;

	Result.ClearedActorCount = ClearPreviousTerrain(WorldContextObject);

	// ------------------------------------------------ find the level's landscape
	ALandscape* Landscape = nullptr;
	for (TActorIterator<ALandscape> It(World); It; ++It)
	{
		Landscape = *It;
		break;
	}
	if (Landscape == nullptr)
	{
		Result.Message = TEXT("no ALandscape in the level (create the level from /Engine/Maps/Templates/OpenWorld first)");
		return Result;
	}
	ULandscapeInfo* LandscapeInfo = Landscape->GetLandscapeInfo();
	if (LandscapeInfo == nullptr)
	{
		Result.Message = TEXT("the landscape has no ULandscapeInfo");
		return Result;
	}

	TArray<ALandscapeProxy*> Proxies;
	for (TActorIterator<ALandscapeProxy> It(World); It; ++It)
	{
		ALandscapeProxy* Proxy = *It;
		if (IsValid(Proxy) && (Proxy == Landscape || Proxy->GetLandscapeActor() == Landscape))
		{
			Proxies.Add(Proxy);
		}
	}
	Result.ProxyCount = Proxies.Num();
	Result.LandscapeLabel = Landscape->GetActorLabel();

	// ------------------------------------------------ grid and vertex rect to fill
	// The landscape is streamed as several actors (main landscape + streaming proxies),
	// so the rect is derived from the world bounds of all of them.
	const FTransform LandscapeTransform = Landscape->GetActorTransform();
	FBox LandscapeBounds(ForceInit);
	for (ALandscapeProxy* Proxy : Proxies)
	{
		FVector ProxyOrigin;
		FVector ProxyExtent;
		Proxy->GetActorBounds(/*bOnlyCollidingComponents=*/false, ProxyOrigin, ProxyExtent);
		LandscapeBounds += FBox::BuildAABB(ProxyOrigin, ProxyExtent);
	}
	if (!LandscapeBounds.IsValid)
	{
		Result.Message = TEXT("could not measure the landscape bounds");
		return Result;
	}
	const FVector LocalMin = LandscapeTransform.InverseTransformPosition(LandscapeBounds.Min);
	const FVector LocalMax = LandscapeTransform.InverseTransformPosition(LandscapeBounds.Max);
	const int32 VertexMinX = FMath::RoundToInt(LocalMin.X);
	const int32 VertexMinY = FMath::RoundToInt(LocalMin.Y);
	const int32 VertexMaxX = FMath::RoundToInt(LocalMax.X);
	const int32 VertexMaxY = FMath::RoundToInt(LocalMax.Y);
	if (VertexMaxX <= VertexMinX || VertexMaxY <= VertexMinY)
	{
		Result.Message = TEXT("the landscape has no components to edit");
		return Result;
	}

	Result.ComponentSizeQuads = Landscape->ComponentSizeQuads;
	Result.NumSubsections = Landscape->NumSubsections;
	Result.SubsectionSizeQuads = Landscape->SubsectionSizeQuads;
	Result.VertexMinX = VertexMinX;
	Result.VertexMinY = VertexMinY;
	Result.VertexMaxX = VertexMaxX;
	Result.VertexMaxY = VertexMaxY;

	// world mapping: one landscape vertex is (actor scale / 100) meters
	const FVector WorldAtMinVertex = LandscapeTransform.TransformPosition(FVector(VertexMinX, VertexMinY, 0)) / 100.f;
	FieldStepM = FMath::Max(0.01f, static_cast<float>(Landscape->GetActorScale3D().X) / 100.f);
	FieldOriginM = FVector2D(WorldAtMinVertex.X, WorldAtMinVertex.Y);

	const int32 SizeX = VertexMaxX - VertexMinX + 1;
	const int32 SizeY = VertexMaxY - VertexMinY + 1;
	Result.HeightmapSizeX = SizeX;
	Result.HeightmapSizeY = SizeY;
	Result.QuadSizeMeters = FieldStepM;
	Result.WorldMinM = FieldOriginM;
	Result.WorldMaxM = IndexToWorld(SizeX - 1, SizeY - 1);
	Result.WorldSizeMeters = FMath::Max(Result.WorldMaxM.X - Result.WorldMinM.X,
	                                    Result.WorldMaxM.Y - Result.WorldMinM.Y);

	// ------------------------------------------------ design anchored to the world edge
	// The reference design is authored for a 4032 m world; it is scaled to the world we
	// actually have (the engine template landscape), keeping the home near the corner.
	FDesign Design;
	Design.Scale = FMath::Clamp(Result.WorldSizeMeters / 4032.f, 0.25f, 2.f);
	Design.HeightScale = FMath::Sqrt(Design.Scale);
	const FVector2D OriginalHome(1500.f, 1500.f);
	const FVector2D Anchor = FVector2D(Result.WorldMaxM.X - 516.f * Design.Scale,
	                                   Result.WorldMaxM.Y - 516.f * Design.Scale);
	auto AnchorPoint = [&Anchor, &OriginalHome, &Design](const FVector2D& Point)
	{
		return Anchor + (Point - OriginalHome) * Design.Scale;
	};

	Design.HomeCenter = Anchor;
	Design.HillCenter = AnchorPoint(FVector2D(1780.f, 1790.f));
	Design.TownCenter = AnchorPoint(FVector2D(-500.f, -1650.f));
	Design.MechanicCenter = AnchorPoint(FVector2D(400.f, -1250.f));
	Design.MarketCenter = AnchorPoint(FVector2D(1000.f, -1230.f));

	auto AnchorRoute = [&AnchorPoint](const TArray<FVector2D>& In)
	{
		TArray<FVector2D> Out;
		Out.Reserve(In.Num());
		for (const FVector2D& Point : In)
		{
			Out.Add(AnchorPoint(Point));
		}
		return Out;
	};
	const TArray<FVector2D> HomeRoadRoute = AnchorRoute(HomeRoadPoints());
	const TArray<FVector2D> MainRoadRoute = AnchorRoute(FutureMainRoadPoints());

	// ------------------------------------------------ elevation field
	TArray<float> Field;
	Field.SetNumUninitialized(SizeX * SizeY);
	for (int32 Y = 0; Y < SizeY; ++Y)
	{
		for (int32 X = 0; X < SizeX; ++X)
		{
			Field[Y * SizeX + X] = BaseHeightM(IndexToWorld(X, Y), Design);
		}
	}

	// Home clearing: the levelled property pad (house + garage + yard + driveway space).
	Design.HomeClearingHeightM = SampleField(Field, SizeX, SizeY, Design.HomeCenter) + 3.f;
	Result.HomeCenter = Design.HomeCenter;
	Result.HomePadHeightM = Design.HomeClearingHeightM;
	FlattenCircle(Field, SizeX, SizeY, Design.HomeCenter, Design.HomeClearingHeightM,
		FDesign::HomeClearingRadiusM * Design.Scale, FDesign::HomeClearingFalloffM * Design.Scale);

	// Reserved flat ground for later gameplay locations.
	FlattenRectangle(Field, SizeX, SizeY, Design.TownCenter, Design.TownHalfSize * Design.Scale,
		FDesign::TownHeightM * Design.HeightScale, 150.f * Design.Scale);
	FlattenRectangle(Field, SizeX, SizeY, Design.MechanicCenter, Design.MechanicHalfSize * Design.Scale,
		SampleField(Field, SizeX, SizeY, Design.MechanicCenter) + 0.5f, 30.f);
	FlattenRectangle(Field, SizeX, SizeY, Design.MarketCenter, Design.MarketHalfSize * Design.Scale,
		SampleField(Field, SizeX, SizeY, Design.MarketCenter) + 0.5f, 30.f);

	// Roads: the home dirt road descends out of the forest belt, the future main road
	// stays gentle through the lower countryside.
	TArray<FVector> HomeSplinePoints;
	TArray<FVector> MainSplinePoints;
	Result.HomeRoadLengthM = CarveRoad(Field, SizeX, SizeY, Design, HomeRoadRoute, true,
		FDesign::HomeRoadMaxGrade, Result.HomeRoadStartHeightM, Result.HomeRoadEndHeightM,
		Result.HomeRoadMaxGrade, Result.MaxRoadRiseStepM, HomeSplinePoints);
	float MainStartHeightM = 0.f;
	float MainEndHeightM = 0.f;
	float MainGrade = 0.f;
	float MainRise = 0.f;
	CarveRoad(Field, SizeX, SizeY, Design, MainRoadRoute, false,
		FDesign::MainRoadMaxGrade, MainStartHeightM, MainEndHeightM, MainGrade, MainRise, MainSplinePoints);

	// ---------------------------------------------------------------- statistics
	{
		float MinZ = FLT_MAX;
		float MaxZ = -FLT_MAX;
		for (int32 Ring = 0; Ring < 2; ++Ring)
		{
			const float Radius = (Ring == 0 ? 0.4f : 0.8f) * FDesign::HomeClearingRadiusM * Design.Scale;
			for (int32 Index = 0; Index < 16; ++Index)
			{
				const float Angle = Index * PI / 8.f;
				const float Z = SampleField(Field, SizeX, SizeY,
					Design.HomeCenter + FVector2D(FMath::Cos(Angle), FMath::Sin(Angle)) * Radius);
				MinZ = FMath::Min(MinZ, Z);
				MaxZ = FMath::Max(MaxZ, Z);
			}
		}
		Result.ClearingFlatnessSpreadM = MaxZ - MinZ;

		float TownMinZ = FLT_MAX;
		float TownMaxZ = -FLT_MAX;
		for (int32 StepX = -1; StepX <= 1; ++StepX)
		{
			for (int32 StepY = -1; StepY <= 1; ++StepY)
			{
				const float Z = SampleField(Field, SizeX, SizeY, Design.TownCenter +
					FVector2D(StepX * Design.TownHalfSize.X * Design.Scale * 0.85f,
						StepY * Design.TownHalfSize.Y * Design.Scale * 0.85f));
				TownMinZ = FMath::Min(TownMinZ, Z);
				TownMaxZ = FMath::Max(TownMaxZ, Z);
			}
		}
		Result.TownFlatnessSpreadM = TownMaxZ - TownMinZ;
	}

	// ---------------------------------------------------------------- report samples
	TArray<TPair<FString, FVector2D>> Probes;
	Probes.Emplace(TEXT("home_clearing"), Design.HomeCenter);
	Probes.Emplace(TEXT("hill_summit"), Design.HillCenter);
	Probes.Emplace(TEXT("forest_belt"), Design.HomeCenter - FVector2D(600.f, 600.f) * Design.Scale);
	Probes.Emplace(TEXT("mid_road"), Design.HomeCenter - FVector2D(1015.f, 1250.f) * Design.Scale);
	Probes.Emplace(TEXT("lowland_south_west"), Result.WorldMinM + FVector2D(300.f, 300.f));
	Probes.Emplace(TEXT("lowland_south"),
		FVector2D((Result.WorldMinM.X + Result.WorldMaxM.X) * 0.5f, Result.WorldMinM.Y + 160.f));
	Probes.Emplace(TEXT("lowland_west"),
		FVector2D(Result.WorldMinM.X + 200.f, (Result.WorldMinM.Y + Result.WorldMaxM.Y) * 0.5f));
	Probes.Emplace(TEXT("north_west_region"), Result.WorldMinM + FVector2D(200.f, Result.WorldSizeMeters - 400.f));
	Probes.Emplace(TEXT("world_edge_north_east"), Result.WorldMaxM - FVector2D(30.f, 30.f));
	Probes.Emplace(TEXT("town_reserved"), Design.TownCenter);
	Probes.Emplace(TEXT("mechanic_reserved"), Design.MechanicCenter);
	Probes.Emplace(TEXT("market_reserved"), Design.MarketCenter);
	Probes.Emplace(TEXT("home_road_start"), HomeRoadRoute[0]);
	Probes.Emplace(TEXT("home_road_end"), HomeRoadRoute.Last());
	Probes.Emplace(TEXT("main_road_west"), MainRoadRoute[1]);
	Probes.Emplace(TEXT("main_road_junction"), MainRoadRoute.Last());

	auto Sample = [&Field, SizeX, SizeY](const TCHAR* Key, const FVector2D& Point, FPhase4ATerrainBuildResult& Out)
	{
		Out.ElevationSamplesM.Add(
			FString::Printf(TEXT("%s (%d,%d)"), Key, FMath::RoundToInt(Point.X), FMath::RoundToInt(Point.Y)),
			SampleField(Field, SizeX, SizeY, Point));
	};
	for (const TPair<FString, FVector2D>& Probe : Probes)
	{
		Sample(*Probe.Key, Probe.Value, Result);
	}

	// ---------------------------------------------------------------- write the terrain
	TArray<uint16> HeightData;
	HeightData.SetNumUninitialized(SizeX * SizeY);
	const float ActorZScale = Landscape->GetActorScale3D().Z;
	for (int32 Index = 0; Index < Field.Num(); ++Index)
	{
		HeightData[Index] = HeightToLandscapeValue(Field[Index], ActorZScale);
	}

	{
		// Bulk heightmap edit through the landscape editing interface (the same path the
		// landscape tools use), applied to the landscape's default edit layer.
		FLandscapeEditDataInterface LandscapeEdit(LandscapeInfo);
		LandscapeEdit.SetHeightData(VertexMinX, VertexMinY, VertexMaxX, VertexMaxY,
			HeightData.GetData(), /*InStride=*/0, /*InCalcNormals=*/false);
		LandscapeEdit.Flush();
	}

	// Make sure the edit layer content is merged into the render data right away
	// (this is what the editor's landscape rebuild does after layer content changes).
	Landscape->ForceLayersFullUpdate();

	// Read the heights back to prove that the designed terrain really landed.
	{
		FLandscapeEditDataInterface ReadEdit(LandscapeInfo);
		for (const TPair<FString, FVector2D>& Probe : Probes)
		{
			const int32 PX = FMath::Clamp(WorldToIndexX(Probe.Value.X), VertexMinX, VertexMaxX);
			const int32 PY = FMath::Clamp(WorldToIndexY(Probe.Value.Y), VertexMinY, VertexMaxY);
			uint16 Value = 32768;
			ReadEdit.GetHeightDataFast(PX, PY, PX, PY, &Value, /*InStride=*/1, nullptr, nullptr);
			Result.ReadbackSamplesM.Add(Probe.Key + FString::Printf(TEXT(" (%d,%d)"), PX, PY),
				(static_cast<float>(Value) - 32768.f) * ActorZScale / 12800.f);
		}
	}

	// Rebuild the landscape collision heightfields so the new terrain is walkable and
	// driveable (the render heightmap is updated by the edit interface, collision is not).
	for (ALandscapeProxy* Proxy : Proxies)
	{
		Proxy->RecreateCollisionComponents();
		Proxy->MarkPackageDirty();
	}

	if (LandscapeMaterial != nullptr)
	{
		Landscape->LandscapeMaterial = LandscapeMaterial;
		Landscape->UpdateAllComponentMaterialInstances();
	}

	TSet<ULandscapeComponent*> EditedComponents;
	LandscapeInfo->GetComponentsInRegion(VertexMinX, VertexMinY, VertexMaxX, VertexMaxY, EditedComponents);
	Result.ComponentCountX = EditedComponents.Num();
	Result.ComponentCountY = EditedComponents.Num();
	UE_LOG(LogTemp, Display,
		TEXT("P4A: landscape '%s' proxies=%d editedComponents=%d componentSizeQuads=%d subsections=%d subsectionSizeQuads=%d scale=%s"),
		*Landscape->GetActorLabel(), Proxies.Num(), EditedComponents.Num(), Landscape->ComponentSizeQuads,
		Landscape->NumSubsections, Landscape->SubsectionSizeQuads, *Landscape->GetActorScale3D().ToString());

	// ---------------------------------------------------------------- route splines
	auto SpawnRoute = [World](const TCHAR* Label, const TArray<FVector>& Points) -> FString
	{
		if (Points.Num() < 2)
		{
			return FString();
		}
		AActor* Actor = World->SpawnActor<AActor>(AActor::StaticClass(), FVector::ZeroVector, FRotator::ZeroRotator);
		if (!Actor)
		{
			return FString();
		}
		USplineComponent* Spline = NewObject<USplineComponent>(Actor, TEXT("RouteSpline"));
		Spline->SetMobility(EComponentMobility::Movable);
		Actor->SetRootComponent(Spline);
		Spline->RegisterComponent();
		Actor->AddInstanceComponent(Spline);
		Spline->ClearSplinePoints(false);
		for (const FVector& Point : Points)
		{
			Spline->AddSplinePoint(Point, ESplineCoordinateSpace::World, false);
		}
		Spline->UpdateSpline();
		Spline->SetClosedLoop(false, false);
		Actor->SetActorLabel(FString(Label));
		return Actor->GetActorLabel();
	};

	Result.RouteActorLabels.Add(SpawnRoute(TEXT("Road_Route_Home"), HomeSplinePoints));
	Result.RouteActorLabels.Add(SpawnRoute(TEXT("Road_Route_FutureMainRoad"), MainSplinePoints));

	World->MarkPackageDirty();
	Result.bSuccess = true;
	Result.Message = FString::Printf(
		TEXT("terrain written into '%s': %d components, %.0f x %.0f m world, %.2f m per quad"),
		*Landscape->GetActorLabel(), EditedComponents.Num(), Result.WorldSizeMeters, Result.WorldSizeMeters, FieldStepM);
#else
	Result.Message = TEXT("Phase 4A terrain builder is editor only");
#endif
	return Result;
}
