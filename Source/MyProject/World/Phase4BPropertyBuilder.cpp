// Copyright Epic Games, Inc. All Rights Reserved.
// Phase 4B - player home property builder (implementation).

#include "World/Phase4BPropertyBuilder.h"

#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "PhysicsEngine/BodySetup.h"
#include "PhysicsEngine/ConvexElem.h"
#include "Engine/Engine.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Actor.h"
#include "Landscape.h"
#include "LandscapeEdit.h"
#include "LandscapeInfo.h"
#include "LandscapeProxy.h"
#include "Materials/MaterialInterface.h"
#include "UObject/Package.h"
#include "UObject/SavePackage.h"

#if WITH_EDITOR
#include "AssetRegistry/AssetRegistryModule.h"
#include "Components/SplineComponent.h"
#include "Materials/Material.h"
#include "MeshDescription.h"
#include "Misc/PackageName.h"
#include "StaticMeshAttributes.h"
#endif

namespace Phase4B
{
	// ------------------------------------------------------------------
	// Constants
	// ------------------------------------------------------------------
	static const FString AssetDir = TEXT("/Game/Game/Environment/Home");

	/** Material instances the generated meshes use (created by the Phase 4B Python step). */
	static const TCHAR* MatPlaster = TEXT("/Game/Game/Environment/Home/MI_Plaster.MI_Plaster");
	static const TCHAR* MatRoofTile = TEXT("/Game/Game/Environment/Home/MI_RoofTile.MI_RoofTile");
	static const TCHAR* MatWoodTrim = TEXT("/Game/Game/Environment/Home/MI_WoodTrim.MI_WoodTrim");
	static const TCHAR* MatWoodPlank = TEXT("/Game/Game/Environment/Home/MI_WoodPlank.MI_WoodPlank");
	static const TCHAR* MatMetal = TEXT("/Game/Game/Environment/Home/MI_MetalDoor.MI_MetalDoor");
	static const TCHAR* MatGlass = TEXT("/Game/Game/Environment/Home/MI_Glass.MI_Glass");
	static const TCHAR* MatConcrete = TEXT("/Game/Game/Environment/Home/MI_Concrete.MI_Concrete");
	static const TCHAR* MatGravel = TEXT("/Game/Game/Environment/Home/MI_Gravel.MI_Gravel");
	static const TCHAR* MatBark = TEXT("/Game/Game/Environment/Home/MI_Bark.MI_Bark");
	static const TCHAR* MatNeedles = TEXT("/Game/Game/Environment/Home/MI_Needles.MI_Needles");
	static const TCHAR* MatBrick = TEXT("/Game/Game/Environment/Home/MI_Brick.MI_Brick");

	// ------------------------------------------------------------------
	// Small math helpers (the terrain design language of Phase 4A)
	// ------------------------------------------------------------------
	static float Falloff(float Distance, float Inner, float Outer)
	{
		if (Outer <= Inner)
		{
			return Distance <= Inner ? 1.f : 0.f;
		}
		return 1.f - FMath::SmoothStep(Inner, Outer, Distance);
	}

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

	/** Landscape heightmap value <-> meters (MidValue 32768 == 0 m). */
	static float ValueToHeightM(uint16 Value, float ZScale)
	{
		return (static_cast<float>(Value) - 32768.f) * ZScale / 12800.f;
	}

	static uint16 HeightToValue(float HeightM, float ZScale)
	{
		const float Pixels = 32768.f + (HeightM * 100.f * 128.f) / ZScale;
		return static_cast<uint16>(FMath::Clamp(FMath::RoundToInt(Pixels), 0, 65535));
	}
	// ------------------------------------------------------------------
	// Landscape access (the grid Phase 4A wrote into)
	// ------------------------------------------------------------------
	struct FLandscapeGrid
	{
		ALandscape* Landscape = nullptr;
		ULandscapeInfo* Info = nullptr;
		TArray<ALandscapeProxy*> Proxies;
		int32 VertexMinX = 0;
		int32 VertexMinY = 0;
		int32 VertexMaxX = 0;
		int32 VertexMaxY = 0;
		FVector2D OriginM = FVector2D::ZeroVector;
		float StepM = 1.f;
		float ZScale = 100.f;

		int32 IndexX(float XM) const { return FMath::RoundToInt((XM - OriginM.X) / StepM); }
		int32 IndexY(float YM) const { return FMath::RoundToInt((YM - OriginM.Y) / StepM); }
		FVector2D WorldAt(int32 X, int32 Y) const { return OriginM + FVector2D(X * StepM, Y * StepM); }
		int32 SizeX() const { return VertexMaxX - VertexMinX + 1; }
		int32 SizeY() const { return VertexMaxY - VertexMinY + 1; }
		/** World Z of the landscape actor: stored heightmap meters + this offset = world meters. */
		float ZOffsetM = 0.f;
	};

	static bool ResolveGrid(UWorld* World, FLandscapeGrid& Out)
	{
		for (TActorIterator<ALandscape> It(World); It; ++It)
		{
			Out.Landscape = *It;
			break;
		}
		if (Out.Landscape == nullptr)
		{
			return false;
		}
		Out.Info = Out.Landscape->GetLandscapeInfo();
		if (Out.Info == nullptr)
		{
			return false;
		}
		for (TActorIterator<ALandscapeProxy> It(World); It; ++It)
		{
			ALandscapeProxy* Proxy = *It;
			if (IsValid(Proxy) && (Proxy == Out.Landscape || Proxy->GetLandscapeActor() == Out.Landscape))
			{
				Out.Proxies.Add(Proxy);
			}
		}
		const FTransform Transform = Out.Landscape->GetActorTransform();
		FBox Bounds(ForceInit);
		for (ALandscapeProxy* Proxy : Out.Proxies)
		{
			FVector Origin;
			FVector Extent;
			Proxy->GetActorBounds(false, Origin, Extent);
			Bounds += FBox::BuildAABB(Origin, Extent);
		}
		if (!Bounds.IsValid)
		{
			return false;
		}
		const FVector LocalMin = Transform.InverseTransformPosition(Bounds.Min);
		const FVector LocalMax = Transform.InverseTransformPosition(Bounds.Max);
		Out.VertexMinX = FMath::RoundToInt(LocalMin.X);
		Out.VertexMinY = FMath::RoundToInt(LocalMin.Y);
		Out.VertexMaxX = FMath::RoundToInt(LocalMax.X);
		Out.VertexMaxY = FMath::RoundToInt(LocalMax.Y);
		const FVector WorldAtMin = Transform.TransformPosition(FVector(Out.VertexMinX, Out.VertexMinY, 0)) / 100.f;
		Out.StepM = FMath::Max(0.01f, static_cast<float>(Out.Landscape->GetActorScale3D().X) / 100.f);
		Out.OriginM = FVector2D(WorldAtMin.X, WorldAtMin.Y);
		Out.ZScale = Out.Landscape->GetActorScale3D().Z;
		Out.ZOffsetM = static_cast<float>(Transform.GetTranslation().Z) / 100.f;
		return (Out.VertexMaxX > Out.VertexMinX) && (Out.VertexMaxY > Out.VertexMinY);
	}

	/** Reads the current landscape heights as world meters (bulk read, tight packing). */
	static bool ReadHeightField(const FLandscapeGrid& Grid, TArray<float>& OutMeters)
	{
#if WITH_EDITOR
		const int32 SizeX = Grid.SizeX();
		const int32 SizeY = Grid.SizeY();
		OutMeters.SetNumUninitialized(SizeX * SizeY);
		TArray<uint16> Raw;
		Raw.SetNumUninitialized(SizeX * SizeY);
		{
			FLandscapeEditDataInterface Edit(Grid.Info);
			Edit.GetHeightDataFast(Grid.VertexMinX, Grid.VertexMinY, Grid.VertexMaxX, Grid.VertexMaxY,
				Raw.GetData(), /*Stride=*/0, nullptr, nullptr);
		}
		for (int32 Index = 0; Index < Raw.Num(); ++Index)
		{
			OutMeters[Index] = ValueToHeightM(Raw[Index], Grid.ZScale) + Grid.ZOffsetM;
		}
		return true;
#else
		return false;
#endif
	}

	/** Writes the heights of a vertex rect back into the landscape (bulk edit). */
	static bool WriteHeightField(const FLandscapeGrid& Grid, int32 MinX, int32 MinY, int32 MaxX, int32 MaxY,
	                             const TArray<float>& Meters, float& OutPadHeightM)
	{
#if WITH_EDITOR
		const int32 SizeX = MaxX - MinX + 1;
		const int32 SizeY = MaxY - MinY + 1;
		if (Meters.Num() != SizeX * SizeY)
		{
			return false;
		}
		TArray<uint16> Raw;
		Raw.SetNumUninitialized(Meters.Num());
		for (int32 Index = 0; Index < Meters.Num(); ++Index)
		{
			Raw[Index] = HeightToValue(Meters[Index], Grid.ZScale);
		}
		{
			FLandscapeEditDataInterface Edit(Grid.Info);
			Edit.SetHeightData(MinX, MinY, MaxX, MaxY, Raw.GetData(), /*InStride=*/0, /*InCalcNormals=*/false);
			Edit.Flush();
		}
		Grid.Landscape->ForceLayersFullUpdate();
		OutPadHeightM = 0.f;
		return true;
#else
		return false;
#endif
	}

	static void RefreshCollision(const FLandscapeGrid& Grid)
	{
		for (ALandscapeProxy* Proxy : Grid.Proxies)
		{
			if (IsValid(Proxy))
			{
				Proxy->RecreateCollisionComponents();
				Proxy->MarkPackageDirty();
			}
		}
	}

	/** Ground height (meters) measured through the landscape collision. */
	static bool TraceGround(UWorld* World, const FVector2D& WorldM, float& OutZM)
	{
		FHitResult Hit(ForceInit);
		const FVector Start(WorldM.X * 100.f, WorldM.Y * 100.f, 300000.f);
		const FVector End(WorldM.X * 100.f, WorldM.Y * 100.f, -60000.f);
		FCollisionQueryParams Params(SCENE_QUERY_STAT(Phase4BGround), /*bTraceComplex=*/false);
		bool bHit = World->LineTraceSingleByChannel(Hit, Start, End, ECC_WorldStatic, Params);
		if (!bHit)
		{
			bHit = World->LineTraceSingleByChannel(Hit, Start, End, ECC_Visibility, Params);
		}
		if (!bHit)
		{
			bHit = World->LineTraceSingleByChannel(Hit, Start, End, ECC_WorldDynamic, Params);
		}
		if (!bHit)
		{
			return false;
		}
		OutZM = static_cast<float>(Hit.Location.Z) * 0.01f;
		return true;
	}

#if WITH_EDITOR
	// ------------------------------------------------------------------
	// Procedural mesh building (blockout geometry - no external art assets)
	// ------------------------------------------------------------------
	struct FWallOpening
	{
		float AlongMin = 0.f;
		float AlongMax = 0.f;
		float ZMin = 0.f;
		float ZMax = 0.f;
	};

	/** Planar UV in meters (used by the procedural property materials). */
	static FVector2D PlanarUV(const FVector& P, const FVector& N)
	{
		const FVector Abs(FMath::Abs(N.X), FMath::Abs(N.Y), FMath::Abs(N.Z));
		if (Abs.X >= Abs.Y && Abs.X >= Abs.Z)
		{
			return FVector2D(P.Y, P.Z);
		}
		return (Abs.Y >= Abs.Z) ? FVector2D(P.X, P.Z) : FVector2D(P.X, P.Y);
	}

	struct FMeshBuilder
	{
		FMeshDescription Description;
		FStaticMeshAttributes Attributes;
		TArray<FName> SlotNames;
		TMap<FName, FPolygonGroupID> Groups;
		int32 TriangleCount = 0;

		FMeshBuilder()
			: Attributes(Description)
		{
			Attributes.Register();
		}

		int32 Slot(const FName& SlotName)
		{
			const int32 Existing = SlotNames.IndexOfByKey(SlotName);
			if (Existing != INDEX_NONE)
			{
				return Existing;
			}
			SlotNames.Add(SlotName);
			const FPolygonGroupID Group = Description.CreatePolygonGroup();
			Attributes.GetPolygonGroupMaterialSlotNames()[Group] = SlotName;
			Groups.Add(SlotName, Group);
			return SlotNames.Num() - 1;
		}

		FPolygonGroupID GroupFor(int32 SlotIndex)
		{
			const FName GroupName = SlotNames.IsValidIndex(SlotIndex) ? SlotNames[SlotIndex] : FName(TEXT("Default"));
			FPolygonGroupID* Found = Groups.Find(GroupName);
			if (Found == nullptr)
			{
				Slot(GroupName);
				Found = Groups.Find(GroupName);
			}
			return Found != nullptr ? *Found : FPolygonGroupID(INDEX_NONE);
		}

		void Tri(const FVector& A, const FVector& B, const FVector& C,
		         const FVector2D& UVA, const FVector2D& UVB, const FVector2D& UVC, int32 SlotIndex)
		{
			FVector Normal = FVector::CrossProduct(B - A, C - A);
			if (!Normal.Normalize())
			{
				return;
			}
			const FPolygonGroupID Group = GroupFor(SlotIndex);
			if (Group.GetValue() == INDEX_NONE)
			{
				return;
			}
			FVector Tangent = (B - A).GetSafeNormal();
			if (Tangent.IsNearlyZero())
			{
				Tangent = FVector(1.f, 0.f, 0.f);
			}

			// Positions are authored in metres (spec space); mesh space is centimetres.
			const FVector Positions[3] = { A * 100.f, B * 100.f, C * 100.f };
			const FVector2D UVs[3] = { UVA, UVB, UVC };
			TArray<FVertexInstanceID, TInlineAllocator<3>> Instances;
			for (int32 Corner = 0; Corner < 3; ++Corner)
			{
				const FVertexID Vertex = Description.CreateVertex();
				Attributes.GetVertexPositions()[Vertex] = FVector3f(Positions[Corner]);
				const FVertexInstanceID Instance = Description.CreateVertexInstance(Vertex);
				Attributes.GetVertexInstanceNormals()[Instance] = FVector3f(Normal);
				Attributes.GetVertexInstanceTangents()[Instance] = FVector3f(Tangent);
				Attributes.GetVertexInstanceBinormalSigns()[Instance] = 1.f;
				Attributes.GetVertexInstanceUVs()[Instance] = FVector2f(UVs[Corner]);
				Instances.Add(Instance);
			}
			Description.CreatePolygon(Group, Instances);
			++TriangleCount;
		}

		void TriAuto(const FVector& A, const FVector& B, const FVector& C, int32 SlotIndex)
		{
			FVector Normal = FVector::CrossProduct(B - A, C - A);
			Normal.Normalize();
			Tri(A, B, C, PlanarUV(A, Normal), PlanarUV(B, Normal), PlanarUV(C, Normal), SlotIndex);
		}

		void Quad(const FVector& A, const FVector& B, const FVector& C, const FVector& D, int32 SlotIndex)
		{
			TriAuto(A, B, C, SlotIndex);
			TriAuto(A, C, D, SlotIndex);
		}
		/** Axis aligned box (optionally rotated) with automatic planar UVs. */
		void Box(const FVector& Center, const FVector& HalfSize, int32 SlotIndex,
		         const FRotator& Rot = FRotator::ZeroRotator, bool bSkipBottom = false)
		{
			const FTransform Xf(Rot, Center);
			auto Corner = [&Xf, &HalfSize](float SX, float SY, float SZ)
			{
				return Xf.TransformPosition(FVector(SX * HalfSize.X, SY * HalfSize.Y, SZ * HalfSize.Z));
			};
			const FVector P000 = Corner(-1.f, -1.f, -1.f);
			const FVector P100 = Corner(1.f, -1.f, -1.f);
			const FVector P110 = Corner(1.f, 1.f, -1.f);
			const FVector P010 = Corner(-1.f, 1.f, -1.f);
			const FVector P001 = Corner(-1.f, -1.f, 1.f);
			const FVector P101 = Corner(1.f, -1.f, 1.f);
			const FVector P111 = Corner(1.f, 1.f, 1.f);
			const FVector P011 = Corner(-1.f, 1.f, 1.f);

			Quad(P001, P101, P111, P011, SlotIndex);   // +Z
			if (!bSkipBottom)
			{
				Quad(P000, P010, P110, P100, SlotIndex);   // -Z
			}
			Quad(P100, P110, P111, P101, SlotIndex);   // +X
			Quad(P000, P001, P011, P010, SlotIndex);   // -X
			Quad(P010, P011, P111, P110, SlotIndex);   // +Y
			Quad(P000, P100, P101, P001, SlotIndex);   // -Y
		}

		/**
		 * Extrudes a convex cross section (given in the local YZ plane, counter clockwise)
		 * along the local X axis: used for gable roofs and mono pitch roofs.
		 */
		void ExtrudeProfile(const TArray<FVector2D>& CrossSectionYZ, float XMin, float XMax,
		                    const FTransform& Xf, int32 SlotIndex)
		{
			if (CrossSectionYZ.Num() < 3)
			{
				return;
			}
			auto At = [&Xf](float X, const FVector2D& YZ)
			{
				return Xf.TransformPosition(FVector(X, YZ.X, YZ.Y));
			};
			const FVector2D First = CrossSectionYZ[0];
			for (int32 Index = 1; Index + 1 < CrossSectionYZ.Num(); ++Index)
			{
				TriAuto(At(XMax, First), At(XMax, CrossSectionYZ[Index]), At(XMax, CrossSectionYZ[Index + 1]), SlotIndex);
				TriAuto(At(XMin, First), At(XMin, CrossSectionYZ[Index + 1]), At(XMin, CrossSectionYZ[Index]), SlotIndex);
			}
			for (int32 Index = 0; Index < CrossSectionYZ.Num(); ++Index)
			{
				const int32 Next = (Index + 1) % CrossSectionYZ.Num();
				Quad(At(XMin, CrossSectionYZ[Index]), At(XMin, CrossSectionYZ[Next]),
					At(XMax, CrossSectionYZ[Next]), At(XMax, CrossSectionYZ[Index]), SlotIndex);
			}
		}
		/** Slab from four (possibly irregular) corners: top surface + sides. */
		void Slab(const FVector2D& P00, const FVector2D& P10, const FVector2D& P11, const FVector2D& P01,
		          float TopZ, float Thickness, int32 SlotIndex)
		{
			const FVector2D Corners[4] = { P00, P10, P11, P01 };
			auto At = [](const FVector2D& P, float Z) { return FVector(P.X, P.Y, Z); };
			Quad(At(P00, TopZ), At(P10, TopZ), At(P11, TopZ), At(P01, TopZ), SlotIndex);
			const float BottomZ = TopZ - Thickness;
			for (int32 Index = 0; Index < 4; ++Index)
			{
				const FVector2D& Current = Corners[Index];
				const FVector2D& Next = Corners[(Index + 1) % 4];
				Quad(At(Next, TopZ), At(Current, TopZ), At(Current, BottomZ), At(Next, BottomZ), SlotIndex);
			}
		}

		/** Tapered cylinder / cone between two points (trunks and the pine canopy tiers). */
		void Cylinder(const FVector& Base, const FVector& Top, float RadiusBase, float RadiusTop,
		              int32 Segments, int32 SlotIndex, float Jitter = 0.f, int32 Seed = 0)
		{
			Segments = FMath::Clamp(Segments, 3, 64);
			const FVector Axis = Top - Base;
			const float Height = Axis.Size();
			if (Height <= KINDA_SMALL_NUMBER || RadiusBase <= 0.001f)
			{
				return;
			}
			const FVector AxisDir = Axis / Height;
			const FVector Ref = (FMath::Abs(AxisDir.Z) < 0.9f) ? FVector::UpVector : FVector::ForwardVector;
			const FVector Side = FVector::CrossProduct(AxisDir, Ref).GetSafeNormal();
			const FVector Side2 = FVector::CrossProduct(AxisDir, Side).GetSafeNormal();

			FRandomStream Rng(Seed);
			TArray<FVector> BaseRing;
			TArray<FVector> TopRing;
			BaseRing.Reserve(Segments);
			TopRing.Reserve(Segments);
			for (int32 Index = 0; Index < Segments; ++Index)
			{
				const float Angle = 2.f * PI * Index / static_cast<float>(Segments);
				const float Wobble = (Jitter > 0.f) ? (1.f + Rng.FRandRange(-Jitter, Jitter)) : 1.f;
				const FVector Radial = (Side * FMath::Cos(Angle) + Side2 * FMath::Sin(Angle)) * Wobble;
				BaseRing.Add(Base + Radial * RadiusBase);
				TopRing.Add(Top + Radial * RadiusTop);
			}
			for (int32 Index = 0; Index < Segments; ++Index)
			{
				const int32 Next = (Index + 1) % Segments;
				Quad(BaseRing[Index], BaseRing[Next], TopRing[Next], TopRing[Index], SlotIndex);
			}
			for (int32 Index = 1; Index + 1 < Segments; ++Index)
			{
				TriAuto(Top, TopRing[Index], TopRing[Index + 1], SlotIndex);
				TriAuto(Base, BaseRing[Index + 1], BaseRing[Index], SlotIndex);
			}
		}

		/**
		 * Straight wall with real rectangular openings (windows / doors can sit inside
		 * them). The wall is built from solid panels around the openings, thickness is
		 * centered on the A->B line. Openings use along-wall / height coordinates.
		 */
		void Wall(const FVector2D& A, const FVector2D& B, float ZBase, float ZTop, float Thickness,
		          const TArray<FWallOpening>& Openings, int32 SlotIndex)
		{
			const FVector2D Axis2D = B - A;
			const float Length = Axis2D.Size();
			if (Length <= KINDA_SMALL_NUMBER || ZTop <= ZBase)
			{
				return;
			}
			const FVector2D Dir = Axis2D / Length;
			const float YawDeg = FMath::RadiansToDegrees(FMath::Atan2(Dir.Y, Dir.X));

			TArray<float> Xs;
			TArray<float> Zs;
			Xs.Add(0.f);
			Xs.Add(Length);
			Zs.Add(ZBase);
			Zs.Add(ZTop);
			for (const FWallOpening& Opening : Openings)
			{
				Xs.Add(FMath::Clamp(Opening.AlongMin, 0.f, Length));
				Xs.Add(FMath::Clamp(Opening.AlongMax, 0.f, Length));
				Zs.Add(FMath::Clamp(Opening.ZMin, ZBase, ZTop));
				Zs.Add(FMath::Clamp(Opening.ZMax, ZBase, ZTop));
			}
			Xs.Sort();
			Zs.Sort();

			for (int32 Xi = 0; Xi + 1 < Xs.Num(); ++Xi)
			{
				const float AlongMin = Xs[Xi];
				const float AlongMax = Xs[Xi + 1];
				const float Width = AlongMax - AlongMin;
				if (Width <= 0.02f)
				{
					continue;
				}
				for (int32 Zi = 0; Zi + 1 < Zs.Num(); ++Zi)
				{
					const float HeightMin = Zs[Zi];
					const float HeightMax = Zs[Zi + 1];
					const float Height = HeightMax - HeightMin;
					if (Height <= 0.02f)
					{
						continue;
					}
					const float CenterAlong = (AlongMin + AlongMax) * 0.5f;
					const float CenterZ = (HeightMin + HeightMax) * 0.5f;
					bool bInside = false;
					for (const FWallOpening& Opening : Openings)
					{
						if (CenterAlong > Opening.AlongMin && CenterAlong < Opening.AlongMax &&
							CenterZ > Opening.ZMin && CenterZ < Opening.ZMax)
						{
							bInside = true;
							break;
						}
					}
					if (bInside)
					{
						continue;
					}
					const FVector2D Center2D = A + Dir * CenterAlong;
					Box(FVector(Center2D.X, Center2D.Y, CenterZ),
						FVector(Width * 0.5f, Thickness * 0.5f, Height * 0.5f), SlotIndex, FRotator(0.f, YawDeg, 0.f));
				}
			}
		}
		/**
		 * Window / door unit that sits inside a wall opening: a frame all around, a
		 * recessed panel (glass/muntins for windows, planks/metal for doors) and a sill
		 * for windows. Opening coordinates match FMeshBuilder::Wall.
		 */
		void OpeningUnit(const FVector2D& A, const FVector2D& B, float ZBase, float Thickness,
		                 const FWallOpening& Opening, int32 FrameSlot, int32 PanelSlot, int32 TrimSlot,
		                 float PanelInset, float FrameSize, bool bWindow)
		{
			const FVector2D Axis2D = B - A;
			const float Length = Axis2D.Size();
			if (Length <= KINDA_SMALL_NUMBER)
			{
				return;
			}
			const FVector2D Dir = Axis2D / Length;
			const FVector2D Side(-Dir.Y, Dir.X);
			const float YawDeg = FMath::RadiansToDegrees(FMath::Atan2(Dir.Y, Dir.X));
			const FRotator Rot(0.f, YawDeg, 0.f);
			const float CenterAlong = (Opening.AlongMin + Opening.AlongMax) * 0.5f;
			const float Width = Opening.AlongMax - Opening.AlongMin;
			const float Height = Opening.ZMax - Opening.ZMin;
			const float MidZ = (Opening.ZMin + Opening.ZMax) * 0.5f;
			const float FrameHalf = FrameSize * 0.5f;
			const float FrameDepth = Thickness * 0.5f + 0.03f;

			auto Place = [&A, &Dir, &Side](float Along, float Offset)
			{
				const FVector2D P = A + Dir * Along + Side * Offset;
				return FVector2D(P.X, P.Y);
			};

			// Recessed panel (glass / door leaf).
			{
				const FVector2D Center = Place(CenterAlong, -PanelInset);
				Box(FVector(Center.X, Center.Y, MidZ),
					FVector(FMath::Max(0.02f, Width * 0.5f - FrameSize), 0.022f,
						FMath::Max(0.02f, Height * 0.5f - FrameSize)), PanelSlot, Rot);
			}

			// Frame bars.
			const FVector2D Offset(0.f, 0.f);
			{
				const FVector2D Left = Place(Opening.AlongMin + FrameHalf, Offset.Y);
				const FVector2D Right = Place(Opening.AlongMax - FrameHalf, Offset.Y);
				const FVector2D Top = Place(CenterAlong, Offset.Y);
				const FVector2D Bottom = Place(CenterAlong, Offset.Y);
				Box(FVector(Left.X, Left.Y, MidZ), FVector(FrameHalf, FrameDepth, Height * 0.5f), FrameSlot, Rot);
				Box(FVector(Right.X, Right.Y, MidZ), FVector(FrameHalf, FrameDepth, Height * 0.5f), FrameSlot, Rot);
				Box(FVector(Top.X, Top.Y, Opening.ZMax - FrameHalf), FVector(Width * 0.5f, FrameDepth, FrameHalf), FrameSlot, Rot);
				Box(FVector(Bottom.X, Bottom.Y, Opening.ZMin + FrameHalf), FVector(Width * 0.5f, FrameDepth, FrameHalf), FrameSlot, Rot);
			}

			if (bWindow)
			{
				// Sill and simple cross muntins.
				const FVector2D Sill = Place(CenterAlong, 0.f);
				Box(FVector(Sill.X, Sill.Y, Opening.ZMin + 0.05f),
					FVector(Width * 0.5f + 0.12f, Thickness * 0.5f + 0.16f, 0.05f), TrimSlot, Rot);
				const FVector2D Muntin = Place(CenterAlong, -PanelInset - 0.02f);
				Box(FVector(Muntin.X, Muntin.Y, MidZ), FVector(0.03f, 0.03f, Height * 0.5f - FrameSize), TrimSlot, Rot);
				Box(FVector(Muntin.X, Muntin.Y, MidZ), FVector(Width * 0.5f - FrameSize, 0.03f, 0.03f), TrimSlot, Rot);
			}
		}
	};

	// ------------------------------------------------------------------
	// Asset creation
	// ------------------------------------------------------------------
	struct FMaterialSet
	{
		TMap<FName, UMaterialInterface*> BySlot;
		TArray<FString> Missing;

		void Load(const TCHAR* Path, const TCHAR* SlotName)
		{
			UMaterialInterface* Material = LoadObject<UMaterialInterface>(nullptr, Path);
			if (Material == nullptr)
			{
				Missing.Add(FString(SlotName));
			}
			BySlot.Add(FName(SlotName), Material);
		}

		UMaterialInterface* Get(const FName& SlotName) const
		{
			UMaterialInterface* const* Found = BySlot.Find(SlotName);
			return Found != nullptr ? *Found : nullptr;
		}
	};

	static FMaterialSet LoadPropertyMaterials()
	{
		FMaterialSet Set;
		Set.Load(MatPlaster, TEXT("MI_Plaster"));
		Set.Load(MatRoofTile, TEXT("MI_RoofTile"));
		Set.Load(MatWoodTrim, TEXT("MI_WoodTrim"));
		Set.Load(MatWoodPlank, TEXT("MI_WoodPlank"));
		Set.Load(MatMetal, TEXT("MI_MetalDoor"));
		Set.Load(MatGlass, TEXT("MI_Glass"));
		Set.Load(MatConcrete, TEXT("MI_Concrete"));
		Set.Load(MatGravel, TEXT("MI_Gravel"));
		Set.Load(MatBark, TEXT("MI_Bark"));
		Set.Load(MatNeedles, TEXT("MI_Needles"));
		Set.Load(MatBrick, TEXT("MI_Brick"));
		return Set;
	}

	/** Creates (or replaces) a static mesh asset from a mesh description. */
	static UStaticMesh* CreateStaticMeshAsset(const FString& AssetName, FMeshBuilder& Builder,
	                                          const FMaterialSet& Materials, bool bSimpleCollision,
	                                          float CollisionTopM, TArray<FString>& OutWarnings)
	{
		const FString ObjectPath = FString::Printf(TEXT("%s/%s.%s"), *AssetDir, *AssetName, *AssetName);
		if (UObject* Existing = LoadObject<UObject>(nullptr, *ObjectPath))
		{
			Existing->ClearFlags(RF_Public | RF_Standalone);
			Existing->Rename(nullptr, GetTransientPackage(), REN_DontCreateRedirectors);
		}

		UPackage* Package = CreatePackage(*FString::Printf(TEXT("%s/%s"), *AssetDir, *AssetName));
		if (Package == nullptr)
		{
			OutWarnings.Add(FString::Printf(TEXT("could not create package for %s"), *AssetName));
			return nullptr;
		}
		Package->FullyLoad();

		UStaticMesh* Mesh = NewObject<UStaticMesh>(Package, FName(*AssetName), RF_Public | RF_Standalone);
		if (Mesh == nullptr)
		{
			OutWarnings.Add(FString::Printf(TEXT("could not create %s"), *AssetName));
			return nullptr;
		}

		for (const FName& SlotName : Builder.SlotNames)
		{
			UMaterialInterface* Material = Materials.Get(SlotName);
			Mesh->GetStaticMaterials().Add(FStaticMaterial(Material, SlotName, SlotName));
		}

		UStaticMesh::FBuildMeshDescriptionsParams Params;
		Params.bMarkPackageDirty = true;
		Params.bBuildSimpleCollision = bSimpleCollision;
		Params.bCommitMeshDescription = true;
		Params.bFastBuild = false;
		if (!Mesh->BuildFromMeshDescriptions({ &Builder.Description }, Params))
		{
			OutWarnings.Add(FString::Printf(TEXT("BuildFromMeshDescriptions failed for %s"), *AssetName));
			return nullptr;
		}

		// A mesh built from a mesh description gets no simple collision from the build itself,
		// so add a convex hull over the whole mesh: placed walls block the player and the
		// instanced tree trunks collide as well (instanced meshes only use simple shapes).
		UBodySetup* Body = Mesh->GetBodySetup();
		if (Body == nullptr)
		{
			Mesh->CreateBodySetup();
			Body = Mesh->GetBodySetup();
		}
		if (Body != nullptr)
		{
			if (bSimpleCollision)
			{
				TArray<FVector> Points;
				const TVertexAttributesConstRef<FVector3f> Positions =
					Builder.Description.VertexAttributes().GetAttributesRef<FVector3f>(MeshAttribute::Vertex::Position);
				for (const FVertexID VertexID : Builder.Description.Vertices().GetElementIDs())
				{
					// CollisionTopM (when > 0) drops everything above the walkable surface,
					// so decks and paving get a flat hull instead of one over their roofs.
					const FVector Position(Positions[VertexID]);
					if (CollisionTopM <= 0.f || Position.Z <= CollisionTopM * 100.f)
					{
						Points.Add(Position);
					}
				}
				if (Points.Num() >= 4)
				{
					FKConvexElem& Hull = Body->AggGeom.ConvexElems.AddDefaulted_GetRef();
					Hull.VertexData = Points;
					// The hull itself is cooked by CreatePhysicsMeshes() from VertexData.
					Hull.UpdateElemBox();
				}
				Body->CollisionTraceFlag = ECollisionTraceFlag::CTF_UseSimpleAndComplex;
			}
			else
			{
				Body->CollisionTraceFlag = ECollisionTraceFlag::CTF_UseSimpleAsComplex;
			}
			Body->InvalidatePhysicsData();
			Body->CreatePhysicsMeshes();
		}
		Mesh->MarkPackageDirty();
		Mesh->PostEditChange();
		Mesh->MarkPackageDirty();

		const FString FileName = FPackageName::LongPackageNameToFilename(
			Package->GetName(), FPackageName::GetAssetPackageExtension());
		FSavePackageArgs SaveArgs;
		SaveArgs.TopLevelFlags = RF_Public | RF_Standalone;
		SaveArgs.SaveFlags = SAVE_NoError;
		UPackage::SavePackage(Package, Mesh, *FileName, SaveArgs);

		FAssetRegistryModule::AssetCreated(Mesh);
		return Mesh;
	}
	// ------------------------------------------------------------------
	// Property geometry (all meshes are built in a local frame where
	// z = 0 is the terrain pad surface and XY are world meters)
	// ------------------------------------------------------------------
	static void BuildHouseMesh(FMeshBuilder& B, const FPhase4BHomeSpec& Spec)
	{
		const int32 SPlaster = B.Slot(TEXT("MI_Plaster"));
		const int32 SRoof = B.Slot(TEXT("MI_RoofTile"));
		const int32 STrim = B.Slot(TEXT("MI_WoodTrim"));
		const int32 SGlass = B.Slot(TEXT("MI_Glass"));
		const int32 SPlank = B.Slot(TEXT("MI_WoodPlank"));
		const int32 SConcrete = B.Slot(TEXT("MI_Concrete"));

		const float HL = Spec.HouseLengthX;
		const float HW = Spec.HouseWidthY;
		const float WallT = 0.32f;
		const float FloorZ = Spec.FoundationHeight;
		const float EaveZ = FloorZ + Spec.HouseWallHeight;
		const float RidgeZ = EaveZ + Spec.HouseRoofRise;
		const FVector2D C = Spec.HouseCenter;
		const float XMin = C.X - HL * 0.5f;
		const float XMax = C.X + HL * 0.5f;
		const float YMin = C.Y - HW * 0.5f;
		const float YMax = C.Y + HW * 0.5f;

		// Foundation / plinth and the interior floor.
		B.Box(FVector(C.X, C.Y, (FloorZ - 0.25f) * 0.5f), FVector(HL * 0.5f + 0.25f, HW * 0.5f + 0.25f, (FloorZ + 0.25f) * 0.5f), SConcrete);
		B.Box(FVector(C.X, C.Y, FloorZ - 0.06f), FVector(HL * 0.5f - WallT, HW * 0.5f - WallT, 0.06f), SPlank);

		// Walls with real openings (front door, rear door, five windows).
		const float WinZ0 = FloorZ + 0.95f;
		const float WinZ1 = FloorZ + 2.25f;
		auto MakeOpening = [](float CenterAlong, float Width, float ZMin, float ZMax)
		{
			FWallOpening Opening;
			Opening.AlongMin = CenterAlong - Width * 0.5f;
			Opening.AlongMax = CenterAlong + Width * 0.5f;
			Opening.ZMin = ZMin;
			Opening.ZMax = ZMax;
			return Opening;
		};

		// South wall (front, faces the yard).
		{
			const FVector2D A(XMin, YMin);
			const FVector2D Bp(XMax, YMin);
			const FWallOpening Door = MakeOpening((C.X - 1.7f) - XMin, 1.05f, FloorZ, FloorZ + 2.10f);
			const FWallOpening W1 = MakeOpening((C.X - 4.0f) - XMin, 1.25f, WinZ0, WinZ1);
			const FWallOpening W2 = MakeOpening((C.X + 1.4f) - XMin, 1.25f, WinZ0, WinZ1);
			B.Wall(A, Bp, FloorZ, EaveZ, WallT, { Door, W1, W2 }, SPlaster);
			B.OpeningUnit(A, Bp, FloorZ, WallT, Door, STrim, SPlank, STrim, 0.10f, 0.07f, false);
			B.OpeningUnit(A, Bp, FloorZ, WallT, W1, STrim, SGlass, STrim, 0.12f, 0.07f, true);
			B.OpeningUnit(A, Bp, FloorZ, WallT, W2, STrim, SGlass, STrim, 0.12f, 0.07f, true);
		}
		// North wall (back, faces the veranda).
		{
			const FVector2D A(XMax, YMax);
			const FVector2D Bp(XMin, YMax);
			const FWallOpening Door = MakeOpening(XMax - (C.X + 1.5f), 1.00f, FloorZ, FloorZ + 2.05f);
			const FWallOpening W = MakeOpening(XMax - (C.X - 3.2f), 1.25f, WinZ0, WinZ1);
			B.Wall(A, Bp, FloorZ, EaveZ, WallT, { Door, W }, SPlaster);
			B.OpeningUnit(A, Bp, FloorZ, WallT, Door, STrim, SPlank, STrim, 0.10f, 0.07f, false);
			B.OpeningUnit(A, Bp, FloorZ, WallT, W, STrim, SGlass, STrim, 0.12f, 0.07f, true);
		}
		// East wall.
		{
			const FVector2D A(XMax, YMin);
			const FVector2D Bp(XMax, YMax);
			const FWallOpening W = MakeOpening(C.Y - YMin, 1.25f, WinZ0, WinZ1);
			B.Wall(A, Bp, FloorZ, EaveZ, WallT, { W }, SPlaster);
			B.OpeningUnit(A, Bp, FloorZ, WallT, W, STrim, SGlass, STrim, 0.12f, 0.07f, true);
		}
		// West wall.
		{
			const FVector2D A(XMin, YMax);
			const FVector2D Bp(XMin, YMin);
			const FWallOpening W = MakeOpening(YMax - C.Y, 1.00f, FloorZ + 1.05f, FloorZ + 2.25f);
			B.Wall(A, Bp, FloorZ, EaveZ, WallT, { W }, SPlaster);
			B.OpeningUnit(A, Bp, FloorZ, WallT, W, STrim, SGlass, STrim, 0.12f, 0.07f, true);
		}

		// Gable roof (ridge along X, eaves with overhang).
		{
			const float HalfSpan = HW * 0.5f + Spec.EaveOverhang;
			const float EaveZ2 = EaveZ - 0.05f;
			const TArray<FVector2D> Section = {
				FVector2D(C.Y + HalfSpan, EaveZ2),
				FVector2D(C.Y, RidgeZ),
				FVector2D(C.Y - HalfSpan, EaveZ2)
			};
			B.ExtrudeProfile(Section, XMin - Spec.GableOverhang, XMax + Spec.GableOverhang, FTransform::Identity, SRoof);
			// Ridge cap and chimney.
			B.Box(FVector(C.X, C.Y, RidgeZ + 0.06f), FVector(HL * 0.5f + Spec.GableOverhang, 0.14f, 0.07f), SRoof);
			B.Box(FVector(C.X + 2.2f, C.Y - 0.7f, (EaveZ2 + RidgeZ + 1.05f) * 0.5f),
				FVector(0.31f, 0.31f, (RidgeZ + 1.05f - EaveZ2) * 0.5f), B.Slot(TEXT("MI_Brick")));
			B.Box(FVector(C.X + 2.2f, C.Y - 0.7f, RidgeZ + 1.12f), FVector(0.39f, 0.39f, 0.06f), SConcrete);
		}
	}
	/** Veranda (covered rear porch) + the open outdoor living area behind the house. */
	static void BuildVerandaMesh(FMeshBuilder& B, const FPhase4BHomeSpec& Spec)
	{
		const int32 SConcrete = B.Slot(TEXT("MI_Concrete"));
		const int32 STrim = B.Slot(TEXT("MI_WoodTrim"));
		const int32 SRoof = B.Slot(TEXT("MI_RoofTile"));

		const float HL = Spec.HouseLengthX;
		const float FloorZ = Spec.FoundationHeight;
		const float VerandaTop = FloorZ - 0.05f;
		const float ApronTop = FloorZ - 0.21f;
		const FVector2D C = Spec.HouseCenter;
		const float XMin = C.X - HL * 0.5f;
		const float XMax = C.X + HL * 0.5f;
		const float CenterX = (XMin + XMax) * 0.5f;
		const float Y0 = C.Y + Spec.HouseWidthY * 0.5f;
		const float Y1 = Y0 + Spec.VerandaDepthY;
		const float Y2 = Y1 + Spec.VerandaApronDepthY;

		// Covered veranda floor, the open apron behind it and steps down to the apron.
		B.Box(FVector(CenterX, (Y0 + Y1) * 0.5f, VerandaTop - 0.14f),
			FVector(HL * 0.5f, Spec.VerandaDepthY * 0.5f, 0.14f), SConcrete);
		B.Box(FVector(CenterX, (Y1 + Y2) * 0.5f, ApronTop - 0.16f),
			FVector(HL * 0.5f, Spec.VerandaApronDepthY * 0.5f, 0.16f), SConcrete);
		B.Box(FVector(CenterX - 2.6f, Y1 + 0.34f, VerandaTop - 0.19f),
			FVector(2.0f, 0.34f, 0.19f), SConcrete);
		B.Box(FVector(CenterX + 2.6f, Y1 + 0.34f, VerandaTop - 0.19f),
			FVector(2.0f, 0.34f, 0.19f), SConcrete);

		// Posts.
		const float PostY = Y1 - 0.22f;
		for (int32 Index = 0; Index < 4; ++Index)
		{
			const float X = XMin + 0.45f + (HL - 0.9f) * Index / 3.f;
			B.Box(FVector(X, PostY, VerandaTop + 1.30f), FVector(0.09f, 0.09f, 1.30f), STrim);
		}

		// Railing (rails + balusters) along the open side.
		B.Box(FVector(CenterX, PostY, VerandaTop + 0.99f), FVector(HL * 0.5f - 0.2f, 0.055f, 0.055f), STrim);
		B.Box(FVector(CenterX, PostY, VerandaTop + 0.22f), FVector(HL * 0.5f - 0.2f, 0.045f, 0.045f), STrim);
		const int32 Balusters = 20;
		for (int32 Index = 1; Index < Balusters; ++Index)
		{
			const float X = XMin + 0.25f + (HL - 0.5f) * Index / static_cast<float>(Balusters);
			B.Box(FVector(X, PostY, VerandaTop + 0.60f), FVector(0.033f, 0.033f, 0.37f), STrim);
		}

		// Lean-to veranda roof, tilted down away from the house.
		const float RoofWidth = Spec.VerandaDepthY + 0.8f;
		const float RoofPitch = -10.f;
		const float RoofCenterY = (Y0 - 0.20f + Y1 + 0.60f) * 0.5f;
		const float HouseEndZ = FloorZ + Spec.HouseWallHeight - 0.22f;
		const float RoofCenterZ = HouseEndZ - FMath::Tan(FMath::DegreesToRadians(-RoofPitch)) * RoofWidth * 0.5f;
		B.Box(FVector(CenterX, RoofCenterY, RoofCenterZ), FVector(HL * 0.5f + 0.30f, RoofWidth * 0.5f, 0.075f),
			SRoof, FRotator(RoofPitch, 0.f, 0.f));
	}
	/** Detached garage: gable roof and one vehicle door facing the concrete yard. */
	static void BuildGarageMesh(FMeshBuilder& B, const FPhase4BHomeSpec& Spec)
	{
		const int32 SPlaster = B.Slot(TEXT("MI_Plaster"));
		const int32 SRoof = B.Slot(TEXT("MI_RoofTile"));
		const int32 SMetal = B.Slot(TEXT("MI_MetalDoor"));
		const int32 SGlass = B.Slot(TEXT("MI_Glass"));
		const int32 SConcrete = B.Slot(TEXT("MI_Concrete"));
		const int32 STrim = B.Slot(TEXT("MI_WoodTrim"));

		const float GW = Spec.GarageWidthX;
		const float GD = Spec.GarageDepthY;
		const float WallT = 0.30f;
		const float FloorZ = Spec.YardTopOffsetM + 0.06f;
		const float EaveZ = FloorZ + Spec.GarageWallHeight;
		const float RidgeZ = EaveZ + Spec.GarageRoofRise;
		const FVector2D C = Spec.GarageCenter;
		const float XMin = C.X - GW * 0.5f;
		const float XMax = C.X + GW * 0.5f;
		const float YMin = C.Y - GD * 0.5f;
		const float YMax = C.Y + GD * 0.5f;

		auto Opening = [](float AlongMin, float AlongMax, float ZMin, float ZMax)
		{
			FWallOpening Result;
			Result.AlongMin = AlongMin;
			Result.AlongMax = AlongMax;
			Result.ZMin = ZMin;
			Result.ZMax = ZMax;
			return Result;
		};

		B.Box(FVector(C.X, C.Y, FloorZ - 0.16f), FVector(GW * 0.5f + 0.22f, GD * 0.5f + 0.22f, 0.16f), SConcrete);

		// North wall (yard side) carries the vehicle door.
		{
			const FVector2D A(XMax, YMax);
			const FVector2D Bp(XMin, YMax);
			const float Center = XMax - C.X;
			const FWallOpening Door = Opening(Center - Spec.GarageDoorWidth * 0.5f,
				Center + Spec.GarageDoorWidth * 0.5f, FloorZ, FloorZ + Spec.GarageDoorHeight);
			B.Wall(A, Bp, FloorZ, EaveZ, WallT, { Door }, SPlaster);
		}
		// South wall (back) and west wall.
		B.Wall(FVector2D(XMin, YMin), FVector2D(XMax, YMin), FloorZ, EaveZ, WallT, {}, SPlaster);
		B.Wall(FVector2D(XMin, YMax), FVector2D(XMin, YMin), FloorZ, EaveZ, WallT, {}, SPlaster);
		// East wall with a small workshop window.
		{
			const FVector2D A(XMax, YMin);
			const FVector2D Bp(XMax, YMax);
			const float Center = C.Y - YMin;
			const FWallOpening Window = Opening(Center - 0.45f, Center + 0.45f, FloorZ + 1.25f, FloorZ + 2.15f);
			B.Wall(A, Bp, FloorZ, EaveZ, WallT, { Window }, SPlaster);
			B.OpeningUnit(A, Bp, FloorZ, WallT, Window, STrim, SGlass, STrim, 0.12f, 0.07f, true);
		}

		// Gable roof.
		{
			const float HalfSpan = GD * 0.5f + 0.50f;
			const float EaveZ2 = EaveZ - 0.05f;
			const TArray<FVector2D> Section = {
				FVector2D(C.Y + HalfSpan, EaveZ2),
				FVector2D(C.Y, RidgeZ),
				FVector2D(C.Y - HalfSpan, EaveZ2)
			};
			B.ExtrudeProfile(Section, XMin - 0.40f, XMax + 0.40f, FTransform::Identity, SRoof);
			B.Box(FVector(C.X, C.Y, RidgeZ + 0.05f), FVector(GW * 0.5f + 0.4f, 0.13f, 0.06f), SRoof);
		}

		// Ribbed metal vehicle door (closed) with its frame.
		{
			const float DoorW = Spec.GarageDoorWidth;
			const float DoorH = Spec.GarageDoorHeight;
			const float DoorY = YMax - WallT * 0.5f;
			B.Box(FVector(C.X, DoorY - 0.10f, FloorZ + DoorH * 0.5f),
				FVector(DoorW * 0.5f - 0.02f, 0.035f, DoorH * 0.5f - 0.02f), SMetal);
			for (int32 Index = 0; Index < 5; ++Index)
			{
				const float Z = FloorZ + DoorH * (Index + 1) / 6.f;
				B.Box(FVector(C.X, DoorY - 0.15f, Z), FVector(DoorW * 0.5f - 0.06f, 0.045f, 0.045f), SMetal);
			}
			B.Box(FVector(C.X - DoorW * 0.5f - 0.06f, DoorY, FloorZ + DoorH * 0.5f),
				FVector(0.06f, WallT * 0.5f + 0.05f, DoorH * 0.5f + 0.06f), STrim);
			B.Box(FVector(C.X + DoorW * 0.5f + 0.06f, DoorY, FloorZ + DoorH * 0.5f),
				FVector(0.06f, WallT * 0.5f + 0.05f, DoorH * 0.5f + 0.06f), STrim);
			B.Box(FVector(C.X, DoorY, FloorZ + DoorH + 0.06f),
				FVector(DoorW * 0.5f + 0.12f, WallT * 0.5f + 0.05f, 0.06f), STrim);
		}
	}
	/** Old improvised shed / small workshop: plank walls, mono pitch metal roof, wide door. */
	static void BuildShedMesh(FMeshBuilder& B, const FPhase4BHomeSpec& Spec)
	{
		const int32 SPlank = B.Slot(TEXT("MI_WoodPlank"));
		const int32 SMetal = B.Slot(TEXT("MI_MetalDoor"));
		const int32 STrim = B.Slot(TEXT("MI_WoodTrim"));
		const int32 SGlass = B.Slot(TEXT("MI_Glass"));
		const int32 SConcrete = B.Slot(TEXT("MI_Concrete"));

		const float SW = Spec.ShedWidthX;
		const float SD = Spec.ShedDepthY;
		const float WallT = 0.22f;
		const float FloorZ = 0.12f;
		const float LowZ = FloorZ + Spec.ShedWallHeightLow;
		const float HighZ = FloorZ + Spec.ShedWallHeightHigh;
		const FVector2D C = Spec.ShedCenter;
		const float XMin = C.X - SW * 0.5f;
		const float XMax = C.X + SW * 0.5f;
		const float YMin = C.Y - SD * 0.5f;
		const float YMax = C.Y + SD * 0.5f;

		auto Opening = [](float AlongMin, float AlongMax, float ZMin, float ZMax)
		{
			FWallOpening Result;
			Result.AlongMin = AlongMin;
			Result.AlongMax = AlongMax;
			Result.ZMin = ZMin;
			Result.ZMax = ZMax;
			return Result;
		};

		// Floor and the three plain walls (the mono pitch roof slopes towards the north).
		B.Box(FVector(C.X, C.Y, FloorZ - 0.16f), FVector(SW * 0.5f + 0.15f, SD * 0.5f + 0.15f, 0.16f), SConcrete);
		B.Wall(FVector2D(XMin, YMin), FVector2D(XMax, YMin), FloorZ, LowZ, WallT, {}, SPlank);   // north (low)
		B.Wall(FVector2D(XMin, YMax), FVector2D(XMin, YMin), FloorZ, LowZ, WallT, {}, SPlank);   // west
		// South wall (high side) with a small workshop window.
		{
			const FVector2D A(XMin, YMax);
			const FVector2D Bp(XMax, YMax);
			const float Center = (C.X - 1.6f) - XMin;
			const FWallOpening Window = Opening(Center - 0.35f, Center + 0.35f, FloorZ + 1.25f, FloorZ + 1.85f);
			B.Wall(A, Bp, FloorZ, HighZ, WallT, { Window }, SPlank);
			B.OpeningUnit(A, Bp, FloorZ, WallT, Window, STrim, SGlass, STrim, 0.12f, 0.06f, true);
		}
		// East wall (faces the yard): wide plank door, the rest is low wall.
		{
			const FVector2D A(XMax, YMin);
			const FVector2D Bp(XMax, YMax);
			const float Center = C.Y - YMin;
			const FWallOpening Door = Opening(Center - Spec.ShedDoorWidth * 0.5f, Center + Spec.ShedDoorWidth * 0.5f,
				FloorZ, FloorZ + Spec.ShedDoorHeight);
			B.Wall(A, Bp, FloorZ, LowZ, WallT, { Door }, SPlank);
			B.OpeningUnit(A, Bp, FloorZ, WallT, Door, STrim, SPlank, STrim, 0.09f, 0.06f, false);
		}
		// Triangles between the low walls and the sloping roof (east and west ends).
		{
			const TArray<FVector2D> Section = {
				FVector2D(YMax, LowZ),
				FVector2D(YMax, HighZ),
				FVector2D(YMin, LowZ)
			};
			B.ExtrudeProfile(Section, XMin, XMin + WallT, FTransform::Identity, SPlank);
			B.ExtrudeProfile(Section, XMax - WallT, XMax, FTransform::Identity, SPlank);
		}
		// Metal sheet roof.
		{
			const float Pitch = FMath::RadiansToDegrees(FMath::Atan2(HighZ - LowZ, SD));
			const float SlopeHalf = (SD * 0.5f) / FMath::Cos(FMath::DegreesToRadians(Pitch)) + 0.22f;
			B.Box(FVector(C.X, C.Y, (LowZ + HighZ) * 0.5f + 0.04f), FVector(SW * 0.5f + 0.32f, SlopeHalf, 0.05f),
				SMetal, FRotator(Pitch, 0.f, 0.f));
		}
	}
	/**
	 * Central concrete yard: separately poured panels with joint lines, a base that
	 * shows through the joints, the apron towards the driveway and the doorstep slab.
	 */
	static void BuildYardMesh(FMeshBuilder& B, const FPhase4BHomeSpec& Spec)
	{
		const int32 SConcrete = B.Slot(TEXT("MI_Concrete"));
		const int32 SGravel = B.Slot(TEXT("MI_Gravel"));

		const FVector2D Min = Spec.YardMin;
		const FVector2D Max = Spec.YardMax;
		const int32 NX = FMath::Clamp(Spec.YardPanelsX, 2, 12);
		const int32 NY = FMath::Clamp(Spec.YardPanelsY, 2, 12);
		const float Top = Spec.YardTopOffsetM;
		const float Thickness = Spec.YardThicknessM;
		const float Gap = 0.04f;

		FRandomStream Rng(Spec.RandomSeed + 977);
		TArray<FVector2D> Nodes;
		Nodes.Reserve((NX + 1) * (NY + 1));
		for (int32 IY = 0; IY <= NY; ++IY)
		{
			for (int32 IX = 0; IX <= NX; ++IX)
			{
				const float U = IX / static_cast<float>(NX);
				const float V = IY / static_cast<float>(NY);
				FVector2D P(Min.X + (Max.X - Min.X) * U, Min.Y + (Max.Y - Min.Y) * V);
				if (IX == 0 || IX == NX || IY == 0 || IY == NY)
				{
					// Break the outline up: no perfectly rectangular poured yard.
					P.X += Rng.FRandRange(-0.30f, 0.30f);
					P.Y += Rng.FRandRange(-0.30f, 0.30f);
				}
				Nodes.Add(P);
			}
		}
		auto Node = [&Nodes, NX](int32 IX, int32 IY) { return Nodes[IY * (NX + 1) + IX]; };

		// Base underneath (this is what is visible in the joint lines).
		B.Slab(Node(0, 0) - FVector2D(0.25f, 0.25f), Node(NX, 0) + FVector2D(0.25f, -0.25f),
			Node(NX, NY) + FVector2D(0.25f, 0.25f), Node(0, NY) + FVector2D(-0.25f, 0.25f),
			Top - 0.05f, 0.22f, SGravel);

		// Poured panels.
		for (int32 IY = 0; IY < NY; ++IY)
		{
			for (int32 IX = 0; IX < NX; ++IX)
			{
				const FVector2D P00 = Node(IX, IY);
				const FVector2D P10 = Node(IX + 1, IY);
				const FVector2D P11 = Node(IX + 1, IY + 1);
				const FVector2D P01 = Node(IX, IY + 1);
				const FVector2D Center = (P00 + P10 + P11 + P01) * 0.25f;
				auto Shrink = [&Center](const FVector2D& P)
				{
					const FVector2D Dir = (Center - P).GetSafeNormal();
					return P + Dir * FMath::Min(0.04f, FVector2D::Distance(Center, P) * 0.2f);
				};
				B.Slab(Shrink(P00), Shrink(P10), Shrink(P11), Shrink(P01), Top, Thickness, SConcrete);
			}
		}

		// Apron towards the driveway (west side, only up to the end of the apartment).
		{
			const FVector2D A0(Min.X - 6.4f, 755.6f);
			const FVector2D A1(Min.X + 0.5f, 768.6f);
			const float Split = 762.0f;
			for (int32 Index = 0; Index < 2; ++Index)
			{
				const float Y0 = (Index == 0) ? A0.Y : Split;
				const float Y1 = (Index == 0) ? Split : A1.Y;
				const FVector2D Jitter(Rng.FRandRange(-0.2f, 0.2f), Rng.FRandRange(-0.15f, 0.15f));
				B.Slab(FVector2D(A0.X + 0.15f, Y0 + 0.12f), FVector2D(A1.X - 0.15f, Y0 + 0.12f),
					FVector2D(A1.X - 0.15f + Jitter.X, Y1 - 0.12f), FVector2D(A0.X + 0.15f, Y1 - 0.12f),
					Top, Thickness, SConcrete);
			}
		}

		// Doorstep slab in front of the front door.
		{
			const FVector2D HC = Spec.HouseCenter;
			const float DoorX = HC.X - 1.7f;
			const float WallY = HC.Y - Spec.HouseWidthY * 0.5f;
			B.Box(FVector(DoorX, WallY - 0.62f, Top + 0.13f), FVector(1.05f, 0.62f, 0.13f), SConcrete);
		}
	}

	/** Barbecue / grill spot on the veranda (brick body with a metal grate). */
	static void BuildGrillMesh(FMeshBuilder& B)
	{
		const int32 SBrick = B.Slot(TEXT("MI_Brick"));
		const int32 SMetal = B.Slot(TEXT("MI_MetalDoor"));

		const float BaseZ = 0.30f;      // veranda floor level
		const FVector2D At(764.2f, 792.2f);
		B.Box(FVector(At.X, At.Y, BaseZ + 0.44f), FVector(0.52f, 0.33f, 0.44f), SBrick);
		B.Box(FVector(At.X, At.Y - 0.35f, BaseZ + 0.42f), FVector(0.34f, 0.06f, 0.20f), SMetal);
		B.Box(FVector(At.X, At.Y, BaseZ + 0.90f), FVector(0.46f, 0.30f, 0.025f), SMetal);
	}
	// ------------------------------------------------------------------
	// Driveway (the property connection towards the Phase 4A road corridor)
	// ------------------------------------------------------------------
	static const TArray<FVector2D>& DefaultDrivewayPoints()
	{
		// Leaves the concrete yard on its west side, curves down the hillside and joins
		// the Phase 4A home road corridor where it has already descended past the house.
		static const TArray<FVector2D> Points = {
			FVector2D(733.f, 762.f), FVector2D(712.f, 754.f), FVector2D(696.f, 734.f),
			FVector2D(688.f, 710.f), FVector2D(692.f, 684.f), FVector2D(704.f, 662.f),
			FVector2D(721.7f, 636.7f)
		};
		return Points;
	}

	static void ResampleRoute(const TArray<FVector2D>& Points, float StepM, TArray<FVector2D>& Out)
	{
		Out.Reset();
		if (Points.Num() < 2)
		{
			return;
		}
		Out.Add(Points[0]);
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
				Out.Add(From + Direction * Travelled);
				Travelled += StepM;
			}
			Carried = StepM - (Travelled - Length);
		}
		if (FVector2D::Distance(Out.Last(), Points.Last()) > 0.5f)
		{
			Out.Add(Points.Last());
		}
	}

	/** Gravel driveway ribbon that follows the graded terrain of the driveway corridor. */
	static void BuildDrivewayMesh(FMeshBuilder& B, const FPhase4BHomeSpec& Spec, UWorld* World,
	                              TArray<FVector>* OutProfileM)
	{
		const int32 SGravel = B.Slot(TEXT("MI_Gravel"));
		const TArray<FVector2D>& Route = (Spec.DrivewayPoints.Num() >= 2) ? Spec.DrivewayPoints : DefaultDrivewayPoints();
		TArray<FVector2D> Samples;
		ResampleRoute(Route, 2.f, Samples);
		if (Samples.Num() < 3)
		{
			return;
		}

		FRandomStream Rng(Spec.RandomSeed + 5150);
		TArray<float> Profile;
		Profile.SetNumUninitialized(Samples.Num());
		for (int32 Index = 0; Index < Samples.Num(); ++Index)
		{
			float Z = 0.f;
			Profile[Index] = TraceGround(World, Samples[Index], Z) ? Z : 0.f;
		}

		// Like every other property mesh the driveway is authored relative to the pad
		// surface (the actors are placed at the pad height), so rebase the profile.
		float PadZ = 0.f;
		if (!TraceGround(World, Spec.PropertyCenter, PadZ) && Profile.Num() > 0)
		{
			PadZ = Profile[0];
		}
		for (float& Value : Profile)
		{
			Value -= PadZ;
		}

		const float StartDistance = 6.0f;   // the concrete apron covers the first metres
		float Travelled = 0.f;
		TArray<FVector2D> Lefts;
		TArray<FVector2D> Rights;
		TArray<float> Tops;
		for (int32 Index = 0; Index < Samples.Num(); ++Index)
		{
			if (Index > 0)
			{
				Travelled += FVector2D::Distance(Samples[Index - 1], Samples[Index]);
			}
			if (Travelled < StartDistance)
			{
				continue;
			}
			const FVector2D Forward = (Index + 1 < Samples.Num())
				? (Samples[Index + 1] - Samples[Index]).GetSafeNormal()
				: (Samples[Index] - Samples[Index - 1]).GetSafeNormal();
			const FVector2D Side(-Forward.Y, Forward.X);
			const float HalfWidth = 2.10f + Rng.FRandRange(-0.15f, 0.15f);
			Lefts.Add(Samples[Index] - Side * HalfWidth);
			Rights.Add(Samples[Index] + Side * HalfWidth);
			Tops.Add(Profile[Index] + 0.045f);
		}
		for (int32 Index = 0; Index + 1 < Lefts.Num(); ++Index)
		{
			const FVector A0(Lefts[Index].X, Lefts[Index].Y, Tops[Index]);
			const FVector A1(Lefts[Index + 1].X, Lefts[Index + 1].Y, Tops[Index + 1]);
			const FVector B1(Rights[Index + 1].X, Rights[Index + 1].Y, Tops[Index + 1]);
			const FVector B0(Rights[Index].X, Rights[Index].Y, Tops[Index]);
			B.Quad(A0, A1, B1, B0, SGravel);
			B.Quad(FVector(A1.X, A1.Y, Tops[Index + 1] - 0.10f), A1, A0,
				FVector(A0.X, A0.Y, Tops[Index] - 0.10f), SGravel);
			B.Quad(B1, FVector(B1.X, B1.Y, Tops[Index + 1] - 0.10f),
				FVector(B0.X, B0.Y, Tops[Index] - 0.10f), B0, SGravel);
		}

		if (OutProfileM != nullptr)
		{
			OutProfileM->Reset();
			OutProfileM->Add(FVector(Samples[0].X, Samples[0].Y, Profile[0]));
			for (int32 Index = 1; Index + 1 < Samples.Num(); Index += 4)
			{
				OutProfileM->Add(FVector(Samples[Index].X, Samples[Index].Y, Profile[Index]));
			}
			OutProfileM->Add(FVector(Samples.Last().X, Samples.Last().Y, Profile.Last()));
		}
	}
	// ------------------------------------------------------------------
	// Pine trees: tall, layered and irregular - four variants, each split into
	// a trunk mesh (collision) and a canopy mesh (no collision)
	// ------------------------------------------------------------------
	struct FPineVariant
	{
		float Height = 20.f;
		float Radius = 4.f;
		int32 Tiers = 8;
		float CanopyStart = 0.42f;
		float TrunkRadius = 0.30f;
		float ScaleMin = 0.85f;
		float ScaleMax = 1.15f;
	};

	static const TArray<FPineVariant>& PineVariants()
	{
		static const TArray<FPineVariant> Variants = {
			{ 17.5f, 3.2f, 7, 0.42f, 0.26f, 0.82f, 1.06f },
			{ 20.5f, 3.9f, 8, 0.37f, 0.30f, 0.88f, 1.12f },
			{ 23.5f, 4.5f, 8, 0.45f, 0.34f, 0.92f, 1.18f },
			{ 26.5f, 5.1f, 9, 0.40f, 0.38f, 0.96f, 1.24f }
		};
		return Variants;
	}

	static void BuildPineTrunkMesh(FMeshBuilder& B, const FPineVariant& Variant)
	{
		const int32 SBark = B.Slot(TEXT("MI_Bark"));
		const float CrownTop = Variant.Height * (Variant.CanopyStart + 0.20f);
		B.Cylinder(FVector(0.f, 0.f, -0.6f), FVector(0.f, 0.f, 0.7f),
			Variant.TrunkRadius * 1.75f, Variant.TrunkRadius * 1.20f, 9, SBark, 0.24f, 3311);
		B.Cylinder(FVector(0.f, 0.f, 0.6f), FVector(0.f, 0.f, CrownTop),
			Variant.TrunkRadius * 1.12f, Variant.TrunkRadius * 0.50f, 9, SBark, 0.18f, 3312);
	}

	static void BuildPineCanopyMesh(FMeshBuilder& B, const FPineVariant& Variant, int32 VariantIndex)
	{
		const int32 SNeedles = B.Slot(TEXT("MI_Needles"));
		FRandomStream Rng(77000 + VariantIndex * 131);
		const float CanopyBottom = Variant.Height * Variant.CanopyStart;
		const float Span = Variant.Height - CanopyBottom;
		const int32 Tiers = FMath::Max(4, Variant.Tiers);
		for (int32 Tier = 0; Tier < Tiers; ++Tier)
		{
			const float T = Tier / static_cast<float>(Tiers - 1);
			const float BaseZ = CanopyBottom + Span * 0.72f * T;
			const float Radius = Variant.Radius * (1.f - 0.80f * T);
			const float TierHeight = Span * 0.55f * (1.f - 0.45f * T);
			const float Angle = Rng.FRandRange(0.f, 2.f * PI);
			const float Amount = Radius * Rng.FRandRange(0.08f, 0.32f);
			const FVector Offset(FMath::Cos(Angle) * Amount, FMath::Sin(Angle) * Amount, 0.f);
			B.Cylinder(FVector(Offset.X, Offset.Y, BaseZ),
				FVector(Offset.X * 0.5f, Offset.Y * 0.5f, BaseZ + TierHeight),
				Radius, Radius * 0.34f, 12, SNeedles, 0.15f, 4000 + Tier * 17 + VariantIndex);
		}
		B.Cylinder(FVector(0.f, 0.f, Variant.Height - Span * 0.30f), FVector(0.f, 0.f, Variant.Height),
			Variant.Radius * 0.26f, 0.03f, 10, SNeedles, 0.10f, 7000 + VariantIndex);
	}
	// (implementation functions follow, all inside WITH_EDITOR)
	// ------------------------------------------------------------------
	// Terrain refinement (Phase 4A pad -> believable construction site + driveway)
	// ------------------------------------------------------------------
	/** Bilinear sample of a height array that covers the grid rect starting at (MinX, MinY). */
	static float SampleArray(const TArray<float>& Values, int32 SizeX, int32 SizeY, int32 MinX, int32 MinY,
	                         const FLandscapeGrid& Grid, const FVector2D& WorldM)
	{
		const float LocalX = FMath::Clamp((WorldM.X - Grid.OriginM.X) / Grid.StepM - MinX, 0.f, static_cast<float>(SizeX - 1));
		const float LocalY = FMath::Clamp((WorldM.Y - Grid.OriginM.Y) / Grid.StepM - MinY, 0.f, static_cast<float>(SizeY - 1));
		const int32 X0 = FMath::FloorToInt(LocalX);
		const int32 Y0 = FMath::FloorToInt(LocalY);
		const int32 X1 = FMath::Min(X0 + 1, SizeX - 1);
		const int32 Y1 = FMath::Min(Y0 + 1, SizeY - 1);
		const float FX = LocalX - X0;
		const float FY = LocalY - Y0;
		const float A = FMath::Lerp(Values[Y0 * SizeX + X0], Values[Y0 * SizeX + X1], FX);
		const float B = FMath::Lerp(Values[Y1 * SizeX + X0], Values[Y1 * SizeX + X1], FX);
		return FMath::Lerp(A, B, FY);
	}

	static float DistanceOutsideWork(const FPhase4BHomeSpec& Spec, const FVector2D& P)
	{
		const float DX = FMath::Max(FMath::Max(Spec.WorkAreaMin.X - P.X, P.X - Spec.WorkAreaMax.X), 0.f);
		const float DY = FMath::Max(FMath::Max(Spec.WorkAreaMin.Y - P.Y, P.Y - Spec.WorkAreaMax.Y), 0.f);
		return FMath::Sqrt(DX * DX + DY * DY);
	}

	static FPhase4BPropertyResult RefineHomeTerrainImpl(UWorld* World, const FPhase4BHomeSpec& Spec)
	{
		FPhase4BPropertyResult Result;
		Result.PropertyCenter = Spec.PropertyCenter;

		FLandscapeGrid Grid;
		if (!ResolveGrid(World, Grid))
		{
			Result.Message = TEXT("no landscape in the level");
			return Result;
		}

		float PadZ = 0.f;
		if (!TraceGround(World, Spec.PropertyCenter, PadZ))
		{
			Result.Message = TEXT("could not measure the terrain at the property centre");
			return Result;
		}
		Result.PadHeightM = PadZ;
		// The landscape heightmap is stored relative to the landscape actor, so the measured
		// world height has to be converted into that space (and back for the report).
		const float PadStored = PadZ - Grid.ZOffsetM;

		// Region: the property plus the driveway and the slope around it.
		const float HalfRegion = 170.f;
		const int32 MinX = FMath::Max(Grid.VertexMinX, Grid.IndexX(Spec.PropertyCenter.X - HalfRegion));
		const int32 MaxX = FMath::Min(Grid.VertexMaxX, Grid.IndexX(Spec.PropertyCenter.X + HalfRegion));
		const int32 MinY = FMath::Max(Grid.VertexMinY, Grid.IndexY(Spec.PropertyCenter.Y - HalfRegion));
		const int32 MaxY = FMath::Min(Grid.VertexMaxY, Grid.IndexY(Spec.PropertyCenter.Y + HalfRegion));
		const int32 SizeX = MaxX - MinX + 1;
		const int32 SizeY = MaxY - MinY + 1;
		if (SizeX < 8 || SizeY < 8)
		{
			Result.Message = TEXT("the property region is outside the landscape");
			return Result;
		}

		// Current terrain (the Phase 4A result).
		TArray<float> Current;
		Current.SetNumUninitialized(SizeX * SizeY);
		{
			TArray<uint16> Raw;
			Raw.SetNumUninitialized(SizeX * SizeY);
			FLandscapeEditDataInterface Edit(Grid.Info);
			Edit.GetHeightDataFast(MinX, MinY, MaxX, MaxY, Raw.GetData(), /*Stride=*/0, nullptr, nullptr);
			for (int32 Index = 0; Index < Raw.Num(); ++Index)
			{
				Current[Index] = ValueToHeightM(Raw[Index], Grid.ZScale);
			}
		}

		// Natural reference: heights sampled on a ring outside the Phase 4A pad falloff.
		const int32 RingCount = 24;
		const float RingRadius = 142.f;
		TArray<FVector2D> RingPoints;
		TArray<float> RingHeights;
		RingPoints.Reserve(RingCount);
		RingHeights.Reserve(RingCount);
		for (int32 Index = 0; Index < RingCount; ++Index)
		{
			const float Angle = 2.f * PI * Index / static_cast<float>(RingCount);
			const FVector2D P = Spec.PropertyCenter + FVector2D(FMath::Cos(Angle), FMath::Sin(Angle)) * RingRadius;
			RingPoints.Add(P);
			RingHeights.Add(SampleArray(Current, SizeX, SizeY, MinX, MinY, Grid, P));
		}
		auto NaturalAt = [&](const FVector2D& P)
		{
			float Sum = 0.f;
			float WeightSum = 0.f;
			for (int32 Index = 0; Index < RingPoints.Num(); ++Index)
			{
				const float W = 1.f / (FVector2D::DistSquared(P, RingPoints[Index]) + 49.f);
				Sum += W * RingHeights[Index];
				WeightSum += W;
			}
			const float Base = (WeightSum > 0.f) ? (Sum / WeightSum) : PadStored;
			const float Radius = FVector2D::Distance(P, Spec.PropertyCenter);
			const float Relief = (Fbm(P * (1.f / 23.f), 3) * 1.15f +
				Fbm(P * (1.f / 7.5f) + FVector2D(11.f, -7.f), 2) * 0.32f) * Falloff(Radius, 92.f, 138.f);
			return Base + Relief;
		};
		// Target field: level construction area, natural shoulder outside it.
		TArray<float> Target;
		Target.SetNumUninitialized(SizeX * SizeY);
		for (int32 Y = 0; Y < SizeY; ++Y)
		{
			for (int32 X = 0; X < SizeX; ++X)
			{
				const FVector2D P = Grid.WorldAt(MinX + X, MinY + Y);
				const float Distance = DistanceOutsideWork(Spec, P);
				const float Edge = Spec.EdgeNoiseM * (0.5f + 0.5f * Fbm(P * (1.f / 17.f) + FVector2D(3.5f, 9.5f), 2));
				const float Weight = FMath::SmoothStep(Edge, Edge + Spec.WorkAreaBlendM, Distance);
				Target[Y * SizeX + X] = FMath::Lerp(PadStored, NaturalAt(P), Weight);
			}
		}

		// Driveway: profile along the route (grade limited, never climbing), then stamped in.
		const TArray<FVector2D>& Route = (Spec.DrivewayPoints.Num() >= 2) ? Spec.DrivewayPoints : DefaultDrivewayPoints();
		TArray<FVector2D> Samples;
		ResampleRoute(Route, 2.f, Samples);
		if (Samples.Num() >= 3)
		{
			TArray<float> Profile;
			Profile.SetNumUninitialized(Samples.Num());
			for (int32 Index = 0; Index < Samples.Num(); ++Index)
			{
				Profile[Index] = SampleArray(Target, SizeX, SizeY, MinX, MinY, Grid, Samples[Index]);
			}
			for (int32 Pass = 0; Pass < 3; ++Pass)
			{
				const TArray<float> Copy = Profile;
				for (int32 Index = 0; Index < Profile.Num(); ++Index)
				{
					float Sum = 0.f;
					int32 Count = 0;
					for (int32 Offset = -2; Offset <= 2; ++Offset)
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
			Profile[0] = PadStored - 0.02f;
			const float MaxStep = Spec.DrivewayMaxGrade * 2.f;
			float MaxGrade = 0.f;
			for (int32 Index = 1; Index < Profile.Num(); ++Index)
			{
				Profile[Index] = FMath::Clamp(Profile[Index], Profile[Index - 1] - MaxStep, Profile[Index - 1] + MaxStep);
				Profile[Index] = FMath::Min(Profile[Index], Profile[Index - 1]);
				MaxGrade = FMath::Max(MaxGrade, FMath::Abs(Profile[Index] - Profile[Index - 1]) / 2.f);
			}

			const float Reach = Spec.DrivewayHalfWidthM + Spec.DrivewayFalloffM;
			for (int32 Index = 0; Index < Samples.Num(); ++Index)
			{
				const int32 ReachMinX = FMath::Max(0, Grid.IndexX(Samples[Index].X - Reach) - MinX);
				const int32 ReachMaxX = FMath::Min(SizeX - 1, Grid.IndexX(Samples[Index].X + Reach) - MinX);
				const int32 ReachMinY = FMath::Max(0, Grid.IndexY(Samples[Index].Y - Reach) - MinY);
				const int32 ReachMaxY = FMath::Min(SizeY - 1, Grid.IndexY(Samples[Index].Y + Reach) - MinY);
				for (int32 Y = ReachMinY; Y <= ReachMaxY; ++Y)
				{
					for (int32 X = ReachMinX; X <= ReachMaxX; ++X)
					{
						const FVector2D P = Grid.WorldAt(MinX + X, MinY + Y);
						const float Distance = FVector2D::Distance(P, Samples[Index]);
						// The levelled construction area stays untouched: the driveway apron
						// takes over right at the property edge.
						const float Outside = DistanceOutsideWork(Spec, P);
						const float Fade = FMath::SmoothStep(0.f, 4.f, Outside);
						const float Weight = Falloff(Distance, Spec.DrivewayHalfWidthM,
							Spec.DrivewayHalfWidthM + Spec.DrivewayFalloffM) * Fade;
						if (Weight > 0.f)
						{
							float& Height = Target[Y * SizeX + X];
							Height = FMath::Lerp(Height, Profile[Index], Weight);
						}
					}
				}
			}
			Result.DrivewayLengthM = (Samples.Num() - 1) * 2.f;
			Result.DrivewayStartHeightM = Profile[0] + Grid.ZOffsetM;
			Result.DrivewayEndHeightM = Profile.Last() + Grid.ZOffsetM;
			Result.DrivewayMaxGrade = MaxGrade;
			Result.DrivewayPointsCm.Reset();
			for (int32 Index = 0; Index < Samples.Num(); Index += 4)
			{
				Result.DrivewayPointsCm.Add(FVector(Samples[Index].X * 100.f, Samples[Index].Y * 100.f,
					(Profile[Index] + Grid.ZOffsetM) * 100.f));
			}
			Result.DrivewayPointsCm.Add(FVector(Samples.Last().X * 100.f, Samples.Last().Y * 100.f,
				(Profile.Last() + Grid.ZOffsetM) * 100.f));
		}
		// Statistics on the field that is about to be written.
		{
			float MinZ = FLT_MAX;
			float MaxZ = -FLT_MAX;
			for (int32 SampleY = 0; SampleY < 4; ++SampleY)
			{
				for (int32 SampleX = 0; SampleX < 4; ++SampleX)
				{
					const float U = 0.15f + 0.7f * SampleX / 3.f;
					const float V = 0.15f + 0.7f * SampleY / 3.f;
					const FVector2D P(
						Spec.WorkAreaMin.X + (Spec.WorkAreaMax.X - Spec.WorkAreaMin.X) * U,
						Spec.WorkAreaMin.Y + (Spec.WorkAreaMax.Y - Spec.WorkAreaMin.Y) * V);
					const float Z = SampleArray(Target, SizeX, SizeY, MinX, MinY, Grid, P);
					MinZ = FMath::Min(MinZ, Z);
					MaxZ = FMath::Max(MaxZ, Z);
				}
			}
			Result.WorkAreaSpreadM = MaxZ - MinZ;

			float SlopeMin = FLT_MAX;
			float SlopeMax = -FLT_MAX;
			float MaxSlope = 0.f;
			for (int32 Ring = 0; Ring < 3; ++Ring)
			{
				const float Radius = 58.f + Ring * 32.f;
				for (int32 Index = 0; Index < 16; ++Index)
				{
					const float Angle = 2.f * PI * Index / 16.f;
					const FVector2D Dir(FMath::Cos(Angle), FMath::Sin(Angle));
					const FVector2D P = Spec.PropertyCenter + Dir * Radius;
					const float Z = SampleArray(Target, SizeX, SizeY, MinX, MinY, Grid, P);
					const float ZOut = SampleArray(Target, SizeX, SizeY, MinX, MinY, Grid, P + Dir * 4.f);
					SlopeMin = FMath::Min(SlopeMin, Z);
					SlopeMax = FMath::Max(SlopeMax, Z);
					MaxSlope = FMath::Max(MaxSlope, FMath::Abs(ZOut - Z) / 4.f);
				}
			}
			Result.NaturalSlopeSpreadM = SlopeMax - SlopeMin;
			Result.NaturalSlopeMaxPercent = MaxSlope * 100.f;
		}

		// Write the field and rebuild the collision.
		float Unused = 0.f;
		if (!WriteHeightField(Grid, MinX, MinY, MaxX, MaxY, Target, Unused))
		{
			Result.Message = TEXT("could not write the terrain heights");
			return Result;
		}
		RefreshCollision(Grid);

		// Read the heights back: proof that the pad survived and the slope is real.
		{
			FLandscapeEditDataInterface ReadEdit(Grid.Info);
			auto ReadOne = [&Grid, &ReadEdit](const FVector2D& P)
			{
				const int32 PX = FMath::Clamp(Grid.IndexX(P.X), Grid.VertexMinX, Grid.VertexMaxX);
				const int32 PY = FMath::Clamp(Grid.IndexY(P.Y), Grid.VertexMinY, Grid.VertexMaxY);
				uint16 Value = 32768;
				ReadEdit.GetHeightDataFast(PX, PY, PX, PY, &Value, 0, nullptr, nullptr);
				return ValueToHeightM(Value, Grid.ZScale) + Grid.ZOffsetM;
			};
			const FVector2D WorkCenter(
				(Spec.WorkAreaMin.X + Spec.WorkAreaMax.X) * 0.5f,
				(Spec.WorkAreaMin.Y + Spec.WorkAreaMax.Y) * 0.5f);
			Result.ReadbackSamplesM.Add(TEXT("pad_centre"), ReadOne(Spec.PropertyCenter));
			Result.ReadbackSamplesM.Add(TEXT("work_area_centre"), ReadOne(WorkCenter));
			Result.ReadbackSamplesM.Add(TEXT("natural_north_110m"), ReadOne(Spec.PropertyCenter + FVector2D(0.f, 110.f)));
			Result.ReadbackSamplesM.Add(TEXT("natural_south_110m"), ReadOne(Spec.PropertyCenter + FVector2D(0.f, -110.f)));
			Result.ReadbackSamplesM.Add(TEXT("natural_west_110m"), ReadOne(Spec.PropertyCenter + FVector2D(-110.f, 0.f)));
			Result.ReadbackSamplesM.Add(TEXT("natural_east_110m"), ReadOne(Spec.PropertyCenter + FVector2D(110.f, 0.f)));
			if (Result.DrivewayPointsCm.Num() > 0)
			{
				const FVector& Start = Result.DrivewayPointsCm[0];
				const FVector& End = Result.DrivewayPointsCm.Last();
				Result.ReadbackSamplesM.Add(TEXT("driveway_start"), ReadOne(FVector2D(Start.X * 0.01f, Start.Y * 0.01f)));
				Result.ReadbackSamplesM.Add(TEXT("driveway_join"), ReadOne(FVector2D(End.X * 0.01f, End.Y * 0.01f)));
			}
		}

		// Design samples (world XY key -> height).
		auto AddSample = [&Result, &Target, SizeX, SizeY, MinX, MinY, &Grid](const TCHAR* Key, const FVector2D& P)
		{
			Result.ElevationSamplesM.Add(FString(Key), SampleArray(Target, SizeX, SizeY, MinX, MinY, Grid, P) + Grid.ZOffsetM);
		};
		AddSample(TEXT("house_site"), Spec.HouseCenter);
		AddSample(TEXT("veranda_apron"), FVector2D(Spec.HouseCenter.X, Spec.HouseCenter.Y + Spec.HouseWidthY * 0.5f
			+ Spec.VerandaDepthY + Spec.VerandaApronDepthY * 0.5f));
		AddSample(TEXT("yard_centre"), FVector2D((Spec.YardMin.X + Spec.YardMax.X) * 0.5f,
			(Spec.YardMin.Y + Spec.YardMax.Y) * 0.5f));
		AddSample(TEXT("garage_site"), Spec.GarageCenter);
		AddSample(TEXT("shed_site"), Spec.ShedCenter);
		for (int32 Index = 0; Index < 8; ++Index)
		{
			const float Angle = 2.f * PI * Index / 8.f;
			const FVector2D Dir(FMath::Cos(Angle), FMath::Sin(Angle));
			AddSample(*FString::Printf(TEXT("slope_%02d_60m"), Index), Spec.PropertyCenter + Dir * 60.f);
			AddSample(*FString::Printf(TEXT("slope_%02d_120m"), Index), Spec.PropertyCenter + Dir * 120.f);
		}

		TSet<ULandscapeComponent*> Edited;
		Grid.Info->GetComponentsInRegion(MinX, MinY, MaxX, MaxY, Edited);
		Result.EditedComponentCount = Edited.Num();

		World->MarkPackageDirty();
		Result.bSuccess = true;
		Result.Message = FString::Printf(
			TEXT("property terrain refined around (%.0f, %.0f) m: pad %.2f m, driveway %.0f m at %.1f%% max grade"),
			Spec.PropertyCenter.X, Spec.PropertyCenter.Y, PadZ, Result.DrivewayLengthM, Result.DrivewayMaxGrade * 100.f);
		return Result;
	}

	// ------------------------------------------------------------------
	// Mesh generation implementation
	// ------------------------------------------------------------------
	static FPhase4BPropertyResult BuildPropertyAssetsImpl(UWorld* World, const FPhase4BHomeSpec& Spec)
	{
		FPhase4BPropertyResult Result;
		Result.PropertyCenter = Spec.PropertyCenter;

		const FMaterialSet Materials = LoadPropertyMaterials();
		for (const FString& Missing : Materials.Missing)
		{
			Result.Warnings.Add(FString::Printf(
				TEXT("material instance missing (the mesh keeps a default material): %s"), *Missing));
		}

		auto Save = [&Materials, &Result](const TCHAR* AssetName, FMeshBuilder& Builder, bool bSimpleCollision,
		                                  float CollisionTopM = 0.f)
		{
			const FString Name(AssetName);
			UStaticMesh* Mesh = CreateStaticMeshAsset(Name, Builder, Materials, bSimpleCollision, CollisionTopM,
				Result.Warnings);
			if (Mesh != nullptr)
			{
				Result.CreatedAssets.Add(FString::Printf(TEXT("%s/%s [%d slots, %d tris, collision %s, %d verts]"),
					*AssetDir, *Name, Builder.SlotNames.Num(), Builder.TriangleCount,
					bSimpleCollision ? TEXT("yes") : TEXT("no"), Builder.Description.Vertices().Num()));
			}
		};

		{
			FMeshBuilder Builder;
			BuildHouseMesh(Builder, Spec);
			Save(TEXT("SM_P4B_House"), Builder, true);
		}
		{
			FMeshBuilder Builder;
			BuildVerandaMesh(Builder, Spec);
			// Collision stops just under the deck so the player can stand on the veranda
			// instead of being pushed up onto the pergola (the open apron is a little lower).
			Save(TEXT("SM_P4B_Veranda"), Builder, true, Spec.FoundationHeight - 0.11f);
		}
		{
			FMeshBuilder Builder;
			BuildGarageMesh(Builder, Spec);
			Save(TEXT("SM_P4B_Garage"), Builder, true);
		}
		{
			FMeshBuilder Builder;
			BuildShedMesh(Builder, Spec);
			Save(TEXT("SM_P4B_Shed"), Builder, true);
		}
		{
			FMeshBuilder Builder;
			BuildYardMesh(Builder, Spec);
			// Collision is clamped to the paving surface so the hull stays flat.
			Save(TEXT("SM_P4B_ConcreteYard"), Builder, true, Spec.YardTopOffsetM);
		}
		{
			FMeshBuilder Builder;
			BuildGrillMesh(Builder);
			Save(TEXT("SM_P4B_Grill"), Builder, true);
		}
		{
			FMeshBuilder Builder;
			BuildDrivewayMesh(Builder, Spec, World, nullptr);
			Save(TEXT("SM_P4B_Driveway"), Builder, false);
		}

		const TArray<FPineVariant>& Variants = PineVariants();
		for (int32 Index = 0; Index < Variants.Num(); ++Index)
		{
			const FString Suffix = FString::Chr(TEXT('A') + Index);
			{
				FMeshBuilder Builder;
				BuildPineTrunkMesh(Builder, Variants[Index]);
				Save(*FString::Printf(TEXT("SM_P4B_PineTrunk_%s"), *Suffix), Builder, true);
			}
			{
				FMeshBuilder Builder;
				BuildPineCanopyMesh(Builder, Variants[Index], Index);
				Save(*FString::Printf(TEXT("SM_P4B_PineCanopy_%s"), *Suffix), Builder, false);
			}
		}

		Result.bSuccess = Result.CreatedAssets.Num() > 0;
		Result.Message = FString::Printf(TEXT("%d property meshes generated in %s"),
			Result.CreatedAssets.Num(), *AssetDir);
		return Result;
	}

	static int32 ClearPropertyActorsImpl(UWorld* World)
	{
		TArray<AActor*> ToDestroy;
		for (TActorIterator<AActor> It(World); It; ++It)
		{
			AActor* Actor = *It;
			if (IsValid(Actor) && Actor->GetActorLabel().StartsWith(TEXT("P4B_")))
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
		return Removed;
	}

	static float GroundHeightMImpl(UWorld* World, float XM, float YM, bool& bHit)
	{
		float Z = 0.f;
		bHit = TraceGround(World, FVector2D(XM, YM), Z);
		return Z;
	}
	// ------------------------------------------------------------------
	// Forest implementation: dense pines right around the property, thinning with
	// distance, following the tree line of the hill, all instanced per WP cell
	// ------------------------------------------------------------------
	static FPhase4BPropertyResult PlacePineForestImpl(UWorld* World, const FPhase4BHomeSpec& Spec)
	{
		FPhase4BPropertyResult Result;
		Result.PropertyCenter = Spec.PropertyCenter;

		const TArray<FPineVariant>& Variants = PineVariants();
		TArray<UStaticMesh*> Trunks;
		TArray<UStaticMesh*> Canopies;
		for (int32 Index = 0; Index < Variants.Num(); ++Index)
		{
			const FString Suffix = FString::Chr(TEXT('A') + Index);
			UStaticMesh* Trunk = LoadObject<UStaticMesh>(nullptr,
				*FString::Printf(TEXT("%s/SM_P4B_PineTrunk_%s.SM_P4B_PineTrunk_%s"), *AssetDir, *Suffix, *Suffix));
			UStaticMesh* Canopy = LoadObject<UStaticMesh>(nullptr,
				*FString::Printf(TEXT("%s/SM_P4B_PineCanopy_%s.SM_P4B_PineCanopy_%s"), *AssetDir, *Suffix, *Suffix));
			if (Trunk == nullptr || Canopy == nullptr)
			{
				Result.Message = TEXT("the pine meshes are missing - generate the property meshes first");
				return Result;
			}
			Trunks.Add(Trunk);
			Canopies.Add(Canopy);
		}

		// Trees of a previous run are replaced.
		{
			TArray<AActor*> ToDestroy;
			for (TActorIterator<AActor> It(World); It; ++It)
			{
				if (IsValid(*It) && (*It)->GetActorLabel().StartsWith(TEXT("P4B_Trees_")))
				{
					ToDestroy.Add(*It);
				}
			}
			for (AActor* Actor : ToDestroy)
			{
				World->DestroyActor(Actor, false, false);
				++Result.RemovedActors;
			}
		}

		// Keep clear of the Phase 4A road corridors.
		TArray<TArray<FVector2D>> RoadPolylines;
		for (TActorIterator<AActor> It(World); It; ++It)
		{
			AActor* Actor = *It;
			if (!IsValid(Actor) || !Actor->GetActorLabel().StartsWith(TEXT("Road_Route_")))
			{
				continue;
			}
			if (USplineComponent* Spline = Actor->FindComponentByClass<USplineComponent>())
			{
				TArray<FVector2D> Points;
				const int32 Count = Spline->GetNumberOfSplinePoints();
				for (int32 Index = 0; Index < Count; ++Index)
				{
					const FVector Point = Spline->GetLocationAtSplinePoint(Index, ESplineCoordinateSpace::World) * 0.01f;
					Points.Add(FVector2D(Point.X, Point.Y));
				}
				if (Points.Num() >= 2)
				{
					RoadPolylines.Add(MoveTemp(Points));
				}
			}
		}

		const TArray<FVector2D>& Route = (Spec.DrivewayPoints.Num() >= 2) ? Spec.DrivewayPoints : DefaultDrivewayPoints();
		TArray<FVector2D> DrivewaySamples;
		ResampleRoute(Route, 2.f, DrivewaySamples);

		auto DistanceToPolyline = [](const TArray<FVector2D>& Points, const FVector2D& P, float SampleStep)
		{
			float Best = FLT_MAX;
			for (int32 Index = 0; Index + 1 < Points.Num(); ++Index)
			{
				const FVector2D A = Points[Index];
				const FVector2D B = Points[Index + 1];
				const float Length = FVector2D::Distance(A, B);
				const int32 Steps = FMath::Max(1, FMath::CeilToInt(Length / SampleStep));
				for (int32 Step = 0; Step <= Steps; ++Step)
				{
					Best = FMath::Min(Best, FVector2D::Distance(P, FMath::Lerp(A, B, Step / static_cast<float>(Steps))));
				}
			}
			return Best;
		};

		auto PickVariant = [](FRandomStream& Rng)
		{
			const float Roll = Rng.FRand();
			if (Roll < 0.30f) { return 0; }
			if (Roll < 0.58f) { return 1; }
			if (Roll < 0.82f) { return 2; }
			return 3;
		};

		FRandomStream Rng(Spec.RandomSeed);
		const float Outer = Spec.ForestOuterM;
		const float Spacing = FMath::Max(2.5f, Spec.TreeSpacingDenseM);
		const int32 GridCount = FMath::CeilToInt(2.f * Outer / Spacing);
		const float GridHalf = GridCount * Spacing * 0.5f;
		TMap<uint64, TArray<FTransform>> Instances;
		TSet<uint64> Occupied;
		int32 TreesInsideWorkArea = 0;   // accepted trees inside the property footprint (must stay 0)
		float Nearest = FLT_MAX;         // distance of the closest tree outside the property footprint
		TMap<int32, int32> PerVariant;
		bool bFull = false;
		for (int32 IY = 0; IY <= GridCount && !bFull; ++IY)
		{
			for (int32 IX = 0; IX <= GridCount && !bFull; ++IX)
			{
				const FVector2D P(
					Spec.PropertyCenter.X - GridHalf + (IX + Rng.FRandRange(-0.42f, 0.42f)) * Spacing,
					Spec.PropertyCenter.Y - GridHalf + (IY + Rng.FRandRange(-0.42f, 0.42f)) * Spacing);
				const float Radius = FVector2D::Distance(P, Spec.PropertyCenter);
				if (Radius < Spec.ForestInnerM || Radius > Outer)
				{
					continue;
				}

				// Density: dense immediately outside the property, thinning with distance
				// and broken up by noise so the clearing edge stays irregular.
				float Chance = (Radius <= Spec.ForestDenseM) ? 0.94f
					: ((Radius <= Spec.ForestMidM) ? 0.46f : 0.17f);
				Chance *= FMath::Clamp(0.45f + 1.15f * (0.5f + 0.5f * Fbm(P * (1.f / 44.f) + FVector2D(19.f, 4.f), 3)), 0.f, 1.f);
				if (Rng.FRand() > Chance)
				{
					continue;
				}

				// The property itself stays open (a few trees may stand close by).
				const float Dwork = DistanceOutsideWork(Spec, P);
				if (Dwork <= 0.f)
				{
					continue;   // never inside the house / garage / yard footprint
				}
				const float Margin = 3.5f + 4.5f * (0.5f + 0.5f * Fbm(P * (1.f / 21.f) + FVector2D(-5.f, 2.f), 2));
				if (Dwork < Margin && (Dwork < 2.2f || Rng.FRand() > 0.18f))
				{
					continue;
				}

				// Driveway and road corridors stay clear.
				if (DistanceToPolyline(DrivewaySamples, P, 2.f) < 7.5f)
				{
					continue;
				}
				bool bNearRoad = false;
				for (const TArray<FVector2D>& Road : RoadPolylines)
				{
					if (DistanceToPolyline(Road, P, 6.f) < 13.f)
					{
						bNearRoad = true;
						break;
					}
				}
				if (bNearRoad)
				{
					continue;
				}

				// Natural spacing (no clumps).
				const int32 BucketX = FMath::FloorToInt(P.X / 3.2f) + 4000;
				const int32 BucketY = FMath::FloorToInt(P.Y / 3.2f) + 4000;
				const uint64 Bucket = (static_cast<uint64>(BucketX) << 20) | static_cast<uint64>(BucketY);
				if (Occupied.Contains(Bucket))
				{
					continue;
				}

				// The tree line follows the hill: no pines in the open lowland.
				float GroundZ = 0.f;
				if (!TraceGround(World, P, GroundZ))
				{
					continue;
				}
				const float TreeLine = Spec.ForestMinHeightM + 5.f * Fbm(P * (1.f / 70.f) + FVector2D(23.f, -9.f), 2);
				if (GroundZ < TreeLine)
				{
					continue;
				}
				// Variant, size and orientation vary per instance.
				const int32 Variant = PickVariant(Rng);
				const FPineVariant& Selected = Variants[Variant];
				const float Scale = Rng.FRandRange(Selected.ScaleMin, Selected.ScaleMax);
				const FVector Scale3D(Scale * Rng.FRandRange(0.94f, 1.06f), Scale * Rng.FRandRange(0.94f, 1.06f),
					Scale * Rng.FRandRange(0.92f, 1.09f));
				const FRotator Rotation(Rng.FRandRange(-2.5f, 2.5f), Rng.FRandRange(0.f, 360.f), Rng.FRandRange(-2.5f, 2.5f));
				const FTransform Transform(Rotation,
					FVector(P.X * 100.f, P.Y * 100.f, (GroundZ - 0.35f) * 100.f), Scale3D);

				const int32 CellX = FMath::FloorToInt(P.X / Spec.TreeCellSizeM);
				const int32 CellY = FMath::FloorToInt(P.Y / Spec.TreeCellSizeM);
				const uint64 CellKey = (static_cast<uint64>(CellX + 100000) * 1000000ULL +
					static_cast<uint64>(CellY + 100000)) * 8ULL + static_cast<uint64>(Variant);
				Instances.FindOrAdd(CellKey).Add(Transform);
				Occupied.Add(Bucket);
				PerVariant.FindOrAdd(Variant)++;
				if (Dwork <= 0.f)
				{
					++TreesInsideWorkArea;
				}
				Nearest = FMath::Min(Nearest, Dwork);
				++Result.TreeInstanceCount;
				if (Result.TreeInstanceCount >= Spec.MaxTrees)
				{
					bFull = true;
				}
			}
		}

		// One instanced actor per World Partition cell and variant.
		for (const TPair<uint64, TArray<FTransform>>& Pair : Instances)
		{
			const int32 Variant = static_cast<int32>(Pair.Key % 8ULL);
			const int64 Combined = static_cast<int64>(Pair.Key / 8ULL);
			const int32 CellX = static_cast<int32>(Combined / 1000000LL) - 100000;
			const int32 CellY = static_cast<int32>(Combined % 1000000LL) - 100000;
			if (!Variants.IsValidIndex(Variant) || !Trunks.IsValidIndex(Variant) || !Canopies.IsValidIndex(Variant))
			{
				continue;
			}

			AActor* Actor = World->SpawnActor<AActor>(AActor::StaticClass(), FVector::ZeroVector, FRotator::ZeroRotator);
			if (Actor == nullptr)
			{
				continue;
			}
			USceneComponent* Root = NewObject<USceneComponent>(Actor, TEXT("Root"));
			Root->SetMobility(EComponentMobility::Static);
			Actor->SetRootComponent(Root);
			Root->RegisterComponent();
			Actor->AddInstanceComponent(Root);

			UHierarchicalInstancedStaticMeshComponent* Trunk = NewObject<UHierarchicalInstancedStaticMeshComponent>(Actor, TEXT("Trunk"));
			Trunk->SetMobility(EComponentMobility::Static);
			Trunk->AttachToComponent(Root, FAttachmentTransformRules::KeepRelativeTransform);
			Trunk->SetStaticMesh(Trunks[Variant]);
			Trunk->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
			Trunk->SetCanEverAffectNavigation(false);
			Trunk->bUseAsOccluder = false;
			Trunk->InstanceStartCullDistance = 0;
			Trunk->InstanceEndCullDistance = 60000;
			Actor->AddInstanceComponent(Trunk);
			Trunk->RegisterComponent();

			UHierarchicalInstancedStaticMeshComponent* Canopy = NewObject<UHierarchicalInstancedStaticMeshComponent>(Actor, TEXT("Canopy"));
			Canopy->SetMobility(EComponentMobility::Static);
			Canopy->AttachToComponent(Root, FAttachmentTransformRules::KeepRelativeTransform);
			Canopy->SetStaticMesh(Canopies[Variant]);
			Canopy->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			Canopy->SetCanEverAffectNavigation(false);
			Canopy->bUseAsOccluder = false;
			Canopy->InstanceStartCullDistance = 0;
			Canopy->InstanceEndCullDistance = 60000;
			Actor->AddInstanceComponent(Canopy);
			Canopy->RegisterComponent();

			for (const FTransform& Instance : Pair.Value)
			{
				Trunk->AddInstance(Instance, /*bWorldSpace=*/true);
				Canopy->AddInstance(Instance, /*bWorldSpace=*/true);
			}

			const FString Suffix = FString::Chr(TEXT('A') + Variant);
			Actor->SetActorLabel(FString::Printf(TEXT("P4B_Trees_%s_%d_%d"), *Suffix, CellX, CellY));
			Result.CreatedActors.Add(Actor->GetActorLabel());
		}

		for (const TPair<int32, int32>& Pair : PerVariant)
		{
			if (Variants.IsValidIndex(Pair.Key))
			{
				Result.TreeInstancesPerVariant.Add(
					FString::Printf(TEXT("Pine_%s"), *FString::Chr(TEXT('A') + Pair.Key)), Pair.Value);
			}
		}
		Result.TreesInsideOpenArea = TreesInsideWorkArea;
		Result.TreeNearestToPropertyM = (Nearest < FLT_MAX) ? Nearest : 0.f;
		World->MarkPackageDirty();
		Result.bSuccess = Result.TreeInstanceCount > 0;
		Result.Message = FString::Printf(TEXT("%d pine instances in %d instanced actors around (%.0f, %.0f) m"),
			Result.TreeInstanceCount, Result.CreatedActors.Num(), Spec.PropertyCenter.X, Spec.PropertyCenter.Y);
		return Result;
	}
#endif
}

FPhase4BPropertyResult UPhase4BPropertyBuilder::RefineHomeTerrain(UObject* WorldContextObject, const FPhase4BHomeSpec& Spec)
{
	FPhase4BPropertyResult Result;
#if WITH_EDITOR
	UWorld* World = GEngine ? GEngine->GetWorldFromContextObject(WorldContextObject, EGetWorldErrorMode::LogAndReturnNull) : nullptr;
	if (World == nullptr)
	{
		Result.Message = TEXT("no valid editor world");
		return Result;
	}
	Result = Phase4B::RefineHomeTerrainImpl(World, Spec);
#else
	Result.Message = TEXT("the Phase 4B property builder is editor only");
#endif
	return Result;
}

FPhase4BPropertyResult UPhase4BPropertyBuilder::BuildPropertyAssets(UObject* WorldContextObject, const FPhase4BHomeSpec& Spec)
{
	FPhase4BPropertyResult Result;
#if WITH_EDITOR
	UWorld* World = GEngine ? GEngine->GetWorldFromContextObject(WorldContextObject, EGetWorldErrorMode::LogAndReturnNull) : nullptr;
	if (World == nullptr)
	{
		Result.Message = TEXT("no valid editor world");
		return Result;
	}
	Result = Phase4B::BuildPropertyAssetsImpl(World, Spec);
#else
	Result.Message = TEXT("the Phase 4B property builder is editor only");
#endif
	return Result;
}

FPhase4BPropertyResult UPhase4BPropertyBuilder::PlacePineForest(UObject* WorldContextObject, const FPhase4BHomeSpec& Spec)
{
	FPhase4BPropertyResult Result;
#if WITH_EDITOR
	UWorld* World = GEngine ? GEngine->GetWorldFromContextObject(WorldContextObject, EGetWorldErrorMode::LogAndReturnNull) : nullptr;
	if (World == nullptr)
	{
		Result.Message = TEXT("no valid editor world");
		return Result;
	}
	Result = Phase4B::PlacePineForestImpl(World, Spec);
#else
	Result.Message = TEXT("the Phase 4B property builder is editor only");
#endif
	return Result;
}

int32 UPhase4BPropertyBuilder::ClearPropertyActors(UObject* WorldContextObject)
{
#if WITH_EDITOR
	UWorld* World = GEngine ? GEngine->GetWorldFromContextObject(WorldContextObject, EGetWorldErrorMode::LogAndReturnNull) : nullptr;
	return World != nullptr ? Phase4B::ClearPropertyActorsImpl(World) : 0;
#else
	return 0;
#endif
}

float UPhase4BPropertyBuilder::GroundHeightM(UObject* WorldContextObject, float XM, float YM, bool& bHit)
{
	bHit = false;
#if WITH_EDITOR
	UWorld* World = GEngine ? GEngine->GetWorldFromContextObject(WorldContextObject, EGetWorldErrorMode::LogAndReturnNull) : nullptr;
	if (World == nullptr)
	{
		return 0.f;
	}
	return Phase4B::GroundHeightMImpl(World, XM, YM, bHit);
#else
	return 0.f;
#endif
}

