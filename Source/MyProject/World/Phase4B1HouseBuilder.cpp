// Copyright Epic Games, Inc. All Rights Reserved.
// Phase 4B-1 - realistic rural Turkish house (implementation).

#include "World/Phase4B1HouseBuilder.h"

#include "Components/PointLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/PointLight.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Actor.h"
#include "Materials/MaterialInterface.h"
#include "PhysicsEngine/BodySetup.h"
#include "PhysicsEngine/BoxElem.h"
#include "UObject/Package.h"
#include "UObject/SavePackage.h"

#if WITH_EDITOR
#include "AssetRegistry/AssetRegistryModule.h"
#include "MeshDescription.h"
#include "Misc/PackageName.h"
#include "StaticMeshAttributes.h"
#endif

namespace Phase4B1
{
#if WITH_EDITOR
	// ------------------------------------------------------------------
	// Asset folders / material instances (created by the Python step)
	// ------------------------------------------------------------------
	static const FString ArchDir = TEXT("/Game/Game/Environment/House/Architecture");
	static const FString MatDir = TEXT("/Game/Game/Environment/House/Materials");
	static const FString FurnDir = TEXT("/Game/Game/Environment/House/Furniture");
	static const FString PropDir = TEXT("/Game/Game/Environment/House/Props");

	// ------------------------------------------------------------------
	// Floor plan. Local frame: origin = house centre at the pad surface,
	// +X east, +Y north, z = 0 is the terrain pad. All values in meters.
	// Exterior 12.04 x 9.00 m, interior 11.44 x 8.40 = 96.1 m2 net.
	// ------------------------------------------------------------------
	static const float OUT_HX = 6.02f;    // footprint half X
	static const float OUT_HY = 4.50f;    // footprint half Y
	static const float EXT_T = 0.30f;     // exterior wall thickness
	static const float INT_T = 0.12f;     // interior partition thickness
	static const float IN_HX = OUT_HX - EXT_T;   // 5.72 - interior face
	static const float IN_HY = OUT_HY - EXT_T;   // 4.20 - interior face
	static const float FLOOR_Z = 0.45f;          // finished floor level above pad
	static const float CEIL_H = 2.70f;           // clear interior height
	static const float CEIL_T = 0.22f;           // ceiling slab
	static const float EAVE_Z = FLOOR_Z + CEIL_H + CEIL_T;   // 3.37 wall top / eave
	static const float ROOF_T = 0.22f;
	static const float PITCH_TAN = 0.487732f;    // tan(26 deg)
	static const float EAVE_OVER = 0.55f;
	static const float GABLE_OVER = 0.30f;
	static const float RIDGE_UNDER_Z = EAVE_Z + OUT_HY * PITCH_TAN;      // 5.565
	static const float EAVE_TIP_Z = EAVE_Z - EAVE_OVER * PITCH_TAN;      // 3.102
	static const float ROOF_HALF_LEN = OUT_HY + EAVE_OVER;               // 5.05 in Y
	static const float ROOF_SLOPE_LEN = ROOF_HALF_LEN / 0.898794f;       // / cos(26)
	static const float ROOF_SURFACE_TOP_Z = RIDGE_UNDER_Z + ROOF_T / 0.898794f;

	// Corridor spine (north-south).
	static const float SPINE_W = -1.42f;         // corridor west inner face
	static const float SPINE_E = -0.02f;         // corridor east inner face
	static const float SPINE_WX = -1.48f;        // west partition centreline
	static const float SPINE_EX = 0.04f;         // east partition centreline

	/** A room rectangle (inner faces). */
	struct FRoomRect
	{
		const TCHAR* Name;
		float X0;
		float X1;
		float Y0;
		float Y1;
		const TCHAR* Contents;
	};

	static void AddRoom(TArray<FRoomRect>& Rooms, const TCHAR* Name, float X0, float X1, float Y0, float Y1,
	                    const TCHAR* Contents)
	{
		FRoomRect Room;
		Room.Name = Name;
		Room.X0 = X0;
		Room.X1 = X1;
		Room.Y0 = Y0;
		Room.Y1 = Y1;
		Room.Contents = Contents;
		Rooms.Add(Room);
	}

	/** Rooms of the plan; an L shaped room is two rectangles sharing the name. */
	static TArray<FRoomRect> PlanRooms()
	{
		TArray<FRoomRect> Rooms;
		AddRoom(Rooms, TEXT("Salon (living room)"), 0.10f, 5.72f, 1.32f, 4.20f,
			TEXT("sofa, armchair, coffee table, TV + cabinet, rug, curtains, dining table + 4 chairs, sideboard"));
		AddRoom(Rooms, TEXT("Salon (living room)"), 2.32f, 5.72f, -0.30f, 1.20f, TEXT("dining alcove"));
		AddRoom(Rooms, TEXT("Mutfak (kitchen)"), -5.72f, -1.54f, 1.00f, 4.20f,
			TEXT("base run + worktop, sink, upper cabinets, hob, wood range, fridge, dining table + chairs"));
		AddRoom(Rooms, TEXT("Oyuncu yatak odasi (player bedroom)"), -5.72f, -1.54f, -4.20f, -1.02f,
			TEXT("single bed, mattress, pillow, blanket, wardrobe, nightstand, lamp, desk, chair, rug, curtains"));
		AddRoom(Rooms, TEXT("Ebeveyn yatak odasi (parents' bedroom)"), 0.10f, 5.72f, -4.20f, -1.98f,
			TEXT("double bed, 2 nightstands, lamp, dresser, wardrobe, rug, curtains, mirror, chest"));
		AddRoom(Rooms, TEXT("Ebeveyn yatak odasi (parents' bedroom)"), 3.62f, 5.72f, -1.86f, -0.30f,
			TEXT("wardrobe nook"));
		AddRoom(Rooms, TEXT("Banyo (bathroom)"), -5.72f, -1.54f, -0.90f, 0.88f,
			TEXT("shower cabin, WC, basin, mirror, storage cabinet, towel rail, privacy window"));
		AddRoom(Rooms, TEXT("WC"), 0.10f, 2.20f, -0.18f, 1.20f,
			TEXT("WC, small basin, mirror, extract grille"));
		AddRoom(Rooms, TEXT("Kiler (pantry)"), 0.10f, 3.50f, -1.86f, -0.30f,
			TEXT("shelf units, jars, crates, flour bin, baskets, household supplies"));
		AddRoom(Rooms, TEXT("Giris holu + koridor (hall/corridor)"), -1.42f, -0.02f, -4.20f, 4.20f,
			TEXT("shoe cabinet, coat rack, hall mirror, doormat, ceiling lights, access to every room"));
		return Rooms;
	}

	// ------------------------------------------------------------------
	// Openings: a wall is built from the walls in WallRuns(); every opening is
	// listed once with its wall, its extent along that wall and its heights.
	// ------------------------------------------------------------------
	enum class EWallSide : uint8
	{
		North,
		South,
		West,
		East
	};

	/** A vertical opening (door or window) in a wall run. */
	struct FOpening
	{
		const TCHAR* Id = TEXT("");
		EWallSide Side = EWallSide::North;
		/** Extent along the wall axis: local X for N/S walls, local Y for W/E. */
		float From = 0.f;
		float To = 0.f;
		/** Sill height above the finished floor (doors: 0). */
		float Sill = 0.f;
		float Height = 2.05f;
		bool bDoor = false;
		bool bLeaf = true;       // gets a swing leaf actor
		const TCHAR* Room = TEXT("");
	};

	/** Plan openings: 2 exterior doors, 6 interior doors, 1 cased opening, 9 windows. */
	static TArray<FOpening> PlanOpenings()
	{
		TArray<FOpening> O;
		auto Add = [&O](const TCHAR* Id, EWallSide Side, float From, float To, float Sill, float Height,
		                bool bDoor, bool bLeaf, const TCHAR* Room)
		{
			FOpening Entry;
			Entry.Id = Id;
			Entry.Side = Side;
			Entry.From = From;
			Entry.To = To;
			Entry.Sill = Sill;
			Entry.Height = Height;
			Entry.bDoor = bDoor;
			Entry.bLeaf = bLeaf;
			Entry.Room = Room;
			O.Add(Entry);
		};

		// --- exterior doors
		Add(TEXT("Door_Front"), EWallSide::North, -1.20f, -0.20f, 0.f, 2.10f, true, true, TEXT("Giris holu"));
		Add(TEXT("Door_Rear"), EWallSide::South, -1.20f, -0.20f, 0.f, 2.05f, true, true, TEXT("Koridor"));
		// --- windows (large in the salon, medium in the rooms, small and high in wet rooms)
		Add(TEXT("Win_Salon_N"), EWallSide::North, 1.60f, 3.40f, 0.90f, 1.50f, false, false, TEXT("Salon"));
		Add(TEXT("Win_Salon_E"), EWallSide::East, 2.00f, 3.40f, 0.90f, 1.50f, false, false, TEXT("Salon"));
		Add(TEXT("Win_Kitchen_N"), EWallSide::North, -4.60f, -3.20f, 0.95f, 1.40f, false, false, TEXT("Mutfak"));
		Add(TEXT("Win_Kitchen_W"), EWallSide::West, 2.20f, 3.40f, 0.95f, 1.40f, false, false, TEXT("Mutfak"));
		Add(TEXT("Win_Player_W"), EWallSide::West, -3.20f, -1.80f, 0.95f, 1.40f, false, false, TEXT("Oyuncu YO"));
		Add(TEXT("Win_Player_S"), EWallSide::South, -4.60f, -3.20f, 0.95f, 1.40f, false, false, TEXT("Oyuncu YO"));
		Add(TEXT("Win_Parents_S"), EWallSide::South, 2.20f, 3.60f, 0.95f, 1.40f, false, false, TEXT("Ebeveyn YO"));
		Add(TEXT("Win_Parents_E"), EWallSide::East, -3.60f, -2.40f, 0.95f, 1.40f, false, false, TEXT("Ebeveyn YO"));
		Add(TEXT("Win_Bath_W"), EWallSide::West, -0.45f, 0.15f, 1.55f, 0.60f, false, false, TEXT("Banyo"));
		// --- interior doors (all open off the hall / central corridor)
		Add(TEXT("Door_Kitchen"), EWallSide::West, 1.60f, 2.45f, 0.f, 2.05f, true, true, TEXT("Mutfak"));
		Add(TEXT("Door_Bath"), EWallSide::West, -0.50f, 0.35f, 0.f, 2.05f, true, true, TEXT("Banyo"));
		Add(TEXT("Door_Player"), EWallSide::West, -3.40f, -2.55f, 0.f, 2.05f, true, true, TEXT("Oyuncu YO"));
		Add(TEXT("Door_WC"), EWallSide::East, -0.05f, 0.70f, 0.f, 2.05f, true, true, TEXT("WC"));
		Add(TEXT("Door_Pantry"), EWallSide::East, -1.75f, -1.00f, 0.f, 2.05f, true, true, TEXT("Kiler"));
		Add(TEXT("Door_Parents"), EWallSide::East, -3.30f, -2.45f, 0.f, 2.05f, true, true, TEXT("Ebeveyn YO"));
		// --- wide cased opening: hall/corridor -> salon
		Add(TEXT("Opening_Salon"), EWallSide::East, 1.50f, 2.70f, 0.f, 2.10f, true, false, TEXT("Salon"));
		return O;
	}

	// ------------------------------------------------------------------
	// Procedural mesh building. Every piece is authored in the local house
	// frame (meters) and every solid box also registers a box collision
	// element, so walls, floors and furniture are physically solid while
	// door and window openings stay real holes.
	// ------------------------------------------------------------------
	struct FWallOpening
	{
		float AlongMin = 0.f;
		float AlongMax = 0.f;
		float ZMin = 0.f;
		float ZMax = 0.f;
	};

	/** Planar UV in meters (the house materials are parametric, meter scaled). */
	static FVector2D PlanarUV(const FVector& P, const FVector& N)
	{
		const FVector Abs(FMath::Abs(N.X), FMath::Abs(N.Y), FMath::Abs(N.Z));
		if (Abs.X >= Abs.Y && Abs.X >= Abs.Z)
		{
			return FVector2D(P.Y, P.Z);
		}
		return (Abs.Y >= Abs.Z) ? FVector2D(P.X, P.Z) : FVector2D(P.X, P.Y);
	}

	/** One box collision element (mesh space, cm). */
	struct FBoxRecord
	{
		FVector Center = FVector::ZeroVector;
		FRotator Rotation = FRotator::ZeroRotator;
		FVector Extent = FVector::ZeroVector;
	};

	struct FMeshBuilder
	{
		FMeshDescription Description;
		FStaticMeshAttributes Attributes;
		TArray<FName> SlotNames;
		TMap<FName, FPolygonGroupID> Groups;
		TArray<FBoxRecord> CollisionBoxes;
		bool bTrackCollision = true;
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

		/** Registers a box collision element (half sizes in meters). */
		void Collide(const FVector& Center, const FVector& HalfSize, const FRotator& Rot = FRotator::ZeroRotator)
		{
			if (!bTrackCollision)
			{
				return;
			}
			FBoxRecord Record;
			Record.Center = Center * 100.f;
			Record.Rotation = Rot;
			Record.Extent = HalfSize * 200.f;
			CollisionBoxes.Add(Record);
		}

		/** Axis aligned (optionally rotated) box with planar UVs and box collision. */
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

			Quad(P001, P101, P111, P011, SlotIndex);
			if (!bSkipBottom)
			{
				Quad(P000, P010, P110, P100, SlotIndex);
			}
			Quad(P100, P110, P111, P101, SlotIndex);
			Quad(P000, P001, P011, P010, SlotIndex);
			Quad(P010, P011, P111, P110, SlotIndex);
			Quad(P000, P100, P101, P001, SlotIndex);
			Collide(Center, HalfSize, Rot);
		}

		/** Horizontal floor / ceiling slab from four corners (top surface + edges). */
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
			// A slab is one collision box per rectangle (centre + half size).
			const FVector2D Centre = (P00 + P11) * 0.5f;
			Collide(FVector(Centre.X, Centre.Y, TopZ - Thickness * 0.5f),
				FVector(FMath::Abs(P11.X - P00.X) * 0.5f, FMath::Abs(P11.Y - P00.Y) * 0.5f, Thickness * 0.5f));
		}

		/** Rectangular floor / ceiling slab (X0..X1, Y0..Y1). */
		void FlatSlab(float X0, float X1, float Y0, float Y1, float TopZ, float Thickness, int32 SlotIndex)
		{
			Slab(FVector2D(X0, Y0), FVector2D(X1, Y0), FVector2D(X1, Y1), FVector2D(X0, Y1), TopZ, Thickness, SlotIndex);
		}

		/** Prism from a convex cross section in the local YZ plane, extruded along X. */
		void ExtrudeProfile(const TArray<FVector2D>& CrossSectionYZ, float XMin, float XMax,
		                    int32 SlotIndex, bool bCollide)
		{
			if (CrossSectionYZ.Num() < 3)
			{
				return;
			}
			auto At = [](float X, const FVector2D& YZ) { return FVector(X, YZ.X, YZ.Y); };
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
			if (bCollide)
			{
				// Conservative box around the prism.
				FBox Bounds(ForceInit);
				for (const FVector2D& Point : CrossSectionYZ)
				{
					Bounds += FVector(XMin, Point.X, Point.Y);
					Bounds += FVector(XMax, Point.X, Point.Y);
				}
				Box(Bounds.GetCenter(), Bounds.GetExtent(), SlotIndex, FRotator::ZeroRotator, true);
			}
		}

		/** Tapered cylinder between two points (pipes, chimney pots, lamp stems). */
		void Cylinder(const FVector& Base, const FVector& Top, float RadiusBase, float RadiusTop,
		              int32 Segments, int32 SlotIndex)
		{
			Segments = FMath::Clamp(Segments, 3, 32);
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
			TArray<FVector> BaseRing;
			TArray<FVector> TopRing;
			for (int32 Index = 0; Index < Segments; ++Index)
			{
				const float Angle = 2.f * PI * Index / static_cast<float>(Segments);
				const FVector Radial = Side * FMath::Cos(Angle) + Side2 * FMath::Sin(Angle);
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
			// Solid enough that the player cannot walk through a pipe or flue.
			Collide((Base + Top) * 0.5f,
				FVector(FMath::Max(RadiusBase, RadiusTop), FMath::Max(RadiusBase, RadiusTop), Height * 0.5f));
		}

		/**
		 * Straight wall built from solid panels around real openings (thickness is
		 * centered on the A->B line). Returns the number of panels created.
		 */
		int32 Wall(const FVector2D& A, const FVector2D& B, float ZBase, float ZTop, float Thickness,
		           const TArray<FWallOpening>& Openings, int32 SlotIndex)
		{
			int32 Panels = 0;
			const FVector2D Axis2D = B - A;
			const float Length = Axis2D.Size();
			if (Length <= KINDA_SMALL_NUMBER || ZTop <= ZBase)
			{
				return 0;
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
						FVector(Width * 0.5f, Thickness * 0.5f, Height * 0.5f), SlotIndex,
						FRotator(0.f, YawDeg, 0.f));
					++Panels;
				}
			}
			return Panels;
		}

		/**
		 * Window / door unit inside a wall opening: joinery frame, glazing with muntins
		 * (windows), exterior stone sill, interior window board and casings on both wall
		 * faces. Coordinates match Wall().
		 */
		void OpeningUnit(const FVector2D& A, const FVector2D& B, float Thickness, const FWallOpening& Opening,
		                 int32 FrameSlot, int32 PaneSlot, bool bWindow, float FrameSize)
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
			const float FrameDepth = Thickness * 0.5f + 0.025f;

			auto Place = [&A, &Dir, &Side](float Along, float Offset)
			{
				const FVector2D P = A + Dir * Along + Side * Offset;
				return FVector(P.X, P.Y, 0.f);
			};

			// Joinery: two jambs, a head and (windows) a bottom rail.
			const FVector Left = Place(Opening.AlongMin + FrameHalf, 0.f);
			const FVector Right = Place(Opening.AlongMax - FrameHalf, 0.f);
			const FVector Center = Place(CenterAlong, 0.f);
			Box(Left + FVector(0.f, 0.f, MidZ), FVector(FrameHalf, FrameDepth, Height * 0.5f), FrameSlot, Rot);
			Box(Right + FVector(0.f, 0.f, MidZ), FVector(FrameHalf, FrameDepth, Height * 0.5f), FrameSlot, Rot);
			Box(Center + FVector(0.f, 0.f, Opening.ZMax - FrameHalf),
				FVector(Width * 0.5f, FrameDepth, FrameHalf), FrameSlot, Rot);
			if (bWindow)
			{
				Box(Center + FVector(0.f, 0.f, Opening.ZMin + FrameHalf),
					FVector(Width * 0.5f, FrameDepth, FrameHalf), FrameSlot, Rot);
			}

			if (bWindow)
			{
				// Glazing plus a simple cross of muntins.
				if (PaneSlot >= 0)
				{
					Box(Center + FVector(0.f, 0.f, MidZ),
						FVector(FMath::Max(0.03f, Width * 0.5f - FrameSize), 0.012f,
							FMath::Max(0.03f, Height * 0.5f - FrameSize)), PaneSlot, Rot);
				}
				const bool bWasTracking = bTrackCollision;
				bTrackCollision = false;   // glazing does not block the player
				Box(Center + FVector(0.f, -0.02f, MidZ),
					FVector(0.022f, 0.022f, Height * 0.5f - FrameSize), FrameSlot, Rot);
				Box(Center + FVector(0.f, -0.02f, MidZ),
					FVector(Width * 0.5f - FrameSize, 0.022f, 0.022f), FrameSlot, Rot);
				bTrackCollision = bWasTracking;

				// Exterior stone sill and interior window board.
				const FVector Outer = Place(CenterAlong, -Thickness * 0.5f - 0.07f);
				Box(Outer + FVector(0.f, 0.f, Opening.ZMin - 0.025f),
					FVector(Width * 0.5f + 0.10f, 0.085f, 0.035f), FrameSlot, Rot);
				const FVector Inner = Place(CenterAlong, Thickness * 0.5f + 0.14f);
				Box(Inner + FVector(0.f, 0.f, Opening.ZMin - 0.012f),
					FVector(Width * 0.5f + 0.06f, 0.145f, 0.022f), FrameSlot, Rot);
			}

			// Casings on both wall faces (thin trim boards around the opening).
			for (int32 FaceIndex = 0; FaceIndex < 2; ++FaceIndex)
			{
				const float Offset = (FaceIndex == 0 ? 1.f : -1.f) * (Thickness * 0.5f + 0.012f);
				const FVector BoardLeft = Place(Opening.AlongMin - 0.035f, Offset);
				const FVector BoardRight = Place(Opening.AlongMax + 0.035f, Offset);
				const FVector BoardTop = Place(CenterAlong, Offset);
				Box(BoardLeft + FVector(0.f, 0.f, MidZ), FVector(0.035f, 0.012f, Height * 0.5f + 0.035f), FrameSlot, Rot);
				Box(BoardRight + FVector(0.f, 0.f, MidZ), FVector(0.035f, 0.012f, Height * 0.5f + 0.035f), FrameSlot, Rot);
				Box(BoardTop + FVector(0.f, 0.f, Opening.ZMax + 0.035f),
					FVector(Width * 0.5f + 0.07f, 0.012f, 0.035f), FrameSlot, Rot);
			}
		}

		/** Decorative trim segment along the local X or Y axis (no collision). */
		void AddTrimSegment(bool bAlongX, float Fixed, float From, float To, float ZMin, float Height,
		                    float Thickness, int32 SlotIndex)
		{
			const float Centre = (From + To) * 0.5f;
			const float HalfLength = FMath::Max(0.01f, (To - From) * 0.5f);
			const FVector Centre3 = bAlongX ? FVector(Centre, Fixed, ZMin + Height * 0.5f)
			                                : FVector(Fixed, Centre, ZMin + Height * 0.5f);
			const FVector Half3 = bAlongX ? FVector(HalfLength, Thickness * 0.5f, Height * 0.5f)
			                              : FVector(Thickness * 0.5f, HalfLength, Height * 0.5f);
			const bool bWasTracking = bTrackCollision;
			bTrackCollision = false;
			Box(Centre3, Half3, SlotIndex);
			bTrackCollision = bWasTracking;
		}
	};

	// ------------------------------------------------------------------
	// Asset creation
	// ------------------------------------------------------------------
	struct FMaterialSet
	{
		TMap<FName, UMaterialInterface*> BySlot;
		TArray<FString> Missing;

		void Load(const TCHAR* SlotName)
		{
			const FString ObjectPath = FString::Printf(TEXT("%s/%s.%s"), *MatDir, SlotName, SlotName);
			UMaterialInterface* Material = LoadObject<UMaterialInterface>(nullptr, *ObjectPath);
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

	static FMaterialSet LoadHouseMaterials()
	{
		FMaterialSet Set;
		const TCHAR* Names[] =
		{
			TEXT("MI_Plaster"), TEXT("MI_WallPaint"), TEXT("MI_Ceiling"), TEXT("MI_FloorWood"),
			TEXT("MI_FloorTile"), TEXT("MI_Concrete"), TEXT("MI_StoneBase"), TEXT("MI_RoofTile"),
			TEXT("MI_WoodTrim"), TEXT("MI_WoodDark"), TEXT("MI_DoorInt"), TEXT("MI_DoorExt"),
			TEXT("MI_Metal"), TEXT("MI_WhiteMetal"), TEXT("MI_Glass"), TEXT("MI_Fabric"),
			TEXT("MI_FabricRed"), TEXT("MI_Carpet"), TEXT("MI_Counter"), TEXT("MI_Ceramic"),
			TEXT("MI_Mirror"), TEXT("MI_LampShade"), TEXT("MI_Curtain"), TEXT("MI_Mattress"),
		};
		for (const TCHAR* Name : Names)
		{
			Set.Load(Name);
		}
		return Set;
	}

	/** Creates (or replaces) a static mesh asset from a mesh description. */
	static UStaticMesh* CreateStaticMeshAsset(const FString& Dir, const FString& AssetName, FMeshBuilder& Builder,
	                                          const FMaterialSet& Materials, TArray<FString>& OutWarnings)
	{
		const FString ObjectPath = FString::Printf(TEXT("%s/%s.%s"), *Dir, *AssetName, *AssetName);
		if (UObject* Existing = LoadObject<UObject>(nullptr, *ObjectPath))
		{
			Existing->ClearFlags(RF_Public | RF_Standalone);
			Existing->Rename(nullptr, GetTransientPackage(), REN_DontCreateRedirectors);
		}

		UPackage* Package = CreatePackage(*FString::Printf(TEXT("%s/%s"), *Dir, *AssetName));
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
			Mesh->GetStaticMaterials().Add(FStaticMaterial(Materials.Get(SlotName), SlotName, SlotName));
		}

		UStaticMesh::FBuildMeshDescriptionsParams Params;
		Params.bMarkPackageDirty = true;
		Params.bBuildSimpleCollision = false;   // box elements are added below
		Params.bCommitMeshDescription = true;
		Params.bFastBuild = false;
		if (!Mesh->BuildFromMeshDescriptions({ &Builder.Description }, Params))
		{
			OutWarnings.Add(FString::Printf(TEXT("BuildFromMeshDescriptions failed for %s"), *AssetName));
			return nullptr;
		}

		// Simple collision: one box element per authored piece. A single convex hull
		// would fill the whole house, so every wall panel, slab and furniture part
		// keeps its own exact box.
		UBodySetup* Body = Mesh->GetBodySetup();
		if (Body == nullptr)
		{
			Mesh->CreateBodySetup();
			Body = Mesh->GetBodySetup();
		}
		if (Body != nullptr)
		{
			Body->AggGeom.BoxElems.Reset();
			Body->AggGeom.ConvexElems.Reset();
			for (const FBoxRecord& Record : Builder.CollisionBoxes)
			{
				FKBoxElem& Elem = Body->AggGeom.BoxElems.AddDefaulted_GetRef();
				Elem.Center = Record.Center;
				Elem.Rotation = Record.Rotation;
				Elem.X = FMath::Max(1.f, Record.Extent.X);
				Elem.Y = FMath::Max(1.f, Record.Extent.Y);
				Elem.Z = FMath::Max(1.f, Record.Extent.Z);
			}
			Body->CollisionTraceFlag = ECollisionTraceFlag::CTF_UseSimpleAsComplex;
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
	// Wall runs: a run is the centreline of one wall plus the openings that
	// belong to it. Coordinates are local meters, Z is mesh space (pad = 0).
	// ------------------------------------------------------------------
	struct FWallRun
	{
		EWallSide Side = EWallSide::North;
		FVector2D A = FVector2D::ZeroVector;
		FVector2D B = FVector2D::ZeroVector;
		float Thickness = EXT_T;
		int32 Slot = 0;
		TArray<FWallOpening> Openings;

		/** Along-wall coordinate of a local axis coordinate (X for N/S, Y for W/E). */
		float Along(float Coord) const
		{
			switch (Side)
			{
			case EWallSide::North: return Coord - A.X;
			case EWallSide::South: return A.X - Coord;
			case EWallSide::West:  return Coord - A.Y;
			default:               return A.Y - Coord;   // East
			}
		}

		void AddOpening(float From, float To, float Sill, float Height, float ZBase)
		{
			FWallOpening W;
			W.AlongMin = FMath::Min(Along(From), Along(To));
			W.AlongMax = FMath::Max(Along(From), Along(To));
			W.ZMin = ZBase + Sill;
			W.ZMax = ZBase + Sill + Height;
			Openings.Add(W);
		}
	};

	/** Centrelines of the four exterior walls (outer faces on the footprint). */
	static void ExteriorRun(EWallSide Side, FWallRun& Run)
	{
		Run.Side = Side;
		Run.Thickness = EXT_T;
		const float Half = EXT_T * 0.5f;
		switch (Side)
		{
		case EWallSide::North:
			Run.A.Set(-OUT_HX, OUT_HY - Half);
			Run.B.Set(OUT_HX, OUT_HY - Half);
			break;
		case EWallSide::South:
			Run.A.Set(OUT_HX, -OUT_HY + Half);
			Run.B.Set(-OUT_HX, -OUT_HY + Half);
			break;
		case EWallSide::West:
			Run.A.Set(-OUT_HX + Half, -OUT_HY);
			Run.B.Set(-OUT_HX + Half, OUT_HY);
			break;
		default:
			Run.A.Set(OUT_HX - Half, OUT_HY);
			Run.B.Set(OUT_HX - Half, -OUT_HY);
			break;
		}
	}

	/** Centrelines of the four interior linings of the exterior walls. */
	static void LiningRun(EWallSide Side, FWallRun& Run)
	{
		Run.Side = Side;
		Run.Thickness = 0.03f;
		const float Half = 0.015f;
		switch (Side)
		{
		case EWallSide::North:
			Run.A.Set(-IN_HX, IN_HY - Half);
			Run.B.Set(IN_HX, IN_HY - Half);
			break;
		case EWallSide::South:
			Run.A.Set(IN_HX, -IN_HY + Half);
			Run.B.Set(-IN_HX, -IN_HY + Half);
			break;
		case EWallSide::West:
			Run.A.Set(-IN_HX + Half, -IN_HY);
			Run.B.Set(-IN_HX + Half, IN_HY);
			break;
		default:
			Run.A.Set(IN_HX - Half, IN_HY);
			Run.B.Set(IN_HX - Half, -IN_HY);
			break;
		}
	}

	/** The nine interior partitions of the plan (centrelines, thickness 0.12). */
	static TArray<FWallRun> InteriorRuns()
	{
		TArray<FWallRun> Runs;
		const float Tie = 0.18f;   // overlaps into the neighbouring wall

		auto Make = [&Runs](EWallSide Side, float Ax, float Ay, float Bx, float By)
		{
			FWallRun Run;
			Run.Side = Side;   // only used for the along-wall maths
			Run.A.Set(Ax, Ay);
			Run.B.Set(Bx, By);
			Run.Thickness = INT_T;
			Runs.Add(Run);
			return Runs.Num() - 1;
		};

		// P1 corridor west wall: kitchen, bathroom, player bedroom doors.
		{
			const int32 Index = Make(EWallSide::West, SPINE_WX, -IN_HY - Tie, SPINE_WX, IN_HY + Tie);
			Runs[Index].AddOpening(1.60f, 2.45f, 0.f, 2.05f, FLOOR_Z);   // kitchen
			Runs[Index].AddOpening(-0.50f, 0.35f, 0.f, 2.05f, FLOOR_Z);  // bathroom
			Runs[Index].AddOpening(-3.40f, -2.55f, 0.f, 2.05f, FLOOR_Z); // player bedroom
		}
		// P2 corridor east wall: salon opening, WC, pantry, parents' bedroom.
		{
			const int32 Index = Make(EWallSide::West, SPINE_EX, -IN_HY - Tie, SPINE_EX, IN_HY + Tie);
			Runs[Index].AddOpening(1.50f, 2.70f, 0.f, 2.10f, FLOOR_Z);   // salon (cased opening)
			Runs[Index].AddOpening(-0.05f, 0.70f, 0.f, 2.05f, FLOOR_Z);  // WC
			Runs[Index].AddOpening(-1.75f, -1.00f, 0.f, 2.05f, FLOOR_Z); // pantry
			Runs[Index].AddOpening(-3.30f, -2.45f, 0.f, 2.05f, FLOOR_Z); // parents' bedroom
		}
		// P3 kitchen / bathroom, P4 bathroom / player bedroom.
		Make(EWallSide::North, -IN_HX, 0.94f, SPINE_W - 0.04f, 0.94f);
		Make(EWallSide::North, -IN_HX, -0.96f, SPINE_W - 0.04f, -0.96f);
		// P5 salon / WC, P6 WC east wall.
		Make(EWallSide::North, SPINE_E + 0.08f, 1.26f, 2.26f, 1.26f);
		Make(EWallSide::West, 2.26f, -0.24f, 2.26f, 1.26f);
		// P7 WC / alcove / wardrobe nook, P8 pantry east wall, P9 parents' north wall.
		Make(EWallSide::North, SPINE_E + 0.08f, -0.24f, IN_HX, -0.24f);
		Make(EWallSide::West, 3.56f, -1.92f, 3.56f, -0.24f);
		Make(EWallSide::North, SPINE_E + 0.08f, -1.92f, 3.56f, -1.92f);
		return Runs;
	}

	static TArray<FWallRun> ExteriorRuns()
	{
		TArray<FWallRun> Runs;
		const EWallSide Sides[4] = { EWallSide::North, EWallSide::South, EWallSide::West, EWallSide::East };
		for (EWallSide Side : Sides)
		{
			FWallRun Run;
			ExteriorRun(Side, Run);
			Runs.Add(Run);
		}
		return Runs;
	}

	static TArray<FWallRun> LiningRuns()
	{
		TArray<FWallRun> Runs;
		const EWallSide Sides[4] = { EWallSide::North, EWallSide::South, EWallSide::West, EWallSide::East };
		for (EWallSide Side : Sides)
		{
			FWallRun Run;
			LiningRun(Side, Run);
			Runs.Add(Run);
		}
		return Runs;
	}

	static bool IsInteriorOpening(const FOpening& Opening);

	/** Copies the plan openings into the matching runs of a wall set. */
	static void ApplyPlanOpenings(const TArray<FOpening>& Plan, TArray<FWallRun>& Runs)
	{
		for (const FOpening& Opening : Plan)
		{
			if (IsInteriorOpening(Opening))
			{
				continue;   // interior doors belong to the partitions, not to the facade
			}
			for (FWallRun& Run : Runs)
			{
				if (Run.Side == Opening.Side)
				{
					Run.AddOpening(Opening.From, Opening.To, Opening.Sill, Opening.Height, FLOOR_Z);
					break;
				}
			}
		}
	}

	/**
	 * Shell geometry: exterior walls with real openings, the interior linings of
	 * those walls and the two gable end triangles above the eaves. The exterior
	 * wall mesh gets plaster on the outside, the lining mesh the interior paint.
	 */
	static void BuildShellGeometry(const TArray<FOpening>& Plan, FMeshBuilder& Ext, FMeshBuilder& Int,
	                              int32& OutExtPanels, int32& OutIntPanels)
	{
		const int32 SPlaster = Ext.Slot(TEXT("MI_Plaster"));
		const int32 SPaint = Int.Slot(TEXT("MI_WallPaint"));

		TArray<FWallRun> Runs = ExteriorRuns();
		ApplyPlanOpenings(Plan, Runs);
		for (FWallRun& Run : Runs)
		{
			OutExtPanels += Ext.Wall(Run.A, Run.B, FLOOR_Z, EAVE_Z, Run.Thickness, Run.Openings, SPlaster);
		}

		TArray<FWallRun> Linings = LiningRuns();
		ApplyPlanOpenings(Plan, Linings);
		for (FWallRun& Run : Linings)
		{
			OutIntPanels += Int.Wall(Run.A, Run.B, FLOOR_Z, EAVE_Z, Run.Thickness, Run.Openings, SPaint);
		}

		// Interior partitions with their door openings.
		for (const FWallRun& Run : InteriorRuns())
		{
			OutIntPanels += Int.Wall(Run.A, Run.B, FLOOR_Z, EAVE_Z, Run.Thickness, Run.Openings, SPaint);
		}

		// Gable ends: the triangle above the eave at both short walls.
		TArray<FVector2D> Profile;
		Profile.Add(FVector2D(-IN_HY, EAVE_Z));
		Profile.Add(FVector2D(IN_HY, EAVE_Z));
		Profile.Add(FVector2D(0.f, RIDGE_UNDER_Z));
		Ext.ExtrudeProfile(Profile, IN_HX, OUT_HX, SPlaster, false);
		Ext.ExtrudeProfile(Profile, -OUT_HX, -IN_HX, SPlaster, false);
	}

	/** Foundation, plinth, structural floor slab, rear landing and steps. */
	static void BuildFoundation(FMeshBuilder& B)
	{
		const int32 SConcrete = B.Slot(TEXT("MI_Concrete"));
		const int32 SStone = B.Slot(TEXT("MI_StoneBase"));

		// Plinth: reaches below grade so the house never floats.
		B.Box(FVector(0.f, 0.f, -0.20f), FVector(OUT_HX + 0.15f, OUT_HY + 0.15f, 0.50f), SConcrete);
		// Stone skirt band just above grade.
		B.Box(FVector(0.f, 0.f, 0.14f), FVector(OUT_HX + 0.21f, OUT_HY + 0.21f, 0.14f), SStone);
		// Structural floor slab under the finished floors.
		B.Box(FVector(0.f, 0.f, 0.35f), FVector(OUT_HX, OUT_HY, 0.05f), SConcrete);
		// Entrance threshold step at the front door (the veranda deck is 0.30 high).
		B.Box(FVector(-0.70f, 4.72f, 0.375f), FVector(0.70f, 0.22f, 0.075f), SStone);
		// Rear landing and two steps down to the yard.
		B.Box(FVector(-1.20f, -5.10f, 0.15f), FVector(1.10f, 0.60f, 0.15f), SStone);
		B.Box(FVector(-1.20f, -5.85f, 0.10f), FVector(1.10f, 0.15f, 0.10f), SStone);
		B.Box(FVector(-1.20f, -6.15f, 0.05f), FVector(1.10f, 0.15f, 0.05f), SStone);
	}

	/** Finished interior floors (timber in the rooms, tiles in the wet rooms). */
	static void BuildFloorFinishes(FMeshBuilder& B)
	{
		const int32 SWood = B.Slot(TEXT("MI_FloorWood"));
		const int32 STile = B.Slot(TEXT("MI_FloorTile"));
		const TArray<FRoomRect> Rooms = PlanRooms();
		for (int32 Index = 0; Index < Rooms.Num(); ++Index)
		{
			const FRoomRect& Room = Rooms[Index];
			// Plan order: 2 = kitchen, 6 = bathroom, 7 = WC, 8 = pantry.
			const bool bWet = (Index == 2 || Index == 6 || Index == 7 || Index == 8);
			B.FlatSlab(Room.X0 - 0.03f, Room.X1 + 0.03f, Room.Y0 - 0.03f, Room.Y1 + 0.03f,
				FLOOR_Z, 0.05f, bWet ? STile : SWood);
		}
	}

	/** Ceiling slabs (one per room) plus exposed beams in the salon. */
	static void BuildCeilings(FMeshBuilder& B)
	{
		const int32 SCeil = B.Slot(TEXT("MI_Ceiling"));
		const int32 SBeam = B.Slot(TEXT("MI_WoodDark"));
		const TArray<FRoomRect> Rooms = PlanRooms();
		for (const FRoomRect& Room : Rooms)
		{
			B.FlatSlab(Room.X0 - 0.05f, Room.X1 + 0.05f, Room.Y0 - 0.05f, Room.Y1 + 0.05f,
				EAVE_Z, CEIL_T, SCeil);
		}

		// Exposed timber beams under the salon ceiling (visual only).
		const bool bWasTracking = B.bTrackCollision;
		B.bTrackCollision = false;
		const float BeamZ = FLOOR_Z + CEIL_H - 0.07f;
		for (int32 Index = 0; Index < 3; ++Index)
		{
			const float Y = 1.95f + Index * 0.85f;
			B.Box(FVector(2.91f, Y, BeamZ), FVector(2.81f, 0.07f, 0.07f), SBeam);
		}
		B.bTrackCollision = bWasTracking;
	}

	/** Pitched gable roof: two slopes, ridge cap, fascias, barge boards, gutters, pipes. */
	static void BuildRoof(FMeshBuilder& B)
	{
		const int32 SRoof = B.Slot(TEXT("MI_RoofTile"));
		const int32 SWood = B.Slot(TEXT("MI_WoodTrim"));
		const int32 SMetal = B.Slot(TEXT("MI_Metal"));

		const float HalfSpanX = OUT_HX + GABLE_OVER;        // 6.32
		const float SlopeHalf = ROOF_SLOPE_LEN * 0.5f;      // half length along the slope
		const float MidY = ROOF_HALF_LEN * 0.5f;            // 2.525
		const float MidZ = EAVE_Z + (OUT_HY - MidY) * PITCH_TAN;
		const float HalfT = ROOF_T * 0.5f;
		const float Sin = 0.438371f;                        // sin(26)
		const float Cos = 0.898794f;                        // cos(26)

		// Slopes: +Z of the box tilts towards +Y (roll -26) resp. -Y (roll +26).
		B.Box(FVector(0.f, MidY + HalfT * Sin, MidZ + HalfT * Cos),
			FVector(HalfSpanX, SlopeHalf, HalfT), SRoof, FRotator(0.f, 0.f, -26.f));
		B.Box(FVector(0.f, -(MidY + HalfT * Sin), MidZ + HalfT * Cos),
			FVector(HalfSpanX, SlopeHalf, HalfT), SRoof, FRotator(0.f, 0.f, 26.f));

		// Ridge cap closing the two slopes.
		B.Box(FVector(0.f, 0.f, RIDGE_UNDER_Z + ROOF_T / Cos + 0.14f), FVector(HalfSpanX + 0.02f, 0.17f, 0.16f), SRoof);

		// Fascia boards and gutters along both eaves.
		for (int32 Index = 0; Index < 2; ++Index)
		{
			const float Sign = (Index == 0) ? 1.f : -1.f;
			B.Box(FVector(0.f, Sign * ROOF_HALF_LEN, EAVE_TIP_Z + 0.05f), FVector(HalfSpanX, 0.035f, 0.20f), SWood);
			B.Box(FVector(0.f, Sign * (ROOF_HALF_LEN + 0.10f), EAVE_TIP_Z - 0.18f),
				FVector(HalfSpanX, 0.075f, 0.075f), SMetal);
			// Barge boards along the gable edges.
			B.Box(FVector(HalfSpanX - 0.02f, Sign * (MidY + HalfT * Sin), MidZ + HalfT * Cos - 0.06f),
				FVector(0.03f, SlopeHalf, 0.18f), SWood, FRotator(0.f, 0.f, Sign > 0.f ? -26.f : 26.f));
			B.Box(FVector(-(HalfSpanX - 0.02f), Sign * (MidY + HalfT * Sin), MidZ + HalfT * Cos - 0.06f),
				FVector(0.03f, SlopeHalf, 0.18f), SWood, FRotator(0.f, 0.f, Sign > 0.f ? -26.f : 26.f));
		}

		// Four downpipes from the gutters down the gable walls.
		for (int32 XIndex = 0; XIndex < 2; ++XIndex)
		{
			for (int32 YIndex = 0; YIndex < 2; ++YIndex)
			{
				const float X = (XIndex == 0) ? (OUT_HX + 0.10f) : -(OUT_HX + 0.10f);
				const float Y = (YIndex == 0) ? (ROOF_HALF_LEN + 0.10f) : -(ROOF_HALF_LEN + 0.10f);
				B.Cylinder(FVector(X, Y, EAVE_TIP_Z - 0.20f), FVector(X, Y, 0.30f), 0.055f, 0.055f, 10, SMetal);
			}
		}
	}

	/** Masonry chimney of the kitchen range, passing through the roof. */
	static void BuildChimney(FMeshBuilder& B)
	{
		const int32 SPlaster = B.Slot(TEXT("MI_Plaster"));
		const int32 SStone = B.Slot(TEXT("MI_StoneBase"));
		const int32 SConcrete = B.Slot(TEXT("MI_Concrete"));
		const int32 SMetal = B.Slot(TEXT("MI_Metal"));

		const float CX = -3.20f;
		const float CY = 1.40f;
		const float R = 0.31f;
		const float TopZ = 5.93f;

		B.Box(FVector(CX, CY, (FLOOR_Z + TopZ) * 0.5f),
			FVector(R, R, (TopZ - FLOOR_Z) * 0.5f), SPlaster);
		B.Box(FVector(CX, CY, FLOOR_Z + 0.18f), FVector(R + 0.04f, R + 0.04f, 0.18f), SStone);
		// Flashing where the flue passes through the north roof slope.
		const float RoofZ = EAVE_Z + (OUT_HY - CY) * PITCH_TAN;
		B.Box(FVector(CX, CY, RoofZ + 0.26f), FVector(R + 0.20f, R + 0.20f, 0.035f),
			SMetal, FRotator(0.f, 0.f, -26.f));
		B.Box(FVector(CX, CY, TopZ + 0.07f), FVector(R + 0.09f, R + 0.09f, 0.07f), SConcrete);
		B.Cylinder(FVector(CX, CY, TopZ + 0.14f), FVector(CX, CY, TopZ + 0.44f), 0.15f, 0.13f, 12, SMetal);
	}

	// ------------------------------------------------------------------
	// Door / window units
	// ------------------------------------------------------------------
	/** Door and window openings that belong to the interior partitions. */
	static bool IsInteriorOpening(const FOpening& Opening)
	{
		const FString Id(Opening.Id);
		return Id == TEXT("Opening_Salon") ||
			(Id.StartsWith(TEXT("Door_")) && Id != TEXT("Door_Front") && Id != TEXT("Door_Rear"));
	}

	/** A door or window unit with everything needed to build its joinery and leaf. */
	struct FUnitSpec
	{
		FString Id;
		FVector2D A = FVector2D::ZeroVector;
		FVector2D B = FVector2D::ZeroVector;
		float Thickness = EXT_T;
		FWallOpening Opening;
		bool bWindow = false;
		bool bCased = false;      // opening without a leaf
		bool bExterior = false;
		float OpenDeg = -84.f;    // swing of the leaf (0 = closed)
	};

	static TArray<FUnitSpec> CollectUnits()
	{
		TArray<FUnitSpec> Units;
		const TArray<FOpening> Plan = PlanOpenings();
		const TArray<FWallRun> Exterior = ExteriorRuns();
		const TArray<FWallRun> Interior = InteriorRuns();

		for (const FOpening& Opening : Plan)
		{
			if (!IsInteriorOpening(Opening))
			{
				for (const FWallRun& Run : Exterior)
				{
					if (Run.Side != Opening.Side)
					{
						continue;
					}
					FUnitSpec Unit;
					Unit.Id = FString(Opening.Id);
					Unit.A = Run.A;
					Unit.B = Run.B;
					Unit.Thickness = Run.Thickness;
					Unit.Opening.AlongMin = FMath::Min(Run.Along(Opening.From), Run.Along(Opening.To));
					Unit.Opening.AlongMax = FMath::Max(Run.Along(Opening.From), Run.Along(Opening.To));
					Unit.Opening.ZMin = FLOOR_Z + Opening.Sill;
					Unit.Opening.ZMax = FLOOR_Z + Opening.Sill + Opening.Height;
					Unit.bWindow = !Opening.bDoor;
					Unit.bCased = !Opening.bLeaf;
					Unit.bExterior = true;
					Unit.OpenDeg = 90.f;   // exterior doors swing out, clear of the hall
					Units.Add(Unit);
					break;
				}
				continue;
			}

			for (const FWallRun& Run : Interior)
			{
				const float Along0 = FMath::Min(Run.Along(Opening.From), Run.Along(Opening.To));
				const float Along1 = FMath::Max(Run.Along(Opening.From), Run.Along(Opening.To));
				bool bMatch = false;
				for (const FWallOpening& WallOpening : Run.Openings)
				{
					if (FMath::IsNearlyEqual(WallOpening.AlongMin, Along0, 0.02f) &&
						FMath::IsNearlyEqual(WallOpening.AlongMax, Along1, 0.02f))
					{
						bMatch = true;
						break;
					}
				}
				if (!bMatch)
				{
					continue;
				}
				FUnitSpec Unit;
				Unit.Id = FString(Opening.Id);
				Unit.A = Run.A;
				Unit.B = Run.B;
				Unit.Thickness = Run.Thickness;
				Unit.Opening.AlongMin = Along0;
				Unit.Opening.AlongMax = Along1;
				Unit.Opening.ZMin = FLOOR_Z + Opening.Sill;
				Unit.Opening.ZMax = FLOOR_Z + Opening.Sill + Opening.Height;
				Unit.bWindow = false;
				Unit.bCased = !Opening.bLeaf;
				Unit.bExterior = false;
				// Neither run is rotated, so the swing only depends on the run: the
				// corridor's west wall opens into the western rooms, the east wall into
				// the eastern ones.
				Unit.OpenDeg = (Run.A.X < 0.f) ? 90.f : -90.f;
				Units.Add(Unit);
				break;
			}
		}
		return Units;
	}

	/** Joinery frames, sills and casings of every door and window opening. */
	static void BuildOpeningUnits(FMeshBuilder& B, const TArray<FUnitSpec>& Units, bool bWindows)
	{
		const int32 SFrame = B.Slot(TEXT("MI_WoodTrim"));
		for (const FUnitSpec& Unit : Units)
		{
			if (Unit.bWindow != bWindows)
			{
				continue;
			}
			// Glazing is generated into its own mesh (no collision, replaceable).
			B.OpeningUnit(Unit.A, Unit.B, Unit.Thickness, Unit.Opening, SFrame, INDEX_NONE, Unit.bWindow, 0.06f);
		}
	}

	/** Glazing panes of all windows (no collision: glass does not block the player). */
	static void BuildGlazing(FMeshBuilder& B, const TArray<FUnitSpec>& Units)
	{
		const int32 SPane = B.Slot(TEXT("MI_Glass"));
		const bool bWasTracking = B.bTrackCollision;
		B.bTrackCollision = false;
		for (const FUnitSpec& Unit : Units)
		{
			if (!Unit.bWindow)
			{
				continue;
			}
			const FVector2D Dir = (Unit.B - Unit.A).GetSafeNormal();
			const float CenterAlong = (Unit.Opening.AlongMin + Unit.Opening.AlongMax) * 0.5f;
			const FVector2D Center2D = Unit.A + Dir * CenterAlong;
			const float YawDeg = FMath::RadiansToDegrees(FMath::Atan2(Dir.Y, Dir.X));
			const float Width = Unit.Opening.AlongMax - Unit.Opening.AlongMin;
			const float Height = Unit.Opening.ZMax - Unit.Opening.ZMin;
			B.Box(FVector(Center2D.X, Center2D.Y, (Unit.Opening.ZMin + Unit.Opening.ZMax) * 0.5f),
				FVector(FMath::Max(0.03f, Width * 0.5f - 0.06f), 0.012f,
					FMath::Max(0.03f, Height * 0.5f - 0.06f)), SPane, FRotator(0.f, YawDeg, 0.f));
		}
		B.bTrackCollision = bWasTracking;
	}

	// ------------------------------------------------------------------
	// Interior trim: skirting boards, ceiling coves and door thresholds
	// ------------------------------------------------------------------
	/** Gaps (along the run) where the openings of the units cut through it. */
	static TArray<FVector2D> RunGaps(const TArray<FUnitSpec>& Units, bool bAlongX, float Fixed,
	                                 float From, float To, float ZBottom)
	{
		TArray<FVector2D> Gaps;
		for (const FUnitSpec& Unit : Units)
		{
			if (Unit.Opening.ZMin > ZBottom + 0.04f)
			{
				continue;   // sill above the trim: no gap needed
			}
			const FVector2D Dir = (Unit.B - Unit.A).GetSafeNormal();
			const FVector2D P0 = Unit.A + Dir * Unit.Opening.AlongMin;
			const FVector2D P1 = Unit.A + Dir * Unit.Opening.AlongMax;
			const float Perp = bAlongX ? FMath::Abs(P0.Y - Fixed) : FMath::Abs(P0.X - Fixed);
			if (Perp > 0.35f)
			{
				continue;
			}
			const float G0 = bAlongX ? FMath::Min(P0.X, P1.X) : FMath::Min(P0.Y, P1.Y);
			const float G1 = bAlongX ? FMath::Max(P0.X, P1.X) : FMath::Max(P0.Y, P1.Y);
			if (G1 <= From || G0 >= To)
			{
				continue;
			}
			Gaps.Add(FVector2D(G0, G1));
		}
		Gaps.Sort([](const FVector2D& L, const FVector2D& R) { return L.X < R.X; });
		return Gaps;
	}

	/** One trim run along a room edge, split around the door gaps. */
	static void TrimRun(FMeshBuilder& B, bool bAlongX, float Fixed, float From, float To,
	                    float ZMin, float Height, float Thickness, int32 Slot,
	                    const TArray<FVector2D>& Gaps)
	{
		float Cursor = From;
		for (const FVector2D& Gap : Gaps)
		{
			const float GapStart = FMath::Clamp(Gap.X - 0.02f, From, To);
			if (GapStart > Cursor + 0.02f)
			{
				B.AddTrimSegment(bAlongX, Fixed, Cursor, GapStart, ZMin, Height, Thickness, Slot);
			}
			Cursor = FMath::Max(Cursor, FMath::Clamp(Gap.Y + 0.02f, From, To));
		}
		if (To > Cursor + 0.02f)
		{
			B.AddTrimSegment(bAlongX, Fixed, Cursor, To, ZMin, Height, Thickness, Slot);
		}
	}

	/**
	 * Skirting boards (0.45-0.55) and ceiling coves (2.92-3.04) around every room,
	 * plus a stone threshold across each door opening.
	 */
	static void BuildInteriorTrim(FMeshBuilder& B, const TArray<FUnitSpec>& Units)
	{
		const int32 SSkirt = B.Slot(TEXT("MI_WoodTrim"));
		const int32 SCove = B.Slot(TEXT("MI_Ceiling"));
		const int32 SStone = B.Slot(TEXT("MI_StoneBase"));
		const TArray<FRoomRect> Rooms = PlanRooms();

		for (const FRoomRect& Room : Rooms)
		{
			const float Inset = 0.0125f;
			const float SkirtZ = FLOOR_Z;
			const float CovesZ = FLOOR_Z + CEIL_H - 0.11f;
			// Edges: (along X or not, fixed coordinate, from, to)
			const bool bAlongX[4] = { true, true, false, false };
			const float Fixed[4] = { Room.Y0 + Inset, Room.Y1 - Inset, Room.X0 + Inset, Room.X1 - Inset };
			const float From[4] = { Room.X0 - 0.02f, Room.X0 - 0.02f, Room.Y0 - 0.02f, Room.Y0 - 0.02f };
			const float To[4] = { Room.X1 + 0.02f, Room.X1 + 0.02f, Room.Y1 + 0.02f, Room.Y1 + 0.02f };
			for (int32 Edge = 0; Edge < 4; ++Edge)
			{
				const TArray<FVector2D> Gaps = RunGaps(Units, bAlongX[Edge], Fixed[Edge],
					From[Edge], To[Edge], SkirtZ);
				TrimRun(B, bAlongX[Edge], Fixed[Edge], From[Edge], To[Edge], SkirtZ, 0.10f, 0.025f, SSkirt, Gaps);
				TrimRun(B, bAlongX[Edge], Fixed[Edge], From[Edge], To[Edge], CovesZ, 0.11f, 0.030f, SCove,
					TArray<FVector2D>());
			}
		}

		// Thresholds: a stone sill across each door opening.
		for (const FUnitSpec& Unit : Units)
		{
			if (Unit.bWindow || Unit.bCased)
			{
				continue;
			}
			const FVector2D Dir = (Unit.B - Unit.A).GetSafeNormal();
			const FVector2D Centre = Unit.A + Dir * (Unit.Opening.AlongMin + Unit.Opening.AlongMax) * 0.5f;
			const float Width = Unit.Opening.AlongMax - Unit.Opening.AlongMin;
			const float YawDeg = FMath::RadiansToDegrees(FMath::Atan2(Dir.Y, Dir.X));
			const bool bWasTracking = B.bTrackCollision;
			B.bTrackCollision = true;
			B.Box(FVector(Centre.X, Centre.Y, FLOOR_Z + 0.01f),
				FVector(Width * 0.5f, 0.10f, 0.01f), SStone, FRotator(0.f, YawDeg, 0.f));
			B.bTrackCollision = bWasTracking;
		}
	}

	// ------------------------------------------------------------------
	// Wall details: light fixtures, switches, outlets, radiators, grilles,
	// towel rail, mirrors, coat rack and doormats.
	// ------------------------------------------------------------------
	/** Ceiling light fixtures: one per room, hall and corridor. */
	static void BuildLightFixtures(FMeshBuilder& B, TArray<FVector2D>& OutPositions)
	{
		const int32 SShade = B.Slot(TEXT("MI_LampShade"));
		const int32 SMetal = B.Slot(TEXT("MI_Metal"));
		const float CeilingZ = FLOOR_Z + CEIL_H;

		OutPositions.Add(FVector2D(2.90f, 2.75f));    // salon
		OutPositions.Add(FVector2D(-3.63f, 2.60f));   // kitchen
		OutPositions.Add(FVector2D(-3.63f, -2.60f));  // player bedroom
		OutPositions.Add(FVector2D(2.90f, -3.10f));   // parents' bedroom
		OutPositions.Add(FVector2D(-3.63f, 0.00f));   // bathroom
		OutPositions.Add(FVector2D(1.15f, 0.50f));    // WC
		OutPositions.Add(FVector2D(1.80f, -1.10f));   // pantry
		OutPositions.Add(FVector2D(-0.72f, 3.20f));   // hall (entrance)
		OutPositions.Add(FVector2D(-0.72f, -2.00f));  // corridor

		for (const FVector2D& Position : OutPositions)
		{
			const FVector P(Position.X, Position.Y, 0.f);
			B.Box(P + FVector(0.f, 0.f, CeilingZ - 0.015f), FVector(0.09f, 0.09f, 0.015f), SShade);
			B.Cylinder(P + FVector(0.f, 0.f, CeilingZ - 0.02f), P + FVector(0.f, 0.f, CeilingZ - 0.20f),
				0.012f, 0.012f, 6, SMetal);
			B.Cylinder(P + FVector(0.f, 0.f, CeilingZ - 0.20f), P + FVector(0.f, 0.f, CeilingZ - 0.30f),
				0.10f, 0.17f, 12, SShade);
		}

		// Porch light beside the front door.
		B.Box(FVector(-1.55f, 4.16f, 2.35f), FVector(0.07f, 0.07f, 0.10f), SShade);
		B.Box(FVector(-1.55f, 4.13f, 2.20f), FVector(0.06f, 0.03f, 0.03f), SMetal);
	}

	/** Switches beside every door and an outlet in every room. */
	static void BuildSwitches(FMeshBuilder& B, const TArray<FUnitSpec>& Units)
	{
		const int32 SPlastic = B.Slot(TEXT("MI_WhiteMetal"));
		const bool bWasTracking = B.bTrackCollision;
		B.bTrackCollision = false;

		for (const FUnitSpec& Unit : Units)
		{
			if (Unit.bWindow || Unit.bCased)
			{
				continue;
			}
			const FVector2D Dir = (Unit.B - Unit.A).GetSafeNormal();
			const FVector2D Normal = (Unit.A.X > 0.f) ? FVector2D(-Dir.Y, Dir.X) : FVector2D(Dir.Y, -Dir.X);
			const FVector2D Point = Unit.A + Dir * (Unit.Opening.AlongMin + 0.18f) + Normal * 0.02f;
			const float YawDeg = FMath::RadiansToDegrees(FMath::Atan2(Dir.Y, Dir.X));
			B.Box(FVector(Point.X, Point.Y, FLOOR_Z + 1.15f), FVector(0.045f, 0.014f, 0.045f),
				SPlastic, FRotator(0.f, YawDeg, 0.f));
		}

		const FVector2D Outlets[9] = {
			FVector2D(5.60f, 4.05f), FVector2D(-3.20f, 4.05f), FVector2D(-5.60f, -1.60f),
			FVector2D(0.30f, -2.10f), FVector2D(-5.60f, 0.60f), FVector2D(2.05f, 1.05f),
			FVector2D(0.30f, -1.05f), FVector2D(5.60f, -2.20f), FVector2D(-1.35f, -4.05f),
		};
		for (const FVector2D& Position : Outlets)
		{
			B.Box(FVector(Position.X, Position.Y, FLOOR_Z + 0.30f), FVector(0.045f, 0.014f, 0.045f), SPlastic);
		}
		B.bTrackCollision = bWasTracking;
	}

	/** Radiators, WC extract grille, towel rail, mirrors, coat rack and mats. */
	static void BuildFittings(FMeshBuilder& B)
	{
		const int32 SPlastic = B.Slot(TEXT("MI_WhiteMetal"));
		const int32 SMetal = B.Slot(TEXT("MI_Metal"));
		const int32 SStone = B.Slot(TEXT("MI_StoneBase"));
		const int32 SMirror = B.Slot(TEXT("MI_Mirror"));
		const int32 SWood = B.Slot(TEXT("MI_WoodTrim"));
		const int32 SFabric = B.Slot(TEXT("MI_Fabric"));

		// Radiators under the windows of the main rooms.
		struct FRadiator { FVector2D Centre; bool bAlongX; };
		const FRadiator Radiators[5] = {
			{ FVector2D(-3.95f, 4.10f), true },    // kitchen, north window
			{ FVector2D(2.90f, -4.10f), true },    // parents' bedroom, south window
			{ FVector2D(-5.60f, -2.50f), false },  // player bedroom, west window
			{ FVector2D(-5.60f, -0.15f), false },  // bathroom, west window
			{ FVector2D(5.60f, 2.70f), false },    // salon, east window
		};
		for (const FRadiator& Radiator : Radiators)
		{
			const FVector Half = Radiator.bAlongX ? FVector(0.35f, 0.055f, 0.28f) : FVector(0.055f, 0.35f, 0.28f);
			B.Box(FVector(Radiator.Centre.X, Radiator.Centre.Y, FLOOR_Z + 0.52f), Half, SMetal);
			for (int32 Index = -1; Index <= 1; Index += 2)
			{
				const FVector Pipe = Radiator.bAlongX
					? FVector(Radiator.Centre.X + Index * 0.28f, Radiator.Centre.Y, FLOOR_Z + 0.10f)
					: FVector(Radiator.Centre.X, Radiator.Centre.Y + Index * 0.28f, FLOOR_Z + 0.10f);
				B.Cylinder(Pipe, Pipe + FVector(0.f, 0.f, 0.16f), 0.018f, 0.018f, 6, SMetal);
			}
		}

		// WC extract grille (the WC is an internal room: it is ventilated).
		B.AddTrimSegment(false, 2.19f, 0.20f, 0.80f, FLOOR_Z + 1.90f, 0.20f, 0.02f, SPlastic);
		for (int32 Index = 0; Index < 3; ++Index)
		{
			B.AddTrimSegment(false, 2.19f, 0.24f, 0.76f, FLOOR_Z + 1.94f + Index * 0.055f, 0.015f, 0.03f, SPlastic);
		}

		// Bathroom towel rail.
		B.Cylinder(FVector(-1.62f, 0.30f, FLOOR_Z + 1.15f), FVector(-1.62f, 0.90f, FLOOR_Z + 1.15f),
			0.016f, 0.016f, 8, SMetal);

		// Mirrors: bathroom, WC and the entrance hall.
		struct FMirror { FVector2D Centre; bool bFacingX; };
		const FMirror Mirrors[3] = {
			{ FVector2D(-1.58f, 0.30f), true },     // bathroom, over the basin
			{ FVector2D(1.60f, -0.16f), false },    // WC, over the basin
			{ FVector2D(-1.40f, 3.60f), true },     // hall mirror
		};
		for (const FMirror& Mirror : Mirrors)
		{
			const FVector Half = Mirror.bFacingX ? FVector(0.012f, 0.26f, 0.32f) : FVector(0.26f, 0.012f, 0.32f);
			const FVector FrameHalf = Mirror.bFacingX ? FVector(0.022f, 0.30f, 0.022f) : FVector(0.30f, 0.022f, 0.022f);
			B.Box(FVector(Mirror.Centre.X, Mirror.Centre.Y, FLOOR_Z + 1.58f), Half, SMirror);
			B.Box(FVector(Mirror.Centre.X, Mirror.Centre.Y, FLOOR_Z + 1.26f), FrameHalf, SWood);
			B.Box(FVector(Mirror.Centre.X, Mirror.Centre.Y, FLOOR_Z + 1.90f), FrameHalf, SWood);
		}

		// Coat rack in the hall (board with four hooks).
		B.Box(FVector(-1.40f, 3.95f, FLOOR_Z + 1.60f), FVector(0.018f, 0.30f, 0.07f), SWood);
		for (int32 Index = 0; Index < 4; ++Index)
		{
			B.Box(FVector(-1.35f, 3.72f + Index * 0.15f, FLOOR_Z + 1.56f), FVector(0.05f, 0.015f, 0.015f), SMetal);
		}

		// Doormats inside and outside the front door, plus one at the rear door.
		const bool bWasTracking = B.bTrackCollision;
		B.bTrackCollision = false;
		B.Box(FVector(-0.72f, 3.95f, FLOOR_Z + 0.012f), FVector(0.55f, 0.30f, 0.012f), SFabric);
		B.Box(FVector(-0.72f, 4.80f, FLOOR_Z - 0.06f), FVector(0.55f, 0.30f, 0.012f), SFabric);
		B.Box(FVector(-0.72f, -4.52f, FLOOR_Z + 0.012f), FVector(0.50f, 0.30f, 0.012f), SFabric);
		B.bTrackCollision = bWasTracking;

		// Threshold step outside the rear door (the landing is 0.30 m high).
		B.Box(FVector(-0.72f, -4.60f, FLOOR_Z - 0.05f), FVector(0.55f, 0.12f, 0.05f), SStone);
	}

	// ------------------------------------------------------------------
	// Furniture and props. Every item is its own mesh asset, authored around
	// its footprint centre with z = 0 on the floor, so the layout can place
	// (and later rearrange) each piece independently.
	// ------------------------------------------------------------------
	struct FPieceSpec
	{
		FVector Center = FVector::ZeroVector;
		FVector Half = FVector::ZeroVector;
		int32 Slot = 0;
		FRotator Rot = FRotator::ZeroRotator;
	};

	static void AddPiece(TArray<FPieceSpec>& Pieces, int32 Slot, float CX, float CY, float CZ,
	                     float HX, float HY, float HZ, FRotator Rot = FRotator::ZeroRotator)
	{
		FPieceSpec Piece;
		Piece.Center = FVector(CX, CY, CZ);
		Piece.Half = FVector(HX, HY, HZ);
		Piece.Slot = Slot;
		Piece.Rot = Rot;
		Pieces.Add(Piece);
	}

	/** One furniture asset from a compact piece list. */
	static void CreatePieceMesh(const FString& Dir, const TCHAR* Name, const FMaterialSet& Materials,
	                            FPhase4B1HouseReport& Report,
	                            TFunctionRef<void(FMeshBuilder&, TArray<FPieceSpec>&)> Build)
	{
		FMeshBuilder Builder;
		TArray<FPieceSpec> Pieces;
		Build(Builder, Pieces);
		for (const FPieceSpec& Piece : Pieces)
		{
			Builder.Box(Piece.Center, Piece.Half, Piece.Slot, Piece.Rot);
		}
		UStaticMesh* Mesh = CreateStaticMeshAsset(Dir, FString(Name), Builder, Materials, Report.Warnings);
		if (Mesh != nullptr)
		{
			Report.MeshTriangles += Builder.TriangleCount;
			Report.CreatedAssets.Add(FString::Printf(TEXT("%s/%s [%d slots, %d tris, %d collision boxes]"),
				*Dir, Name, Builder.SlotNames.Num(), Builder.TriangleCount, Builder.CollisionBoxes.Num()));
		}
	}

	/** Salon seating group: sofa, armchair, coffee table, TV cabinet, TV, rug, sideboard. */
	static void BuildSeatingFurniture(const FMaterialSet& Materials, FPhase4B1HouseReport& Report)
	{
		CreatePieceMesh(FurnDir, TEXT("SM_H_Sofa"), Materials, Report,
			[](FMeshBuilder& B, TArray<FPieceSpec>& P)
		{
			const int32 SFab = B.Slot(TEXT("MI_Fabric"));
			const int32 SWood = B.Slot(TEXT("MI_WoodDark"));
			AddPiece(P, SFab, 0.f, 0.f, 0.26f, 1.05f, 0.42f, 0.20f);       // base 2.10 x 0.84
			AddPiece(P, SFab, 0.f, 0.34f, 0.56f, 1.05f, 0.08f, 0.30f);     // back
			AddPiece(P, SFab, -1.00f, 0.f, 0.46f, 0.05f, 0.42f, 0.20f);    // arms
			AddPiece(P, SFab, 1.00f, 0.f, 0.46f, 0.05f, 0.42f, 0.20f);
			for (int32 Index = -1; Index <= 1; ++Index)
			{
				AddPiece(P, SFab, Index * 0.64f, -0.05f, 0.50f, 0.30f, 0.35f, 0.06f);   // seat cushions
				AddPiece(P, SFab, Index * 0.64f, 0.26f, 0.62f, 0.30f, 0.08f, 0.14f);    // back cushions
			}
			AddPiece(P, SWood, 0.f, 0.f, 0.05f, 1.05f, 0.42f, 0.05f);      // plinth
		});

		CreatePieceMesh(FurnDir, TEXT("SM_H_Armchair"), Materials, Report,
			[](FMeshBuilder& B, TArray<FPieceSpec>& P)
		{
			const int32 SFab = B.Slot(TEXT("MI_Fabric"));
			const int32 SWood = B.Slot(TEXT("MI_WoodDark"));
			AddPiece(P, SFab, 0.f, 0.f, 0.26f, 0.45f, 0.42f, 0.20f);
			AddPiece(P, SFab, 0.f, 0.34f, 0.56f, 0.45f, 0.08f, 0.30f);
			AddPiece(P, SFab, -0.40f, 0.f, 0.46f, 0.05f, 0.42f, 0.20f);
			AddPiece(P, SFab, 0.40f, 0.f, 0.46f, 0.05f, 0.42f, 0.20f);
			AddPiece(P, SFab, 0.f, -0.05f, 0.50f, 0.33f, 0.35f, 0.06f);
			AddPiece(P, SFab, 0.f, 0.26f, 0.62f, 0.33f, 0.08f, 0.14f);
			AddPiece(P, SWood, 0.f, 0.f, 0.05f, 0.45f, 0.42f, 0.05f);
		});

		CreatePieceMesh(FurnDir, TEXT("SM_H_CoffeeTable"), Materials, Report,
			[](FMeshBuilder& B, TArray<FPieceSpec>& P)
		{
			const int32 SWood = B.Slot(TEXT("MI_WoodDark"));
			AddPiece(P, SWood, 0.f, 0.f, 0.42f, 0.55f, 0.30f, 0.025f);
			AddPiece(P, SWood, 0.f, 0.f, 0.24f, 0.50f, 0.26f, 0.02f);
			for (int32 X = -1; X <= 1; X += 2)
			{
				for (int32 Y = -1; Y <= 1; Y += 2)
				{
					AddPiece(P, SWood, X * 0.50f, Y * 0.26f, 0.20f, 0.03f, 0.03f, 0.20f);
				}
			}
		});

		CreatePieceMesh(FurnDir, TEXT("SM_H_TVCabinet"), Materials, Report,
			[](FMeshBuilder& B, TArray<FPieceSpec>& P)
		{
			const int32 SWood = B.Slot(TEXT("MI_WoodDark"));
			const int32 SDoor = B.Slot(TEXT("MI_DoorInt"));
			const int32 SMetal = B.Slot(TEXT("MI_Metal"));
			AddPiece(P, SWood, 0.f, 0.f, 0.28f, 0.80f, 0.22f, 0.28f);
			AddPiece(P, SDoor, -0.39f, -0.225f, 0.28f, 0.39f, 0.015f, 0.25f);
			AddPiece(P, SDoor, 0.39f, -0.225f, 0.28f, 0.39f, 0.015f, 0.25f);
			AddPiece(P, SMetal, -0.06f, -0.245f, 0.28f, 0.012f, 0.012f, 0.10f);
			AddPiece(P, SMetal, 0.06f, -0.245f, 0.28f, 0.012f, 0.012f, 0.10f);
		});

		CreatePieceMesh(FurnDir, TEXT("SM_H_TV"), Materials, Report,
			[](FMeshBuilder& B, TArray<FPieceSpec>& P)
		{
			const int32 SBody = B.Slot(TEXT("MI_WoodDark"));
			const int32 SScreen = B.Slot(TEXT("MI_Glass"));
			const int32 SStand = B.Slot(TEXT("MI_Metal"));
			AddPiece(P, SBody, 0.f, 0.f, 0.36f, 0.53f, 0.035f, 0.31f);
			AddPiece(P, SScreen, 0.f, -0.038f, 0.36f, 0.49f, 0.006f, 0.28f);
			AddPiece(P, SStand, 0.f, 0.f, 0.025f, 0.22f, 0.10f, 0.025f);
		});

		CreatePieceMesh(FurnDir, TEXT("SM_H_Sideboard"), Materials, Report,
			[](FMeshBuilder& B, TArray<FPieceSpec>& P)
		{
			const int32 SWood = B.Slot(TEXT("MI_WoodDark"));
			const int32 SDoor = B.Slot(TEXT("MI_DoorInt"));
			AddPiece(P, SWood, 0.f, 0.f, 0.42f, 0.60f, 0.22f, 0.42f);
			AddPiece(P, SWood, 0.f, 0.f, 0.855f, 0.62f, 0.23f, 0.02f);
			AddPiece(P, SDoor, 0.f, -0.225f, 0.42f, 0.57f, 0.015f, 0.36f);
		});

		CreatePieceMesh(FurnDir, TEXT("SM_H_Rug"), Materials, Report,
			[](FMeshBuilder& B, TArray<FPieceSpec>& P)
		{
			const int32 SCarpet = B.Slot(TEXT("MI_Carpet"));
			const int32 SEdge = B.Slot(TEXT("MI_FabricRed"));
			B.bTrackCollision = false;   // a rug is flat: it must not block walking
			AddPiece(P, SEdge, 0.f, 0.f, 0.012f, 1.00f, 1.00f, 0.012f);
			AddPiece(P, SCarpet, 0.f, 0.f, 0.020f, 0.90f, 0.90f, 0.010f);
		});
	}

	/** Kitchen: base run with worktop, upper cabinet, sink, hob, fridge, wood range,
	 *  dining table and chair. The front of the run faces -Y. */
	static void BuildKitchenFurniture(const FMaterialSet& Materials, FPhase4B1HouseReport& Report)
	{
		CreatePieceMesh(FurnDir, TEXT("SM_H_KitchenBase"), Materials, Report,
			[](FMeshBuilder& B, TArray<FPieceSpec>& P)
		{
			const int32 SWood = B.Slot(TEXT("MI_WoodDark"));
			const int32 SDoor = B.Slot(TEXT("MI_DoorInt"));
			const int32 STop = B.Slot(TEXT("MI_Counter"));
			const int32 SMetal = B.Slot(TEXT("MI_Metal"));
			AddPiece(P, SWood, 0.f, 0.f, 0.44f, 1.00f, 0.30f, 0.40f);        // carcass 2.00 x 0.60
			AddPiece(P, SWood, 0.f, -0.26f, 0.04f, 0.96f, 0.03f, 0.04f);      // toe kick
			AddPiece(P, STop, 0.f, 0.f, 0.86f, 1.02f, 0.32f, 0.02f);          // worktop
			AddPiece(P, SDoor, -0.50f, -0.305f, 0.42f, 0.48f, 0.015f, 0.34f);
			AddPiece(P, SDoor, 0.50f, -0.305f, 0.42f, 0.48f, 0.015f, 0.34f);
			AddPiece(P, SWood, 0.f, -0.305f, 0.76f, 0.99f, 0.015f, 0.06f);    // drawer front
			AddPiece(P, SMetal, -0.10f, -0.325f, 0.42f, 0.08f, 0.012f, 0.012f);
			AddPiece(P, SMetal, 0.10f, -0.325f, 0.42f, 0.08f, 0.012f, 0.012f);
			AddPiece(P, SMetal, 0.f, -0.325f, 0.76f, 0.12f, 0.012f, 0.012f);
		});

		CreatePieceMesh(FurnDir, TEXT("SM_H_KitchenUpper"), Materials, Report,
			[](FMeshBuilder& B, TArray<FPieceSpec>& P)
		{
			const int32 SWood = B.Slot(TEXT("MI_WoodDark"));
			const int32 SDoor = B.Slot(TEXT("MI_DoorInt"));
			const int32 SMetal = B.Slot(TEXT("MI_Metal"));
			AddPiece(P, SWood, 0.f, 0.f, 0.35f, 0.50f, 0.175f, 0.35f);        // 1.00 x 0.35 x 0.70
			AddPiece(P, SDoor, -0.25f, -0.18f, 0.35f, 0.24f, 0.015f, 0.33f);
			AddPiece(P, SDoor, 0.25f, -0.18f, 0.35f, 0.24f, 0.015f, 0.33f);
			AddPiece(P, SMetal, -0.04f, -0.20f, 0.35f, 0.012f, 0.012f, 0.10f);
			AddPiece(P, SMetal, 0.04f, -0.20f, 0.35f, 0.012f, 0.012f, 0.10f);
		});

		CreatePieceMesh(FurnDir, TEXT("SM_H_Sink"), Materials, Report,
			[](FMeshBuilder& B, TArray<FPieceSpec>& P)
		{
			const int32 SMetal = B.Slot(TEXT("MI_Metal"));
			AddPiece(P, SMetal, 0.f, 0.f, 0.012f, 0.29f, 0.21f, 0.012f);      // rim + basin on the worktop
			AddPiece(P, SMetal, 0.f, 0.f, 0.004f, 0.26f, 0.18f, 0.004f);
			B.Cylinder(FVector(0.f, 0.17f, 0.02f), FVector(0.f, 0.17f, 0.24f), 0.018f, 0.018f, 8, SMetal);
			AddPiece(P, SMetal, 0.f, 0.10f, 0.235f, 0.016f, 0.075f, 0.016f);
		});

		CreatePieceMesh(FurnDir, TEXT("SM_H_Hob"), Materials, Report,
			[](FMeshBuilder& B, TArray<FPieceSpec>& P)
		{
			const int32 SMetal = B.Slot(TEXT("MI_Metal"));
			AddPiece(P, SMetal, 0.f, 0.f, 0.015f, 0.29f, 0.24f, 0.015f);
			for (int32 X = -1; X <= 1; X += 2)
			{
				for (int32 Y = -1; Y <= 1; Y += 2)
				{
					B.Cylinder(FVector(X * 0.14f, Y * 0.11f, 0.03f), FVector(X * 0.14f, Y * 0.11f, 0.04f),
						0.055f, 0.055f, 10, SMetal);
				}
			}
		});

		CreatePieceMesh(FurnDir, TEXT("SM_H_Fridge"), Materials, Report,
			[](FMeshBuilder& B, TArray<FPieceSpec>& P)
		{
			const int32 SBody = B.Slot(TEXT("MI_WhiteMetal"));
			const int32 SMetal = B.Slot(TEXT("MI_Metal"));
			AddPiece(P, SBody, 0.f, 0.f, 0.925f, 0.35f, 0.36f, 0.925f);      // 0.70 x 0.72 x 1.85
			AddPiece(P, SMetal, 0.f, -0.365f, 0.72f, 0.34f, 0.006f, 0.006f);  // freezer division
			AddPiece(P, SMetal, 0.28f, -0.375f, 1.15f, 0.02f, 0.02f, 0.22f);
			AddPiece(P, SMetal, 0.28f, -0.375f, 0.45f, 0.02f, 0.02f, 0.14f);
		});

		CreatePieceMesh(FurnDir, TEXT("SM_H_WoodRange"), Materials, Report,
			[](FMeshBuilder& B, TArray<FPieceSpec>& P)
		{
			const int32 SMetal = B.Slot(TEXT("MI_Metal"));
			AddPiece(P, SMetal, 0.f, 0.f, 0.45f, 0.30f, 0.30f, 0.45f);       // body 0.60 x 0.60 x 0.90
			AddPiece(P, SMetal, 0.f, -0.305f, 0.32f, 0.24f, 0.02f, 0.20f);    // oven door
			AddPiece(P, SMetal, 0.f, -0.33f, 0.32f, 0.16f, 0.015f, 0.012f);
			AddPiece(P, SMetal, 0.f, 0.f, 0.905f, 0.29f, 0.29f, 0.02f);       // hot plate
			B.Cylinder(FVector(-0.13f, 0.f, 0.92f), FVector(-0.13f, 0.f, 0.93f), 0.10f, 0.10f, 12, SMetal);
			B.Cylinder(FVector(0.13f, 0.f, 0.92f), FVector(0.13f, 0.f, 0.93f), 0.10f, 0.10f, 12, SMetal);
			B.Cylinder(FVector(0.f, 0.10f, 0.92f), FVector(0.f, 0.10f, 2.20f), 0.07f, 0.07f, 10, SMetal);
			B.Cylinder(FVector(0.f, 0.10f, 2.20f), FVector(0.f, 0.10f, 2.28f), 0.09f, 0.09f, 10, SMetal);
		});

		CreatePieceMesh(FurnDir, TEXT("SM_H_DiningTable"), Materials, Report,
			[](FMeshBuilder& B, TArray<FPieceSpec>& P)
		{
			const int32 SWood = B.Slot(TEXT("MI_WoodDark"));
			AddPiece(P, SWood, 0.f, 0.f, 0.74f, 0.65f, 0.425f, 0.03f);       // 1.30 x 0.85 top
			AddPiece(P, SWood, 0.f, 0.f, 0.68f, 0.55f, 0.36f, 0.03f);        // apron
			for (int32 X = -1; X <= 1; X += 2)
			{
				for (int32 Y = -1; Y <= 1; Y += 2)
				{
					AddPiece(P, SWood, X * 0.58f, Y * 0.35f, 0.36f, 0.04f, 0.04f, 0.35f);
				}
			}
		});

		CreatePieceMesh(FurnDir, TEXT("SM_H_Chair"), Materials, Report,
			[](FMeshBuilder& B, TArray<FPieceSpec>& P)
		{
			const int32 SWood = B.Slot(TEXT("MI_WoodDark"));
			const int32 SFab = B.Slot(TEXT("MI_FabricRed"));
			AddPiece(P, SWood, 0.f, 0.f, 0.44f, 0.225f, 0.225f, 0.02f);      // seat
			AddPiece(P, SFab, 0.f, 0.f, 0.47f, 0.21f, 0.21f, 0.02f);         // cushion
			AddPiece(P, SWood, 0.f, 0.20f, 0.72f, 0.225f, 0.025f, 0.26f);    // back
			for (int32 X = -1; X <= 1; X += 2)
			{
				for (int32 Y = -1; Y <= 1; Y += 2)
				{
					AddPiece(P, SWood, X * 0.19f, Y * 0.19f, 0.21f, 0.025f, 0.025f, 0.21f);
				}
			}
		});
	}

	/** Bedrooms: single and double bed, wardrobe, nightstand, lamp, desk, dresser, chest. */
	static void BuildBedroomFurniture(const FMaterialSet& Materials, FPhase4B1HouseReport& Report)
	{
		CreatePieceMesh(FurnDir, TEXT("SM_H_BedSingle"), Materials, Report,
			[](FMeshBuilder& B, TArray<FPieceSpec>& P)
		{
			const int32 SWood = B.Slot(TEXT("MI_WoodDark"));
			const int32 SMat = B.Slot(TEXT("MI_Mattress"));
			const int32 SFab = B.Slot(TEXT("MI_FabricRed"));
			AddPiece(P, SWood, 0.f, 0.f, 0.14f, 0.475f, 1.00f, 0.14f);        // frame 0.95 x 2.00
			AddPiece(P, SWood, 0.f, 1.01f, 0.48f, 0.475f, 0.03f, 0.48f);      // headboard
			AddPiece(P, SMat, 0.f, 0.f, 0.36f, 0.44f, 0.95f, 0.10f);          // mattress
			AddPiece(P, SMat, 0.f, 0.74f, 0.50f, 0.30f, 0.18f, 0.06f);        // pillow
			AddPiece(P, SFab, 0.f, -0.22f, 0.52f, 0.45f, 0.70f, 0.05f);       // blanket
		});

		CreatePieceMesh(FurnDir, TEXT("SM_H_BedDouble"), Materials, Report,
			[](FMeshBuilder& B, TArray<FPieceSpec>& P)
		{
			const int32 SWood = B.Slot(TEXT("MI_WoodDark"));
			const int32 SMat = B.Slot(TEXT("MI_Mattress"));
			const int32 SFab = B.Slot(TEXT("MI_Fabric"));
			AddPiece(P, SWood, 0.f, 0.f, 0.14f, 0.80f, 1.02f, 0.14f);        // frame 1.60 x 2.05
			AddPiece(P, SWood, 0.f, 1.03f, 0.48f, 0.80f, 0.03f, 0.48f);       // headboard
			AddPiece(P, SMat, 0.f, 0.f, 0.36f, 0.76f, 0.97f, 0.10f);          // mattress
			AddPiece(P, SMat, -0.38f, 0.76f, 0.50f, 0.32f, 0.18f, 0.06f);
			AddPiece(P, SMat, 0.38f, 0.76f, 0.50f, 0.32f, 0.18f, 0.06f);
			AddPiece(P, SFab, 0.f, -0.18f, 0.54f, 0.78f, 0.82f, 0.08f);       // duvet
		});

		CreatePieceMesh(FurnDir, TEXT("SM_H_Wardrobe"), Materials, Report,
			[](FMeshBuilder& B, TArray<FPieceSpec>& P)
		{
			const int32 SWood = B.Slot(TEXT("MI_WoodDark"));
			const int32 SDoor = B.Slot(TEXT("MI_DoorInt"));
			const int32 SMetal = B.Slot(TEXT("MI_Metal"));
			AddPiece(P, SWood, 0.f, 0.f, 1.05f, 0.60f, 0.30f, 1.05f);        // 1.20 x 0.60 x 2.10
			AddPiece(P, SDoor, -0.30f, -0.31f, 1.05f, 0.29f, 0.015f, 1.02f);
			AddPiece(P, SDoor, 0.30f, -0.31f, 1.05f, 0.29f, 0.015f, 1.02f);
			AddPiece(P, SMetal, -0.04f, -0.33f, 1.05f, 0.012f, 0.012f, 0.10f);
			AddPiece(P, SMetal, 0.04f, -0.33f, 1.05f, 0.012f, 0.012f, 0.10f);
		});

		CreatePieceMesh(FurnDir, TEXT("SM_H_Nightstand"), Materials, Report,
			[](FMeshBuilder& B, TArray<FPieceSpec>& P)
		{
			const int32 SWood = B.Slot(TEXT("MI_WoodDark"));
			const int32 SMetal = B.Slot(TEXT("MI_Metal"));
			AddPiece(P, SWood, 0.f, 0.f, 0.27f, 0.225f, 0.20f, 0.27f);       // 0.45 x 0.40 x 0.54
			AddPiece(P, SWood, 0.f, -0.205f, 0.38f, 0.20f, 0.012f, 0.09f);
			AddPiece(P, SMetal, 0.f, -0.22f, 0.38f, 0.06f, 0.012f, 0.012f);
		});

		CreatePieceMesh(FurnDir, TEXT("SM_H_TableLamp"), Materials, Report,
			[](FMeshBuilder& B, TArray<FPieceSpec>& P)
		{
			const int32 SMetal = B.Slot(TEXT("MI_Metal"));
			const int32 SShade = B.Slot(TEXT("MI_LampShade"));
			B.Cylinder(FVector(0.f, 0.f, 0.f), FVector(0.f, 0.f, 0.03f), 0.09f, 0.09f, 12, SMetal);
			B.Cylinder(FVector(0.f, 0.f, 0.03f), FVector(0.f, 0.f, 0.24f), 0.02f, 0.02f, 8, SMetal);
			B.Cylinder(FVector(0.f, 0.f, 0.24f), FVector(0.f, 0.f, 0.40f), 0.10f, 0.16f, 12, SShade);
		});

		CreatePieceMesh(FurnDir, TEXT("SM_H_Desk"), Materials, Report,
			[](FMeshBuilder& B, TArray<FPieceSpec>& P)
		{
			const int32 SWood = B.Slot(TEXT("MI_WoodDark"));
			AddPiece(P, SWood, 0.f, 0.f, 0.74f, 0.60f, 0.28f, 0.025f);       // 1.20 x 0.56
			AddPiece(P, SWood, -0.25f, -0.10f, 0.60f, 0.32f, 0.24f, 0.12f);   // drawer block
			AddPiece(P, SWood, 0.52f, 0.f, 0.36f, 0.03f, 0.26f, 0.36f);
			AddPiece(P, SWood, -0.52f, 0.f, 0.36f, 0.03f, 0.26f, 0.36f);
		});

		CreatePieceMesh(FurnDir, TEXT("SM_H_Dresser"), Materials, Report,
			[](FMeshBuilder& B, TArray<FPieceSpec>& P)
		{
			const int32 SWood = B.Slot(TEXT("MI_WoodDark"));
			const int32 SMetal = B.Slot(TEXT("MI_Metal"));
			AddPiece(P, SWood, 0.f, 0.f, 0.42f, 0.50f, 0.225f, 0.42f);       // 1.00 x 0.45 x 0.84
			for (int32 Index = 0; Index < 3; ++Index)
			{
				AddPiece(P, SWood, 0.f, -0.23f, 0.18f + Index * 0.24f, 0.46f, 0.012f, 0.09f);
				AddPiece(P, SMetal, 0.f, -0.245f, 0.18f + Index * 0.24f, 0.10f, 0.012f, 0.012f);
			}
			AddPiece(P, SWood, 0.f, 0.f, 0.85f, 0.52f, 0.235f, 0.015f);
		});

		CreatePieceMesh(FurnDir, TEXT("SM_H_Chest"), Materials, Report,
			[](FMeshBuilder& B, TArray<FPieceSpec>& P)
		{
			const int32 SWood = B.Slot(TEXT("MI_WoodDark"));
			const int32 SFab = B.Slot(TEXT("MI_FabricRed"));
			AddPiece(P, SWood, 0.f, 0.f, 0.21f, 0.45f, 0.25f, 0.21f);        // 0.90 x 0.50 x 0.42
			AddPiece(P, SWood, 0.f, 0.f, 0.435f, 0.46f, 0.26f, 0.025f);      // lid
			AddPiece(P, SFab, 0.f, 0.f, 0.462f, 0.40f, 0.21f, 0.012f);       // folded blanket on top
		});
	}

	/** Bathroom and WC: toilet, basin, mirror, shower cabin, tall cabinet. */
	static void BuildBathroomFurniture(const FMaterialSet& Materials, FPhase4B1HouseReport& Report)
	{
		CreatePieceMesh(FurnDir, TEXT("SM_H_Toilet"), Materials, Report,
			[](FMeshBuilder& B, TArray<FPieceSpec>& P)
		{
			const int32 SCer = B.Slot(TEXT("MI_Ceramic"));
			const int32 SMetal = B.Slot(TEXT("MI_Metal"));
			AddPiece(P, SCer, 0.f, -0.06f, 0.20f, 0.19f, 0.28f, 0.20f);      // bowl
			AddPiece(P, SCer, 0.f, -0.06f, 0.41f, 0.20f, 0.29f, 0.03f);      // seat
			AddPiece(P, SCer, 0.f, 0.24f, 0.62f, 0.20f, 0.09f, 0.22f);       // cistern (against +Y wall)
			AddPiece(P, SMetal, 0.f, 0.16f, 0.84f, 0.05f, 0.02f, 0.02f);     // flush
		});

		CreatePieceMesh(FurnDir, TEXT("SM_H_Basin"), Materials, Report,
			[](FMeshBuilder& B, TArray<FPieceSpec>& P)
		{
			const int32 SCer = B.Slot(TEXT("MI_Ceramic"));
			const int32 SMetal = B.Slot(TEXT("MI_Metal"));
			AddPiece(P, SCer, 0.f, 0.06f, 0.36f, 0.10f, 0.10f, 0.36f);       // pedestal
			AddPiece(P, SCer, 0.f, 0.f, 0.78f, 0.28f, 0.21f, 0.07f);         // bowl
			B.Cylinder(FVector(0.f, 0.16f, 0.85f), FVector(0.f, 0.16f, 0.97f), 0.015f, 0.015f, 8, SMetal);
			AddPiece(P, SMetal, 0.f, 0.10f, 0.965f, 0.014f, 0.06f, 0.014f);
		});

		CreatePieceMesh(FurnDir, TEXT("SM_H_Mirror"), Materials, Report,
			[](FMeshBuilder& B, TArray<FPieceSpec>& P)
		{
			const int32 SWood = B.Slot(TEXT("MI_WoodTrim"));
			const int32 SMirror = B.Slot(TEXT("MI_Mirror"));
			AddPiece(P, SMirror, 0.f, 0.f, 0.f, 0.26f, 0.010f, 0.32f);
			AddPiece(P, SWood, 0.f, 0.012f, 0.335f, 0.29f, 0.020f, 0.015f);
			AddPiece(P, SWood, 0.f, 0.012f, -0.335f, 0.29f, 0.020f, 0.015f);
			AddPiece(P, SWood, -0.29f, 0.012f, 0.f, 0.015f, 0.020f, 0.32f);
			AddPiece(P, SWood, 0.29f, 0.012f, 0.f, 0.015f, 0.020f, 0.32f);
		});

		CreatePieceMesh(FurnDir, TEXT("SM_H_ShowerCabin"), Materials, Report,
			[](FMeshBuilder& B, TArray<FPieceSpec>& P)
		{
			const int32 SCer = B.Slot(TEXT("MI_Ceramic"));
			const int32 SGlass = B.Slot(TEXT("MI_Glass"));
			const int32 SMetal = B.Slot(TEXT("MI_Metal"));
			AddPiece(P, SCer, 0.f, 0.f, 0.07f, 0.45f, 0.45f, 0.07f);         // tray 0.90 x 0.90
			AddPiece(P, SGlass, 0.f, 0.44f, 1.02f, 0.45f, 0.012f, 0.95f);
			AddPiece(P, SGlass, -0.44f, 0.f, 1.02f, 0.012f, 0.45f, 0.95f);
			AddPiece(P, SGlass, 0.44f, 0.f, 1.02f, 0.012f, 0.45f, 0.95f);
			AddPiece(P, SGlass, 0.f, -0.44f, 1.02f, 0.30f, 0.012f, 0.95f);    // partial front
			AddPiece(P, SMetal, 0.24f, -0.44f, 1.02f, 0.02f, 0.02f, 0.95f);   // front post
			AddPiece(P, SMetal, 0.f, -0.05f, 1.98f, 0.02f, 0.02f, 0.06f);
			B.Cylinder(FVector(0.f, 0.20f, 1.99f), FVector(0.f, 0.20f, 1.94f), 0.09f, 0.09f, 10, SMetal);
		});

		CreatePieceMesh(FurnDir, TEXT("SM_H_BathCabinet"), Materials, Report,
			[](FMeshBuilder& B, TArray<FPieceSpec>& P)
		{
			const int32 SWood = B.Slot(TEXT("MI_WoodDark"));
			const int32 SDoor = B.Slot(TEXT("MI_DoorInt"));
			AddPiece(P, SWood, 0.f, 0.f, 0.90f, 0.25f, 0.20f, 0.90f);        // 0.50 x 0.40 x 1.80
			AddPiece(P, SDoor, 0.f, -0.21f, 0.55f, 0.21f, 0.015f, 0.33f);
			AddPiece(P, SDoor, 0.f, -0.21f, 1.26f, 0.21f, 0.015f, 0.33f);
		});
	}

	/** Pantry, hall and outdoor props, plus curtains. */
	static void BuildPropFurniture(const FMaterialSet& Materials, FPhase4B1HouseReport& Report)
	{
		CreatePieceMesh(PropDir, TEXT("SM_H_ShelfUnit"), Materials, Report,
			[](FMeshBuilder& B, TArray<FPieceSpec>& P)
		{
			const int32 SWood = B.Slot(TEXT("MI_WoodDark"));
			const int32 SFrame = B.Slot(TEXT("MI_WoodTrim"));
			AddPiece(P, SWood, 0.f, 0.195f, 0.90f, 0.60f, 0.01f, 0.90f);      // back
			AddPiece(P, SFrame, -0.59f, 0.f, 0.90f, 0.01f, 0.20f, 0.90f);     // sides 1.20 x 0.40 x 1.80
			AddPiece(P, SFrame, 0.59f, 0.f, 0.90f, 0.01f, 0.20f, 0.90f);
			for (int32 Index = 0; Index < 4; ++Index)
			{
				AddPiece(P, SFrame, 0.f, 0.f, 0.05f + Index * 0.56f, 0.58f, 0.19f, 0.015f);
			}
		});

		CreatePieceMesh(PropDir, TEXT("SM_H_Jar"), Materials, Report,
			[](FMeshBuilder& B, TArray<FPieceSpec>& P)
		{
			const int32 SGlass = B.Slot(TEXT("MI_Glass"));
			const int32 SMetal = B.Slot(TEXT("MI_Metal"));
			B.Cylinder(FVector(0.f, 0.f, 0.f), FVector(0.f, 0.f, 0.22f), 0.07f, 0.07f, 12, SGlass);
			B.Cylinder(FVector(0.f, 0.f, 0.22f), FVector(0.f, 0.f, 0.25f), 0.075f, 0.075f, 12, SMetal);
		});

		CreatePieceMesh(PropDir, TEXT("SM_H_Crate"), Materials, Report,
			[](FMeshBuilder& B, TArray<FPieceSpec>& P)
		{
			const int32 SWood = B.Slot(TEXT("MI_WoodTrim"));
			AddPiece(P, SWood, 0.f, 0.f, 0.13f, 0.225f, 0.16f, 0.13f);
			AddPiece(P, SWood, 0.f, 0.f, 0.265f, 0.235f, 0.17f, 0.015f);
		});

		CreatePieceMesh(PropDir, TEXT("SM_H_Basket"), Materials, Report,
			[](FMeshBuilder& B, TArray<FPieceSpec>& P)
		{
			const int32 SFab = B.Slot(TEXT("MI_FabricRed"));
			const int32 SWood = B.Slot(TEXT("MI_WoodTrim"));
			AddPiece(P, SFab, 0.f, 0.f, 0.14f, 0.20f, 0.15f, 0.14f);
			AddPiece(P, SWood, 0.f, 0.f, 0.285f, 0.21f, 0.16f, 0.02f);
		});

		CreatePieceMesh(PropDir, TEXT("SM_H_FlourBin"), Materials, Report,
			[](FMeshBuilder& B, TArray<FPieceSpec>& P)
		{
			const int32 SMetal = B.Slot(TEXT("MI_Metal"));
			AddPiece(P, SMetal, 0.f, 0.f, 0.40f, 0.275f, 0.225f, 0.40f);      // 0.55 x 0.45 x 0.80
			AddPiece(P, SMetal, 0.f, 0.f, 0.83f, 0.285f, 0.235f, 0.03f);
			AddPiece(P, SMetal, 0.f, -0.20f, 0.55f, 0.10f, 0.03f, 0.02f);
		});

		CreatePieceMesh(PropDir, TEXT("SM_H_ShoeCabinet"), Materials, Report,
			[](FMeshBuilder& B, TArray<FPieceSpec>& P)
		{
			const int32 SWood = B.Slot(TEXT("MI_WoodDark"));
			const int32 SDoor = B.Slot(TEXT("MI_DoorInt"));
			const int32 SMetal = B.Slot(TEXT("MI_Metal"));
			AddPiece(P, SWood, 0.f, 0.f, 0.475f, 0.40f, 0.16f, 0.475f);       // 0.80 x 0.32 x 0.95
			AddPiece(P, SDoor, -0.20f, -0.165f, 0.55f, 0.19f, 0.015f, 0.34f);
			AddPiece(P, SDoor, 0.20f, -0.165f, 0.55f, 0.19f, 0.015f, 0.34f);
			AddPiece(P, SMetal, 0.f, -0.185f, 0.55f, 0.012f, 0.012f, 0.10f);
		});

		CreatePieceMesh(PropDir, TEXT("SM_H_Curtain"), Materials, Report,
			[](FMeshBuilder& B, TArray<FPieceSpec>& P)
			{
				const int32 SFab = B.Slot(TEXT("MI_Curtain"));
				B.bTrackCollision = false;   // soft furnishing
				for (int32 Index = -1; Index <= 1; ++Index)
				{
					AddPiece(P, SFab, Index * 0.105f, 0.f, 0.50f, 0.055f, 0.030f, 0.50f);
				}
				AddPiece(P, SFab, 0.f, 0.f, 0.985f, 0.30f, 0.032f, 0.02f);
			});

		CreatePieceMesh(PropDir, TEXT("SM_H_CurtainRod"), Materials, Report,
			[](FMeshBuilder& B, TArray<FPieceSpec>& P)
			{
				const int32 SMetal = B.Slot(TEXT("MI_Metal"));
				B.bTrackCollision = false;
				B.Cylinder(FVector(-0.60f, 0.f, 0.f), FVector(0.60f, 0.f, 0.f), 0.014f, 0.014f, 8, SMetal);
				for (int32 X = -1; X <= 1; X += 2)
				{
					AddPiece(P, SMetal, X * 0.55f, 0.05f, -0.02f, 0.012f, 0.05f, 0.012f);
				}
			});

		CreatePieceMesh(PropDir, TEXT("SM_H_Doormat"), Materials, Report,
			[](FMeshBuilder& B, TArray<FPieceSpec>& P)
			{
				const int32 SFab = B.Slot(TEXT("MI_Fabric"));
				B.bTrackCollision = false;
				AddPiece(P, SFab, 0.f, 0.f, 0.012f, 0.55f, 0.30f, 0.012f);
			});
	}

	/** Door leaves (entrance, interior, small) built around their hinge edge. */
	static void BuildDoorLeaves(const FMaterialSet& Materials, FPhase4B1HouseReport& Report)
	{
		const FString InteriorDir = TEXT("/Game/Game/Environment/House/Interior");
		CreatePieceMesh(InteriorDir, TEXT("SM_H_Door_Ext"), Materials, Report,
			[](FMeshBuilder& B, TArray<FPieceSpec>& P)
		{
			const int32 SLeaf = B.Slot(TEXT("MI_DoorExt"));
			const int32 SGlass = B.Slot(TEXT("MI_Glass"));
			const int32 SMetal = B.Slot(TEXT("MI_Metal"));
			const float W = 0.94f;
			const float H = 2.00f;
			AddPiece(P, SLeaf, W * 0.5f, 0.f, H * 0.5f, W * 0.5f, 0.022f, H * 0.5f);   // leaf
			AddPiece(P, SGlass, W * 0.5f, 0.f, 1.52f, 0.28f, 0.024f, 0.26f);             // glazed top
			AddPiece(P, SLeaf, W * 0.5f, -0.026f, 0.52f, 0.32f, 0.005f, 0.34f);          // panels
			AddPiece(P, SLeaf, W * 0.5f, 0.026f, 0.52f, 0.32f, 0.005f, 0.34f);
			AddPiece(P, SMetal, W - 0.10f, -0.045f, 1.00f, 0.09f, 0.022f, 0.022f);       // handles
			AddPiece(P, SMetal, W - 0.10f, 0.045f, 1.00f, 0.09f, 0.022f, 0.022f);
			for (int32 Index = 0; Index < 3; ++Index)
			{
				AddPiece(P, SMetal, 0.012f, 0.f, 0.25f + Index * 0.75f, 0.014f, 0.036f, 0.05f);   // hinges
			}
		});

		CreatePieceMesh(InteriorDir, TEXT("SM_H_Door_Int"), Materials, Report,
			[](FMeshBuilder& B, TArray<FPieceSpec>& P)
		{
			const int32 SLeaf = B.Slot(TEXT("MI_DoorInt"));
			const int32 SMetal = B.Slot(TEXT("MI_Metal"));
			const float W = 0.80f;
			const float H = 2.00f;
			AddPiece(P, SLeaf, W * 0.5f, 0.f, H * 0.5f, W * 0.5f, 0.020f, H * 0.5f);
			AddPiece(P, SLeaf, W * 0.5f, -0.024f, 0.55f, 0.29f, 0.005f, 0.42f);
			AddPiece(P, SLeaf, W * 0.5f, 0.024f, 0.55f, 0.29f, 0.005f, 0.42f);
			AddPiece(P, SLeaf, W * 0.5f, -0.024f, 1.48f, 0.29f, 0.005f, 0.36f);
			AddPiece(P, SLeaf, W * 0.5f, 0.024f, 1.48f, 0.29f, 0.005f, 0.36f);
			AddPiece(P, SMetal, W - 0.09f, -0.042f, 1.00f, 0.08f, 0.022f, 0.022f);
			AddPiece(P, SMetal, W - 0.09f, 0.042f, 1.00f, 0.08f, 0.022f, 0.022f);
			for (int32 Index = 0; Index < 3; ++Index)
			{
				AddPiece(P, SMetal, 0.012f, 0.f, 0.25f + Index * 0.75f, 0.014f, 0.032f, 0.05f);
			}
		});

		CreatePieceMesh(InteriorDir, TEXT("SM_H_Door_Small"), Materials, Report,
			[](FMeshBuilder& B, TArray<FPieceSpec>& P)
		{
			const int32 SLeaf = B.Slot(TEXT("MI_DoorInt"));
			const int32 SMetal = B.Slot(TEXT("MI_Metal"));
			const float W = 0.70f;
			const float H = 2.00f;
			AddPiece(P, SLeaf, W * 0.5f, 0.f, H * 0.5f, W * 0.5f, 0.020f, H * 0.5f);
			AddPiece(P, SLeaf, W * 0.5f, -0.024f, 0.60f, 0.24f, 0.005f, 0.48f);
			AddPiece(P, SLeaf, W * 0.5f, 0.024f, 0.60f, 0.24f, 0.005f, 0.48f);
			AddPiece(P, SLeaf, W * 0.5f, -0.024f, 1.48f, 0.24f, 0.005f, 0.34f);
			AddPiece(P, SLeaf, W * 0.5f, 0.024f, 1.48f, 0.24f, 0.005f, 0.34f);
			AddPiece(P, SMetal, W - 0.09f, -0.042f, 1.00f, 0.08f, 0.022f, 0.022f);
			AddPiece(P, SMetal, W - 0.09f, 0.042f, 1.00f, 0.08f, 0.022f, 0.022f);
			for (int32 Index = 0; Index < 3; ++Index)
			{
				AddPiece(P, SMetal, 0.012f, 0.f, 0.25f + Index * 0.75f, 0.014f, 0.032f, 0.05f);
			}
		});
	}
	// ------------------------------------------------------------------
	// Asset build entry point
	// ------------------------------------------------------------------
	static FPhase4B1HouseReport BuildHouseAssetsImpl(UWorld* World, const FPhase4B1HouseSpec& Spec)
	{
		FPhase4B1HouseReport Report;
		const FMaterialSet Materials = LoadHouseMaterials();
		for (const FString& Missing : Materials.Missing)
		{
			Report.Warnings.Add(FString::Printf(
				TEXT("material instance missing (the mesh keeps a default material): %s"), *Missing));
		}

		const TArray<FOpening> Plan = PlanOpenings();
		const TArray<FUnitSpec> Units = CollectUnits();

		auto SaveMesh = [&Materials, &Report](const FString& Dir, const TCHAR* Name, FMeshBuilder& Builder)
		{
			UStaticMesh* Mesh = CreateStaticMeshAsset(Dir, FString(Name), Builder, Materials, Report.Warnings);
			if (Mesh != nullptr)
			{
				Report.MeshTriangles += Builder.TriangleCount;
				Report.CreatedAssets.Add(FString::Printf(TEXT("%s/%s [%d slots, %d tris, %d collision boxes]"),
					*Dir, Name, Builder.SlotNames.Num(), Builder.TriangleCount, Builder.CollisionBoxes.Num()));
			}
		};

		// Architecture -----------------------------------------------------
		{
			FMeshBuilder Ext;
			FMeshBuilder Int;
			BuildShellGeometry(Plan, Ext, Int, Report.ExteriorWallPanels, Report.InteriorWallPanels);
			SaveMesh(ArchDir, TEXT("SM_H_WallsExt"), Ext);
			SaveMesh(ArchDir, TEXT("SM_H_WallsInt"), Int);
		}
		{
			FMeshBuilder Builder;
			BuildFoundation(Builder);
			SaveMesh(ArchDir, TEXT("SM_H_Foundation"), Builder);
		}
		{
			FMeshBuilder Builder;
			BuildFloorFinishes(Builder);
			SaveMesh(ArchDir, TEXT("SM_H_Floors"), Builder);
		}
		{
			FMeshBuilder Builder;
			BuildCeilings(Builder);
			SaveMesh(ArchDir, TEXT("SM_H_Ceilings"), Builder);
		}
		{
			FMeshBuilder Builder;
			BuildRoof(Builder);
			SaveMesh(ArchDir, TEXT("SM_H_Roof"), Builder);
		}
		{
			FMeshBuilder Builder;
			BuildChimney(Builder);
			SaveMesh(ArchDir, TEXT("SM_H_Chimney"), Builder);
		}
		{
			FMeshBuilder Builder;
			BuildOpeningUnits(Builder, Units, false);
			SaveMesh(ArchDir, TEXT("SM_H_DoorFrames"), Builder);
		}
		{
			FMeshBuilder Builder;
			BuildOpeningUnits(Builder, Units, true);
			SaveMesh(ArchDir, TEXT("SM_H_WindowFrames"), Builder);
		}
		{
			FMeshBuilder Builder;
			BuildGlazing(Builder, Units);
			SaveMesh(ArchDir, TEXT("SM_H_WindowGlass"), Builder);
		}
		{
			FMeshBuilder Builder;
			BuildInteriorTrim(Builder, Units);
			SaveMesh(ArchDir, TEXT("SM_H_Trim"), Builder);
		}
		{
			FMeshBuilder Builder;
			TArray<FVector2D> Fixtures;
			BuildLightFixtures(Builder, Fixtures);
			Report.LightFixtures = Fixtures.Num();
			SaveMesh(ArchDir, TEXT("SM_H_LightFixtures"), Builder);
		}
		{
			FMeshBuilder Builder;
			BuildSwitches(Builder, Units);
			BuildFittings(Builder);
			SaveMesh(ArchDir, TEXT("SM_H_WallDetails"), Builder);
		}

		// Interior doors, furniture and props -------------------------------
		BuildDoorLeaves(Materials, Report);
		BuildSeatingFurniture(Materials, Report);
		BuildKitchenFurniture(Materials, Report);
		BuildBedroomFurniture(Materials, Report);
		BuildBathroomFurniture(Materials, Report);
		BuildPropFurniture(Materials, Report);

		// Element counts ----------------------------------------------------
		for (const FUnitSpec& Unit : Units)
		{
			if (Unit.bWindow)
			{
				++Report.Windows;
			}
			else if (!Unit.bCased)
			{
				++Report.Doors;
			}
		}

		Report.bSuccess = Report.CreatedAssets.Num() >= 40;
		Report.Message = FString::Printf(TEXT("%d house meshes generated (%d triangles)"),
			Report.CreatedAssets.Num(), Report.MeshTriangles);
		return Report;
	}

	// ------------------------------------------------------------------
	// Level layout
	// ------------------------------------------------------------------
	static UStaticMesh* LoadHouseMesh(const FString& Dir, const TCHAR* Name)
	{
		return LoadObject<UStaticMesh>(nullptr, *FString::Printf(TEXT("%s/%s.%s"), *Dir, Name, Name));
	}

	static AStaticMeshActor* SpawnMeshActor(UWorld* World, UStaticMesh* Mesh, const FVector& LocationCm,
	                                        const FRotator& Rotation, const FVector& Scale, const FString& Label,
	                                        FPhase4B1HouseReport& Report, bool bCollide = true,
	                                        const TCHAR* ExtraTag = nullptr)
	{
		if (Mesh == nullptr)
		{
			Report.Warnings.Add(FString::Printf(TEXT("mesh missing for actor %s"), *Label));
			return nullptr;
		}
		FActorSpawnParameters Params;
		Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		AStaticMeshActor* Actor = World->SpawnActor<AStaticMeshActor>(AStaticMeshActor::StaticClass(),
			FTransform(Rotation, LocationCm, Scale), Params);
		if (Actor == nullptr)
		{
			Report.Warnings.Add(FString::Printf(TEXT("could not spawn %s"), *Label));
			return nullptr;
		}
		UStaticMeshComponent* Component = Actor->GetStaticMeshComponent();
		Component->SetMobility(EComponentMobility::Movable);
		Component->SetStaticMesh(Mesh);
		Component->SetMobility(EComponentMobility::Static);
		Component->SetCollisionEnabled(bCollide ? ECollisionEnabled::QueryAndPhysics : ECollisionEnabled::NoCollision);
#if WITH_EDITOR
		Actor->SetActorLabel(Label);
#endif
		Actor->Tags.Add(TEXT("P4B1_House"));
		if (ExtraTag != nullptr)
		{
			Actor->Tags.Add(FName(ExtraTag));
		}
#if WITH_EDITOR
		Actor->SetFolderPath(FName(TEXT("Phase4B1_House")));
#endif
		Report.CreatedActors.Add(Label);
		return Actor;
	}

	/** Places the thirteen architecture meshes at the house origin. */
	static void PlaceArchitecture(UWorld* World, const FVector& OriginCm, FPhase4B1HouseReport& Report)
	{
		struct FEntry { const TCHAR* Name; const TCHAR* Label; };
		const FEntry Entries[] =
		{
			{ TEXT("SM_H_Foundation"), TEXT("P4B1_Foundation") },
			{ TEXT("SM_H_WallsExt"), TEXT("P4B1_WallsExterior") },
			{ TEXT("SM_H_WallsInt"), TEXT("P4B1_WallsInterior") },
			{ TEXT("SM_H_Floors"), TEXT("P4B1_Floors") },
			{ TEXT("SM_H_Ceilings"), TEXT("P4B1_Ceilings") },
			{ TEXT("SM_H_Roof"), TEXT("P4B1_Roof") },
			{ TEXT("SM_H_Chimney"), TEXT("P4B1_Chimney") },
			{ TEXT("SM_H_DoorFrames"), TEXT("P4B1_DoorFrames") },
			{ TEXT("SM_H_WindowFrames"), TEXT("P4B1_WindowFrames") },
			{ TEXT("SM_H_WindowGlass"), TEXT("P4B1_WindowGlass") },
			{ TEXT("SM_H_Trim"), TEXT("P4B1_Trim") },
			{ TEXT("SM_H_LightFixtures"), TEXT("P4B1_LightFixtures") },
			{ TEXT("SM_H_WallDetails"), TEXT("P4B1_WallDetails") },
		};
		for (const FEntry& Entry : Entries)
		{
			UStaticMesh* Mesh = LoadHouseMesh(ArchDir, Entry.Name);
			SpawnMeshActor(World, Mesh, OriginCm, FRotator::ZeroRotator, FVector::OneVector,
				FString(Entry.Label), Report, Mesh != nullptr && Mesh->GetName().Contains(TEXT("WindowGlass")) == false);
		}
	}

	/** Places every door leaf, hinged at its jamb and swung open against the wall. */
	static int32 PlaceDoorLeaves(UWorld* World, const FVector& OriginCm, float PadHeightM,
	                             const TArray<FUnitSpec>& Units, FPhase4B1HouseReport& Report)
	{
		const FString InteriorDir = TEXT("/Game/Game/Environment/House/Interior");
		int32 Placed = 0;
		for (const FUnitSpec& Unit : Units)
		{
			if (Unit.bWindow || Unit.bCased)
			{
				continue;
			}
			const float Width = Unit.Opening.AlongMax - Unit.Opening.AlongMin;
			const TCHAR* LeafName = (Width > 0.95f) ? TEXT("SM_H_Door_Ext")
				: (Width > 0.80f ? TEXT("SM_H_Door_Int") : TEXT("SM_H_Door_Small"));
			UStaticMesh* Leaf = LoadHouseMesh(InteriorDir, LeafName);
			if (Leaf == nullptr)
			{
				continue;
			}
			const FVector2D Dir = (Unit.B - Unit.A).GetSafeNormal();
			const float BaseYaw = FMath::RadiansToDegrees(FMath::Atan2(Dir.Y, Dir.X));
			// The leaf hangs on the side it swings to, clear of the wall thickness.
			const FVector2D OffsetDir = (Unit.OpenDeg > 0.f) ? FVector2D(-Dir.Y, Dir.X) : FVector2D(Dir.Y, -Dir.X);
			const FVector2D Jamb = Unit.A + Dir * (Unit.Opening.AlongMin + 0.02f);
			const FVector2D Hinge = Jamb + OffsetDir * (Unit.Thickness * 0.5f + 0.034f);
			const FVector Placement(OriginCm.X + Hinge.X * 100.f, OriginCm.Y + Hinge.Y * 100.f,
				PadHeightM * 100.f + FLOOR_Z * 100.f + 1.f);
			const FRotator Rot(0.f, BaseYaw + Unit.OpenDeg, 0.f);
			SpawnMeshActor(World, Leaf, Placement, Rot, FVector::OneVector,
				FString::Printf(TEXT("P4B1_%s"), *Unit.Id), Report, true, TEXT("P4B1_Door"));
			++Placed;
		}
		return Placed;
	}

	/** Places the furniture kit. Coordinates are house-local meters above the floor. */
	static void PlaceFurniture(UWorld* World, const FVector& OriginCm, float PadHeightM, FPhase4B1HouseReport& Report)
	{
		const float FloorZ = PadHeightM * 100.f + FLOOR_Z * 100.f;
		const FString FurnDirLocal = FurnDir;
		const FString PropDirLocal = PropDir;

		auto Place = [&](const FString& Dir, const TCHAR* MeshName, const TCHAR* Label, float X, float Y, float Z,
		                 float Yaw = 0.f, float SX = 1.f, float SY = 1.f, float SZ = 1.f)
		{
			UStaticMesh* Mesh = LoadHouseMesh(Dir, MeshName);
			const FVector Location(OriginCm.X + X * 100.f, OriginCm.Y + Y * 100.f, FloorZ + Z * 100.f);
			SpawnMeshActor(World, Mesh, Location, FRotator(0.f, Yaw, 0.f), FVector(SX, SY, SZ), FString(Label), Report,
				true, TEXT("P4B1_Furniture"));
			++Report.FurnitureItems;
		};

		// Two curtain panels and a rod for one window. bAlongX: the wall runs along X
		// (north/south walls); the panels hang Inward (room side) of the wall face.
		auto Curtains = [&](const TCHAR* Prefix, bool bAlongX, float WallCoord, float Inward,
		                    float WindowFrom, float WindowTo, float Sill, float Height)
		{
			const float PanelZ = Sill - 0.10f;
			const float ScaleZ = (Height + 0.20f) / 1.0f;
			const float P1 = WindowFrom + 0.16f;
			const float P2 = WindowTo - 0.16f;
			const float RodZ = Sill + Height + 0.07f;
			if (bAlongX)
			{
				const float Y = WallCoord + Inward * 0.12f;
				Place(PropDirLocal, TEXT("SM_H_Curtain"), *FString::Printf(TEXT("P4B1_%s_CurtainA"), Prefix),
					P1, Y, PanelZ, 0.f, 1.f, 1.f, ScaleZ);
				Place(PropDirLocal, TEXT("SM_H_Curtain"), *FString::Printf(TEXT("P4B1_%s_CurtainB"), Prefix),
					P2, Y, PanelZ, 0.f, 1.f, 1.f, ScaleZ);
				Place(PropDirLocal, TEXT("SM_H_CurtainRod"), *FString::Printf(TEXT("P4B1_%s_Rod"), Prefix),
					(WindowFrom + WindowTo) * 0.5f, Y, RodZ, 0.f,
					(WindowTo - WindowFrom + 0.55f) / 1.20f, 1.f, 1.f);
			}
			else
			{
				const float X = WallCoord + Inward * 0.12f;
				Place(PropDirLocal, TEXT("SM_H_Curtain"), *FString::Printf(TEXT("P4B1_%s_CurtainA"), Prefix),
					X, P1, PanelZ, 90.f, 1.f, 1.f, ScaleZ);
				Place(PropDirLocal, TEXT("SM_H_Curtain"), *FString::Printf(TEXT("P4B1_%s_CurtainB"), Prefix),
					X, P2, PanelZ, 90.f, 1.f, 1.f, ScaleZ);
				Place(PropDirLocal, TEXT("SM_H_CurtainRod"), *FString::Printf(TEXT("P4B1_%s_Rod"), Prefix),
					X, (WindowFrom + WindowTo) * 0.5f, RodZ, 90.f,
					(WindowTo - WindowFrom + 0.55f) / 1.20f, 1.f, 1.f);
			}
		};

		// --- Salon: sofa on the north wall facing the TV wall, armchair in the
		//     north-east corner, dining zone in the south-east alcove.
		Place(FurnDirLocal, TEXT("SM_H_Sofa"), TEXT("P4B1_Sofa"), 2.60f, 3.75f, 0.f, 0.f);
		Place(FurnDirLocal, TEXT("SM_H_Armchair"), TEXT("P4B1_Armchair"), 4.60f, 3.60f, 0.f, 160.f);
		Place(FurnDirLocal, TEXT("SM_H_CoffeeTable"), TEXT("P4B1_CoffeeTable"), 2.60f, 2.65f, 0.f, 0.f);
		Place(FurnDirLocal, TEXT("SM_H_Rug"), TEXT("P4B1_Rug_Salon"), 2.60f, 2.65f, 0.f, 0.f, 1.3f, 0.9f, 1.f);
		Place(FurnDirLocal, TEXT("SM_H_TVCabinet"), TEXT("P4B1_TVCabinet"), 2.60f, 1.58f, 0.f, 180.f);
		Place(FurnDirLocal, TEXT("SM_H_TV"), TEXT("P4B1_TV"), 2.60f, 1.74f, 0.58f, 180.f);
		Place(FurnDirLocal, TEXT("SM_H_Sideboard"), TEXT("P4B1_Sideboard"), 2.95f, 0.10f, 0.f, 180.f);
		Place(FurnDirLocal, TEXT("SM_H_DiningTable"), TEXT("P4B1_DiningTable_Salon"), 4.20f, 0.55f, 0.f, 0.f);
		Place(FurnDirLocal, TEXT("SM_H_Chair"), TEXT("P4B1_Chair_Salon_A"), 3.65f, 0.55f, 0.f, 90.f);
		Place(FurnDirLocal, TEXT("SM_H_Chair"), TEXT("P4B1_Chair_Salon_B"), 4.75f, 0.55f, 0.f, -90.f);
		Place(FurnDirLocal, TEXT("SM_H_Chair"), TEXT("P4B1_Chair_Salon_C"), 4.20f, 0.12f, 0.f, 180.f);
		Curtains(TEXT("SalonN"), true, IN_HY, -1.f, 1.60f, 3.40f, 0.90f, 1.50f);
		Curtains(TEXT("SalonE"), false, IN_HX, -1.f, 2.00f, 3.40f, 0.90f, 1.50f);

		// --- Kitchen: base run and upper cabinets under the north window, wood range
		//     beside the chimney, fridge against the east wall, table in the middle.
		Place(FurnDirLocal, TEXT("SM_H_KitchenBase"), TEXT("P4B1_KitchenBase"), -4.63f, 3.84f, 0.f, 0.f);
		Place(FurnDirLocal, TEXT("SM_H_KitchenUpper"), TEXT("P4B1_KitchenUpper"), -4.63f, 3.97f, 1.50f, 0.f);
		Place(FurnDirLocal, TEXT("SM_H_Sink"), TEXT("P4B1_Sink"), -3.90f, 3.84f, 0.88f, 0.f);
		Place(FurnDirLocal, TEXT("SM_H_Hob"), TEXT("P4B1_Hob"), -5.30f, 3.84f, 0.88f, 0.f);
		Place(FurnDirLocal, TEXT("SM_H_Fridge"), TEXT("P4B1_Fridge"), -1.90f, 3.20f, 0.f, -90.f);
		Place(FurnDirLocal, TEXT("SM_H_WoodRange"), TEXT("P4B1_WoodRange"), -3.20f, 2.10f, 0.f, 0.f);
		Place(FurnDirLocal, TEXT("SM_H_DiningTable"), TEXT("P4B1_DiningTable_Kitchen"), -4.60f, 2.30f, 0.f, 0.f);
		Place(FurnDirLocal, TEXT("SM_H_Chair"), TEXT("P4B1_Chair_Kitchen_A"), -5.35f, 2.30f, 0.f, 90.f);
		Place(FurnDirLocal, TEXT("SM_H_Chair"), TEXT("P4B1_Chair_Kitchen_B"), -3.85f, 2.30f, 0.f, -90.f);
		Place(FurnDirLocal, TEXT("SM_H_Chair"), TEXT("P4B1_Chair_Kitchen_C"), -4.60f, 1.78f, 0.f, 180.f);
		Place(FurnDirLocal, TEXT("SM_H_Chair"), TEXT("P4B1_Chair_Kitchen_D"), -4.60f, 2.82f, 0.f, 0.f);
		Curtains(TEXT("KitchenN"), true, IN_HY, -1.f, -4.60f, -3.20f, 0.95f, 1.40f);
		Curtains(TEXT("KitchenW"), false, -IN_HX, 1.f, 2.20f, 3.40f, 0.95f, 1.40f);

		// --- Player bedroom: bed head against the north wall, desk on the south
		//     wall, wardrobe beside the door.
		Place(FurnDirLocal, TEXT("SM_H_BedSingle"), TEXT("P4B1_BedSingle"), -3.00f, -2.08f, 0.f, 0.f);
		Place(FurnDirLocal, TEXT("SM_H_Nightstand"), TEXT("P4B1_Nightstand_Player"), -3.75f, -1.35f, 0.f, 180.f);
		Place(FurnDirLocal, TEXT("SM_H_TableLamp"), TEXT("P4B1_Lamp_Player"), -3.75f, -1.35f, 0.54f, 0.f);
		Place(FurnDirLocal, TEXT("SM_H_Wardrobe"), TEXT("P4B1_Wardrobe_Player"), -1.90f, -1.65f, 0.f, -90.f);
		Place(FurnDirLocal, TEXT("SM_H_Desk"), TEXT("P4B1_Desk_Player"), -3.90f, -3.92f, 0.f, 180.f);
		Place(FurnDirLocal, TEXT("SM_H_Chair"), TEXT("P4B1_Chair_Player"), -3.90f, -3.35f, 0.f, 0.f);
		Place(FurnDirLocal, TEXT("SM_H_Rug"), TEXT("P4B1_Rug_Player"), -4.70f, -3.30f, 0.f, 0.f, 0.8f, 0.5f, 1.f);
		Curtains(TEXT("PlayerW"), false, -IN_HX, 1.f, -3.20f, -1.80f, 0.95f, 1.40f);
		Curtains(TEXT("PlayerS"), true, -IN_HY, 1.f, -4.60f, -3.20f, 0.95f, 1.40f);

		// --- Parents' bedroom: double bed on the south wall, dressing corner in the
		//     wardrobe nook.
		Place(FurnDirLocal, TEXT("SM_H_BedDouble"), TEXT("P4B1_BedDouble"), 2.30f, -3.10f, 0.f, 180.f);
		Place(FurnDirLocal, TEXT("SM_H_Nightstand"), TEXT("P4B1_Nightstand_Parents_A"), 1.10f, -3.95f, 0.f, 180.f);
		Place(FurnDirLocal, TEXT("SM_H_Nightstand"), TEXT("P4B1_Nightstand_Parents_B"), 3.50f, -3.95f, 0.f, 180.f);
		Place(FurnDirLocal, TEXT("SM_H_TableLamp"), TEXT("P4B1_Lamp_Parents"), 3.50f, -3.95f, 0.54f, 0.f);
		Place(FurnDirLocal, TEXT("SM_H_Dresser"), TEXT("P4B1_Dresser_Parents"), 5.00f, -2.28f, 0.f, 0.f);
		Place(FurnDirLocal, TEXT("SM_H_Wardrobe"), TEXT("P4B1_Wardrobe_Parents"), 5.42f, -1.10f, 0.f, -90.f);
		Place(FurnDirLocal, TEXT("SM_H_Chest"), TEXT("P4B1_Chest_Parents"), 4.20f, -0.80f, 0.f, 0.f);
		Place(FurnDirLocal, TEXT("SM_H_Rug"), TEXT("P4B1_Rug_Parents"), 2.30f, -2.70f, 0.f, 0.f, 1.2f, 0.6f, 1.f);
		Place(FurnDirLocal, TEXT("SM_H_Mirror"), TEXT("P4B1_Mirror_Parents"), 1.30f, -2.02f, 1.55f, 0.f);
		Curtains(TEXT("ParentsS"), true, -IN_HY, 1.f, 2.20f, 3.60f, 0.95f, 1.40f);
		Curtains(TEXT("ParentsE"), false, IN_HX, -1.f, -3.60f, -2.40f, 0.95f, 1.40f);

		// --- Bathroom: shower cabin in the north-west corner, WC on the south wall,
		//     basin and tall cabinet on the east wall.
		Place(FurnDirLocal, TEXT("SM_H_ShowerCabin"), TEXT("P4B1_ShowerCabin"), -5.25f, 0.41f, 0.f, 0.f);
		Place(FurnDirLocal, TEXT("SM_H_Toilet"), TEXT("P4B1_Toilet_Bath"), -4.60f, -0.57f, 0.f, 180.f);
		Place(FurnDirLocal, TEXT("SM_H_Basin"), TEXT("P4B1_Basin_Bath"), -3.90f, -0.68f, 0.f, 180.f);
		Place(FurnDirLocal, TEXT("SM_H_BathCabinet"), TEXT("P4B1_BathCabinet"), -3.10f, -0.70f, 0.f, 180.f);

		// --- WC: compact, toilet and basin side by side on the north wall.
		Place(FurnDirLocal, TEXT("SM_H_Toilet"), TEXT("P4B1_Toilet_WC"), 1.50f, 0.87f, 0.f, 0.f);
		Place(FurnDirLocal, TEXT("SM_H_Basin"), TEXT("P4B1_Basin_WC"), 0.45f, 0.87f, 0.f, 0.f);

		// --- Pantry: shelf units on the north and south walls, jars on the shelves,
		//     flour bin, crates and a basket.
		Place(PropDirLocal, TEXT("SM_H_ShelfUnit"), TEXT("P4B1_Shelf_Pantry_A"), 0.80f, -0.52f, 0.f, 0.f);
		Place(PropDirLocal, TEXT("SM_H_ShelfUnit"), TEXT("P4B1_Shelf_Pantry_B"), 2.30f, -1.66f, 0.f, 0.f);
		Place(PropDirLocal, TEXT("SM_H_FlourBin"), TEXT("P4B1_FlourBin"), 2.60f, -1.05f, 0.f, 0.f);
		Place(PropDirLocal, TEXT("SM_H_Crate"), TEXT("P4B1_Crate_Pantry_A"), 1.40f, -0.75f, 0.f, 20.f);
		Place(PropDirLocal, TEXT("SM_H_Crate"), TEXT("P4B1_Crate_Pantry_B"), 1.75f, -0.60f, 0.f, -15.f);
		Place(PropDirLocal, TEXT("SM_H_Basket"), TEXT("P4B1_Basket_Pantry"), 2.95f, -1.30f, 0.f, 0.f);
		Place(PropDirLocal, TEXT("SM_H_Jar"), TEXT("P4B1_Jar_Pantry_A"), 0.45f, -0.52f, 1.20f, 0.f);
		Place(PropDirLocal, TEXT("SM_H_Jar"), TEXT("P4B1_Jar_Pantry_B"), 0.80f, -0.52f, 0.63f, 0.f);
		Place(PropDirLocal, TEXT("SM_H_Jar"), TEXT("P4B1_Jar_Pantry_C"), 1.15f, -0.52f, 1.76f, 0.f);
		Place(PropDirLocal, TEXT("SM_H_Jar"), TEXT("P4B1_Jar_Pantry_D"), 2.00f, -1.66f, 1.20f, 0.f);
		Place(PropDirLocal, TEXT("SM_H_Jar"), TEXT("P4B1_Jar_Pantry_E"), 2.60f, -1.66f, 0.63f, 0.f);

		// --- Hall and corridor: the shoe cabinet sits on the east side of the hall,
		//     clear of the front door swing.
		Place(PropDirLocal, TEXT("SM_H_ShoeCabinet"), TEXT("P4B1_ShoeCabinet"), 0.32f, 3.40f, 0.f, -90.f);
		Place(PropDirLocal, TEXT("SM_H_Basket"), TEXT("P4B1_Basket_Corridor"), -1.20f, -1.70f, 0.f, 0.f);
	}
	/** Warm interior lights: one per room plus the entrance porch. */
	static int32 PlaceInteriorLights(UWorld* World, const FVector& OriginCm, float PadHeightM,
	                                 FPhase4B1HouseReport& Report)
	{
		const float CeilingCm = PadHeightM * 100.f + (FLOOR_Z + CEIL_H - 0.30f) * 100.f;
		struct FLightSpec { float X, Y, Intensity; const TCHAR* Label; };
		const FLightSpec Lights[] =
		{
			{ 2.90f, 2.75f, 2600.f, TEXT("P4B1_Light_Salon") },
			{ -3.63f, 2.60f, 2200.f, TEXT("P4B1_Light_Kitchen") },
			{ -3.63f, -2.60f, 1800.f, TEXT("P4B1_Light_PlayerBedroom") },
			{ 2.90f, -3.10f, 1800.f, TEXT("P4B1_Light_ParentsBedroom") },
			{ -3.63f, 0.00f, 1500.f, TEXT("P4B1_Light_Bathroom") },
			{ 1.15f, 0.50f, 1200.f, TEXT("P4B1_Light_WC") },
			{ 1.80f, -1.10f, 1200.f, TEXT("P4B1_Light_Pantry") },
			{ -0.72f, 3.20f, 1600.f, TEXT("P4B1_Light_Hall") },
			{ -0.72f, -2.00f, 1400.f, TEXT("P4B1_Light_Corridor") },
		};

		int32 Count = 0;
		for (const FLightSpec& Light : Lights)
		{
			FActorSpawnParameters Params;
			Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
			const FVector Location(OriginCm.X + Light.X * 100.f, OriginCm.Y + Light.Y * 100.f, CeilingCm);
			APointLight* Actor = World->SpawnActor<APointLight>(APointLight::StaticClass(),
				FTransform(FRotator::ZeroRotator, Location), Params);
			if (Actor == nullptr)
			{
				continue;
			}
			if (UPointLightComponent* Component = Cast<UPointLightComponent>(Actor->GetLightComponent()))
			{
				Component->SetMobility(EComponentMobility::Movable);
				Component->SetIntensity(Light.Intensity);
				Component->SetLightColor(FLinearColor(1.f, 0.86f, 0.68f));
				Component->SetAttenuationRadius(650.f);
				Component->SetCastShadows(false);
			}
#if WITH_EDITOR
			Actor->SetActorLabel(FString(Light.Label));
			Actor->SetFolderPath(FName(TEXT("Phase4B1_House")));
#endif
			Actor->Tags.Add(TEXT("P4B1_House"));
			Report.CreatedActors.Add(FString(Light.Label));
			++Count;
		}

		// Porch light outside the front door, under the veranda edge.
		FActorSpawnParameters Params;
		Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		const FVector Location(OriginCm.X - 1.55f * 100.f, OriginCm.Y + 4.30f * 100.f,
			PadHeightM * 100.f + 2.20f * 100.f);
		if (APointLight* Actor = World->SpawnActor<APointLight>(APointLight::StaticClass(),
			FTransform(FRotator::ZeroRotator, Location), Params))
		{
			if (UPointLightComponent* Component = Cast<UPointLightComponent>(Actor->GetLightComponent()))
			{
				Component->SetMobility(EComponentMobility::Movable);
				Component->SetIntensity(1400.f);
				Component->SetLightColor(FLinearColor(1.f, 0.82f, 0.62f));
				Component->SetAttenuationRadius(500.f);
				Component->SetCastShadows(false);
			}
#if WITH_EDITOR
			Actor->SetActorLabel(TEXT("P4B1_Light_Porch"));
			Actor->SetFolderPath(FName(TEXT("Phase4B1_House")));
#endif
			Actor->Tags.Add(TEXT("P4B1_House"));
			Report.CreatedActors.Add(TEXT("P4B1_Light_Porch"));
			++Count;
		}
		return Count;
	}

	/** Removes the P4B1_* actors of a previous run. */
	static int32 ClearHouseActorsImpl(UWorld* World)
	{
		TArray<AActor*> ToDestroy;
		for (TActorIterator<AActor> It(World); It; ++It)
		{
			AActor* Actor = *It;
			if (IsValid(Actor) &&
				(Actor->ActorHasTag(TEXT("P4B1_House")) || Actor->GetActorLabel().StartsWith(TEXT("P4B1_"))))
			{
				ToDestroy.Add(Actor);
			}
		}
		for (AActor* Actor : ToDestroy)
		{
			if (IsValid(Actor))
			{
				World->DestroyActor(Actor, false, false);
			}
		}
		return ToDestroy.Num();
	}

	/** Removes only the Phase 4B graybox house placeholder. */
	static int32 RemoveLegacyHousePlaceholderImpl(UWorld* World)
	{
		TArray<AActor*> ToDestroy;
		for (TActorIterator<AActor> It(World); It; ++It)
		{
			AActor* Actor = *It;
			if (!IsValid(Actor))
			{
				continue;
			}
			const FString Label = Actor->GetActorLabel();
			if (Label == TEXT("P4B1_LegacyHouse"))
			{
				continue;
			}
			AStaticMeshActor* MeshActor = Cast<AStaticMeshActor>(Actor);
			const bool bLabel = (Label.StartsWith(TEXT("P4B_House"))) ||
				(Label.StartsWith(TEXT("P4B_OldHouse")));
			bool bMesh = false;
			if (MeshActor != nullptr && MeshActor->GetStaticMeshComponent() != nullptr)
			{
				if (const UStaticMesh* Mesh = MeshActor->GetStaticMeshComponent()->GetStaticMesh())
				{
					bMesh = Mesh->GetName() == TEXT("SM_P4B_House");
				}
			}
			if (bLabel || bMesh)
			{
				ToDestroy.Add(Actor);
			}
		}
		for (AActor* Actor : ToDestroy)
		{
			if (IsValid(Actor))
			{
				World->DestroyActor(Actor, false, false);
			}
		}
		return ToDestroy.Num();
	}

	/** Places the whole house: architecture, door leaves, furniture and lights. */
	static float GroundHeightMImpl(UWorld* World, float XM, float YM, bool& bHit)
	{
		FHitResult Hit;
		FCollisionQueryParams Params(SCENE_QUERY_STAT(Phase4B1Ground), false);
		const FVector Start(XM * 100.f, YM * 100.f, 400000.f);
		const FVector End(XM * 100.f, YM * 100.f, -60000.f);
		bHit = World->LineTraceSingleByChannel(Hit, Start, End, ECC_Visibility, Params);
		return bHit ? Hit.ImpactPoint.Z * 0.01f : 0.f;
	}

	/** Places the whole house: architecture, door leaves, furniture and lights. */
	static FPhase4B1HouseReport BuildHouseLayoutImpl(UWorld* World, FPhase4B1HouseSpec Spec)
	{
		FPhase4B1HouseReport Report;
		const FVector2D Centre = Spec.HouseCenter;

		bool bGroundHit = false;
		const float MeasuredPad = GroundHeightMImpl(World, Centre.X - 9.f, Centre.Y, bGroundHit);
		if (Spec.PadHeightM <= 1.f)
		{
			Spec.PadHeightM = bGroundHit ? MeasuredPad : 0.f;
			Report.Warnings.Add(FString::Printf(TEXT("pad height taken from the terrain: %.3f m"), Spec.PadHeightM));
		}
		const float PadM = Spec.PadHeightM;
		const FVector OriginCm(Centre.X * 100.f, Centre.Y * 100.f, PadM * 100.f);

		// A previous run is replaced first.
		Report.RemovedActors.Add(FString::Printf(TEXT("cleared %d previous P4B1 actors"), ClearHouseActorsImpl(World)));

		PlaceArchitecture(World, OriginCm, Report);

		const TArray<FUnitSpec> Units = CollectUnits();
		Report.Doors = PlaceDoorLeaves(World, OriginCm, PadM, Units, Report);
		for (const FUnitSpec& Unit : Units)
		{
			if (Unit.bWindow)
			{
				++Report.Windows;
			}
		}
		if (Spec.bFurniture)
		{
			PlaceFurniture(World, OriginCm, PadM, Report);
		}
		if (Spec.bInteriorLights)
		{
			Report.LightFixtures = PlaceInteriorLights(World, OriginCm, PadM, Report);
		}

		// The Phase 4B graybox house is only removed once the new house exists.
		if (Report.CreatedActors.Num() > 0)
		{
			const int32 Legacy = RemoveLegacyHousePlaceholderImpl(World);
			if (Legacy > 0)
			{
				Report.RemovedActors.Add(FString::Printf(
					TEXT("removed the Phase 4B graybox house placeholder (%d actor)"), Legacy));
			}
		}

		// ---------------------------------------------------------- room table
		const TArray<FRoomRect> Rects = PlanRooms();
		for (const FRoomRect& Rect : Rects)
		{
			FPhase4B1RoomInfo* Found = nullptr;
			for (FPhase4B1RoomInfo& Room : Report.Rooms)
			{
				if (Room.Room == FString(Rect.Name))
				{
					Found = &Room;
					break;
				}
			}
			if (Found == nullptr)
			{
				FPhase4B1RoomInfo Room;
				Room.Room = FString(Rect.Name);
				Room.Contents = FString(Rect.Contents);
				Room.CeilingHeightM = CEIL_H;
				Room.SizeM = FVector2D(Rect.X1 - Rect.X0, Rect.Y1 - Rect.Y0);
				Room.AreaM2 = Room.SizeM.X * Room.SizeM.Y;
				Room.CenterM = FVector2D(Centre.X + (Rect.X0 + Rect.X1) * 0.5f,
					Centre.Y + (Rect.Y0 + Rect.Y1) * 0.5f);
				Report.Rooms.Add(Room);
			}
			else
			{
				// L shaped room: the areas add up, the extents span both rectangles.
				const float Area = (Rect.X1 - Rect.X0) * (Rect.Y1 - Rect.Y0);
				const float Total = Found->AreaM2 + Area;
				const FVector2D RectCentre((Rect.X0 + Rect.X1) * 0.5f, (Rect.Y0 + Rect.Y1) * 0.5f);
				const FVector2D Weighted = (Found->CenterM + FVector2D(-Centre.X, -Centre.Y)
					* Found->AreaM2 + RectCentre * Area) / FMath::Max(1.f, Total);
				Found->AreaM2 = Total;
				Found->CenterM = FVector2D(Centre.X + Weighted.X, Centre.Y + Weighted.Y);
				Found->SizeM.X = FMath::Max(Found->SizeM.X, Rect.X1 - Rect.X0);
				Found->SizeM.Y = FMath::Max(Found->SizeM.Y, Rect.Y1 - Rect.Y0);
			}
		}

		// Doors and windows per room: an opening belongs to the room it opens into.
		for (const FUnitSpec& Unit : Units)
		{
			const FVector2D Dir = (Unit.B - Unit.A).GetSafeNormal();
			const FVector2D P = Unit.A + Dir * (Unit.Opening.AlongMin + Unit.Opening.AlongMax) * 0.5f;
			for (FPhase4B1RoomInfo& Room : Report.Rooms)
			{
				bool bInside = false;
				for (const FRoomRect& Rect : Rects)
				{
					if (Room.Room != FString(Rect.Name))
					{
						continue;
					}
					if (P.X > Rect.X0 - 0.25f && P.X < Rect.X1 + 0.25f &&
						P.Y > Rect.Y0 - 0.25f && P.Y < Rect.Y1 + 0.25f)
					{
						bInside = true;
						break;
					}
				}
				if (!bInside)
				{
					continue;
				}
				if (Unit.bWindow)
				{
					++Room.Windows;
				}
				else if (!Unit.bCased)
				{
					++Room.Doors;
				}
			}
		}

		for (const FPhase4B1RoomInfo& Room : Report.Rooms)
		{
			Report.RoomAreaTotalM2 += Room.AreaM2;
		}
		Report.PadHeightM = PadM;
		Report.FloorLevelM = PadM + FLOOR_Z;
		Report.EaveHeightM = PadM + EAVE_Z;
		Report.RidgeHeightM = PadM + RIDGE_UNDER_Z + ROOF_T / 0.898794f + 0.30f;
		Report.ChimneyTopM = PadM + 6.37f;
		Report.GrossFootprintM2 = Spec.Footprint.X * Spec.Footprint.Y;
		Report.NetInteriorM2 = (Spec.Footprint.X - 2.f * EXT_T) * (Spec.Footprint.Y - 2.f * EXT_T);
		Report.InteriorWallVolumeM2 = FMath::Max(0.f, Report.NetInteriorM2 - Report.RoomAreaTotalM2);

		Report.bSuccess = Report.CreatedActors.Num() >= 15;
		Report.Message = FString::Printf(
			TEXT("house placed at %.2f/%.2f (pad %.3f m): %d actors, %d rooms, %d doors, %d windows"),
			Centre.X, Centre.Y, PadM, Report.CreatedActors.Num(), Report.Rooms.Num(), Report.Doors, Report.Windows);
		return Report;
	}

	// ------------------------------------------------------------------
	// Validation: everything is measured through collision
	// ------------------------------------------------------------------
	static bool TraceHitCm(UWorld* World, const FVector& StartCm, const FVector& EndCm, FVector& OutCm)
	{
		FHitResult Hit;
		FCollisionQueryParams Params(SCENE_QUERY_STAT(Phase4B1Validate), false);
		if (World->LineTraceSingleByChannel(Hit, StartCm, EndCm, ECC_Visibility, Params))
		{
			OutCm = Hit.ImpactPoint;
			return true;
		}
		return false;
	}

	static bool SweepClearCm(UWorld* World, const FVector& FromCm, const FVector& ToCm, float RadiusCm,
	                         FString& OutBlocker)
	{
		FHitResult Hit;
		FCollisionQueryParams Params(SCENE_QUERY_STAT(Phase4B1Validate), false);
		if (World->SweepSingleByChannel(Hit, FromCm, ToCm, FQuat::Identity, ECC_Pawn,
			FCollisionShape::MakeSphere(RadiusCm), Params))
		{
			const AActor* Actor = Hit.GetActor();
			OutBlocker = Actor != nullptr ? Actor->GetActorLabel() : FString(TEXT("static geometry"));
			return false;
		}
		return true;
	}

	static FPhase4B1HouseReport ValidateHouseImpl(UWorld* World, FPhase4B1HouseSpec Spec)
	{
		FPhase4B1HouseReport Report;

		bool bGroundHit = false;
		const float MeasuredPad = GroundHeightMImpl(World, Spec.HouseCenter.X - 9.f, Spec.HouseCenter.Y, bGroundHit);
		const float PadM = (Spec.PadHeightM > 1.f) ? Spec.PadHeightM : MeasuredPad;
		Spec.PadHeightM = PadM;
		const FVector OriginCm(Spec.HouseCenter.X * 100.f, Spec.HouseCenter.Y * 100.f, PadM * 100.f);
		const float FloorCm = PadM * 100.f + FLOOR_Z * 100.f;
		const TArray<FUnitSpec> Units = CollectUnits();
		const float TraceTopCm = PadM * 100.f + 30000.f;

		Report.PadHeightM = PadM;
		Report.FloorLevelM = PadM + FLOOR_Z;
		Report.EaveHeightM = PadM + EAVE_Z;
		Report.Measurements.Add(TEXT("pad_from_terrain_m"), MeasuredPad);
		Report.Measurements.Add(TEXT("pad_used_m"), PadM);

		// --- exterior size and wall thicknesses (the traces avoid the openings).
		{
			FVector Hit;
			const float ZCm = FloorCm + 150.f;
			float WestX = 0.f;
			float EastX = 0.f;
			float SouthY = 0.f;
			float NorthY = 0.f;
			if (TraceHitCm(World, FVector(OriginCm.X - 1200.f, OriginCm.Y + 70.f, ZCm),
				FVector(OriginCm.X + 1200.f, OriginCm.Y + 70.f, ZCm), Hit))
			{
				WestX = (Hit.X - OriginCm.X) * 0.01f;
			}
			if (TraceHitCm(World, FVector(OriginCm.X + 1200.f, OriginCm.Y + 70.f, ZCm),
				FVector(OriginCm.X - 1200.f, OriginCm.Y + 70.f, ZCm), Hit))
			{
				EastX = (Hit.X - OriginCm.X) * 0.01f;
			}
			if (TraceHitCm(World, FVector(OriginCm.X + 480.f, OriginCm.Y + 1200.f, ZCm),
				FVector(OriginCm.X + 480.f, OriginCm.Y - 1200.f, ZCm), Hit))
			{
				NorthY = (Hit.Y - OriginCm.Y) * 0.01f;
			}
			if (TraceHitCm(World, FVector(OriginCm.X + 480.f, OriginCm.Y - 1200.f, ZCm),
				FVector(OriginCm.X + 480.f, OriginCm.Y + 1200.f, ZCm), Hit))
			{
				SouthY = (Hit.Y - OriginCm.Y) * 0.01f;
			}
			Report.Measurements.Add(TEXT("exterior_width_m"), EastX - WestX);
			Report.Measurements.Add(TEXT("exterior_depth_m"), NorthY - SouthY);
			Report.Checks.Add(TEXT("exterior_size_ok"),
				FMath::IsNearlyEqual(EastX - WestX, Spec.Footprint.X, 0.12f) &&
				FMath::IsNearlyEqual(NorthY - SouthY, Spec.Footprint.Y, 0.12f));

			float InnerX = WestX;
			if (TraceHitCm(World, FVector(OriginCm.X - 300.f, OriginCm.Y + 105.f, ZCm),
				FVector(OriginCm.X - 1200.f, OriginCm.Y + 105.f, ZCm), Hit))
			{
				InnerX = (Hit.X - OriginCm.X) * 0.01f;
			}
			Report.Measurements.Add(TEXT("exterior_wall_thickness_m"), InnerX - WestX);
			Report.Checks.Add(TEXT("exterior_wall_thickness_ok"),
				FMath::IsNearlyEqual(InnerX - WestX, EXT_T, 0.05f));

			float PartitionWest = 0.f;
			float PartitionEast = 0.f;
			const float PartitionZ = FloorCm + 100.f;
			if (TraceHitCm(World, FVector(OriginCm.X - 72.f, OriginCm.Y + 105.f, PartitionZ),
				FVector(OriginCm.X - 500.f, OriginCm.Y + 105.f, PartitionZ), Hit))
			{
				PartitionEast = (Hit.X - OriginCm.X) * 0.01f;
			}
			if (TraceHitCm(World, FVector(OriginCm.X - 500.f, OriginCm.Y + 105.f, PartitionZ),
				FVector(OriginCm.X + 500.f, OriginCm.Y + 105.f, PartitionZ), Hit))
			{
				PartitionWest = (Hit.X - OriginCm.X) * 0.01f;
			}
			Report.Measurements.Add(TEXT("partition_thickness_m"), PartitionEast - PartitionWest);
			Report.Checks.Add(TEXT("partition_thickness_ok"),
				FMath::IsNearlyEqual(PartitionEast - PartitionWest, INT_T, 0.05f));
		}

		// --- roof, ridge and chimney heights (measured from above).
		{
			auto RoofTopAt = [&](float LocalX, float LocalY) -> float
			{
				FVector Hit;
				const float X = OriginCm.X + LocalX * 100.f;
				const float Y = OriginCm.Y + LocalY * 100.f;
				if (TraceHitCm(World, FVector(X, Y, TraceTopCm), FVector(X, Y, OriginCm.Z - 100.f), Hit))
				{
					return static_cast<float>((Hit.Z - OriginCm.Z) * 0.01);
				}
				return 0.f;
			};
			const float South = RoofTopAt(0.f, -2.50f);
			const float North = RoofTopAt(0.f, 2.50f);
			const float Ridge = RoofTopAt(0.f, 0.f);
			const float Chimney = RoofTopAt(-3.20f, 1.40f);
			Report.Measurements.Add(TEXT("roof_slope_south_top_m"), South);
			Report.Measurements.Add(TEXT("roof_slope_north_top_m"), North);
			Report.Measurements.Add(TEXT("roof_ridge_top_m"), Ridge);
			Report.Measurements.Add(TEXT("chimney_top_m"), Chimney);
			Report.Checks.Add(TEXT("roof_both_slopes_present"), South > EAVE_Z + 0.5f && North > EAVE_Z + 0.5f);
			Report.Checks.Add(TEXT("roof_is_pitched"), Ridge - FMath::Max(South, North) > 1.20f);
			Report.Checks.Add(TEXT("chimney_above_roof"), Chimney > FMath::Max(South, North) + 0.40f);
			Report.RidgeHeightM = PadM + Ridge;
			Report.ChimneyTopM = PadM + Chimney;
		}

		// --- per room: the floor supports the player and there is a ceiling above.
		{
			struct FRoomProbe { const TCHAR* Name; float X, Y; };
			const FRoomProbe Probes[] =
			{
				{ TEXT("Salon"), 0.60f, 3.90f },
				{ TEXT("Mutfak"), -2.60f, 3.40f },
				{ TEXT("Oyuncu YO"), -4.30f, -1.40f },
				{ TEXT("Ebeveyn YO"), 4.00f, -3.60f },
				{ TEXT("Banyo"), -3.60f, 0.20f },
				{ TEXT("WC"), 1.15f, 0.20f },
				{ TEXT("Kiler"), 2.10f, -1.10f },
				{ TEXT("Koridor"), -0.72f, 1.00f },
			};
			bool bFloors = true;
			bool bCeilings = true;
			for (const FRoomProbe& Probe : Probes)
			{
				const float X = OriginCm.X + Probe.X * 100.f;
				const float Y = OriginCm.Y + Probe.Y * 100.f;
				FVector Hit;
				float FloorZ = -999.f;
				float CeilZ = -999.f;
				if (TraceHitCm(World, FVector(X, Y, FloorCm + 120.f), FVector(X, Y, FloorCm - 400.f), Hit))
				{
					FloorZ = (Hit.Z - OriginCm.Z) * 0.01f;
				}
				if (TraceHitCm(World, FVector(X, Y, FloorCm + 100.f), FVector(X, Y, FloorCm + 2000.f), Hit))
				{
					CeilZ = (Hit.Z - OriginCm.Z) * 0.01f;
				}
				Report.Measurements.Add(FString::Printf(TEXT("floor_%s_m"), Probe.Name), FloorZ);
				Report.Measurements.Add(FString::Printf(TEXT("ceiling_%s_m"), Probe.Name), CeilZ);
				const bool bFloorOk = FMath::Abs(FloorZ - FLOOR_Z) <= 0.08f;
				const bool bCeilOk = FMath::Abs(CeilZ - (FLOOR_Z + CEIL_H)) <= 0.16f;
				bFloors &= bFloorOk;
				bCeilings &= bCeilOk;
				if (!bFloorOk)
				{
					Report.Failures.Add(FString::Printf(TEXT("floor of %s is not where it should be (%.2f m)"),
						Probe.Name, FloorZ));
				}
				if (!bCeilOk)
				{
					Report.Failures.Add(FString::Printf(TEXT("ceiling of %s is not where it should be (%.2f m)"),
						Probe.Name, CeilZ));
				}
			}
			Report.Checks.Add(TEXT("room_floors_solid"), bFloors);
			Report.Checks.Add(TEXT("room_ceilings_present"), bCeilings);
		}

		// --- doorways: a probe must pass through every opening.
		{
			const float SweepZ = FloorCm + 85.f;
			bool bDoors = true;
			for (const FUnitSpec& Unit : Units)
			{
				if (Unit.bCased)
				{
					continue;   // the wide cased opening is tested separately below
				}
				const FVector2D Dir = (Unit.B - Unit.A).GetSafeNormal();
				const FVector2D Inward = (Unit.OpenDeg > 0.f) ? FVector2D(-Dir.Y, Dir.X) : FVector2D(Dir.Y, -Dir.X);
				const FVector2D Door = Unit.A + Dir * (Unit.Opening.AlongMin + Unit.Opening.AlongMax) * 0.5f;
				const FVector2D Outside = Door - Inward * 1.00f;
				const FVector2D Inside = Door + Inward * 1.20f;
				FString Blocker;
				const bool bClear = SweepClearCm(World,
					FVector(OriginCm.X + Outside.X * 100.f, OriginCm.Y + Outside.Y * 100.f, SweepZ),
					FVector(OriginCm.X + Inside.X * 100.f, OriginCm.Y + Inside.Y * 100.f, SweepZ),
					20.f, Blocker);
				Report.Checks.Add(FString::Printf(TEXT("door_usable_%s"), *Unit.Id), bClear);
				if (!bClear)
				{
					bDoors = false;
					Report.Failures.Add(FString::Printf(TEXT("the doorway %s is blocked by %s"), *Unit.Id, *Blocker));
				}
			}
			Report.Checks.Add(TEXT("all_doorways_usable"), bDoors);

			FString Blocker;
			const bool bSalon = SweepClearCm(World,
				FVector(OriginCm.X - 100.f, OriginCm.Y + 210.f, SweepZ),
				FVector(OriginCm.X + 180.f, OriginCm.Y + 210.f, SweepZ), 20.f, Blocker);
			Report.Checks.Add(TEXT("hall_to_salon_open"), bSalon);
			if (!bSalon)
			{
				Report.Failures.Add(FString::Printf(TEXT("the hall cannot reach the salon (%s)"), *Blocker));
			}
		}

		// --- walkability: entrance, hall, corridor and every room.
		{
			const float SweepZ = FloorCm + 85.f;
			auto Local = [&](float X, float Y)
			{
				return FVector(OriginCm.X + X * 100.f, OriginCm.Y + Y * 100.f, SweepZ);
			};
			struct FLeg { const TCHAR* Name; FVector From; FVector To; };
			const FLeg Legs[] =
			{
				{ TEXT("entrance_to_hall"), Local(-0.72f, 5.20f), Local(-0.72f, 3.60f) },
				{ TEXT("hall_to_corridor"), Local(-0.72f, 3.60f), Local(-0.72f, 0.00f) },
				{ TEXT("corridor_to_rear"), Local(-0.72f, 0.00f), Local(-0.72f, -3.60f) },
				{ TEXT("corridor_to_salon"), Local(-0.72f, 2.10f), Local(1.20f, 2.10f) },
				{ TEXT("corridor_to_kitchen"), Local(-0.72f, 2.02f), Local(-2.60f, 2.02f) },
				{ TEXT("corridor_to_bath"), Local(-0.72f, -0.07f), Local(-2.60f, -0.07f) },
				{ TEXT("corridor_to_player"), Local(-0.72f, -2.97f), Local(-2.60f, -2.97f) },
				{ TEXT("corridor_to_wc"), Local(-0.72f, 0.32f), Local(1.30f, 0.32f) },
				{ TEXT("corridor_to_pantry"), Local(-0.72f, -1.37f), Local(1.30f, -1.37f) },
				{ TEXT("corridor_to_parents"), Local(-0.72f, -2.87f), Local(1.30f, -2.87f) },
			};
			bool bWalk = true;
			for (const FLeg& Leg : Legs)
			{
				FString Blocker;
				const bool bClear = SweepClearCm(World, Leg.From, Leg.To, 20.f, Blocker);
				Report.Checks.Add(FString::Printf(TEXT("walk_%s"), Leg.Name), bClear);
				if (!bClear)
				{
					bWalk = false;
					Report.Failures.Add(FString::Printf(TEXT("%s is blocked by %s"), Leg.Name, *Blocker));
				}
			}
			Report.Checks.Add(TEXT("player_can_walk_through_the_house"), bWalk);
		}

		// --- furniture and props: nothing outside the house, nothing in a wall.
		{
			struct FBand { float X0, X1, Y0, Y1; };
			TArray<FBand> Bands;
			Bands.Add({ -OUT_HX, OUT_HX, OUT_HY - EXT_T, OUT_HY });
			Bands.Add({ -OUT_HX, OUT_HX, -OUT_HY, -OUT_HY + EXT_T });
			Bands.Add({ -OUT_HX, -OUT_HX + EXT_T, -OUT_HY, OUT_HY });
			Bands.Add({ OUT_HX - EXT_T, OUT_HX, -OUT_HY, OUT_HY });
			for (const FWallRun& Run : InteriorRuns())
			{
				const float Half = Run.Thickness * 0.5f;
				FBand Band;
				Band.X0 = static_cast<float>(FMath::Min(Run.A.X, Run.B.X)) - Half;
				Band.X1 = static_cast<float>(FMath::Max(Run.A.X, Run.B.X)) + Half;
				Band.Y0 = static_cast<float>(FMath::Min(Run.A.Y, Run.B.Y)) - Half;
				Band.Y1 = static_cast<float>(FMath::Max(Run.A.Y, Run.B.Y)) + Half;
				Bands.Add(Band);
			}

			int32 Checked = 0;
			int32 Clipping = 0;
			int32 Outside = 0;
			for (TActorIterator<AActor> It(World); It; ++It)
			{
				AActor* Actor = *It;
				if (!IsValid(Actor) || !Actor->ActorHasTag(TEXT("P4B1_Furniture")))
				{
					continue;   // only furniture and props are checked against the walls
				}
				UStaticMeshComponent* Component = Actor->FindComponentByClass<UStaticMeshComponent>();
				if (Component == nullptr || Component->GetStaticMesh() == nullptr)
				{
					continue;   // interior lights have no mesh
				}
				FVector BoundsOrigin;
				FVector BoundsExtent;
				Actor->GetActorBounds(true, BoundsOrigin, BoundsExtent);
				const float X0 = (BoundsOrigin.X - BoundsExtent.X - OriginCm.X) * 0.01f - 0.01f;
				const float X1 = (BoundsOrigin.X + BoundsExtent.X - OriginCm.X) * 0.01f + 0.01f;
				const float Y0 = (BoundsOrigin.Y - BoundsExtent.Y - OriginCm.Y) * 0.01f - 0.01f;
				const float Y1 = (BoundsOrigin.Y + BoundsExtent.Y - OriginCm.Y) * 0.01f + 0.01f;
				++Checked;
				if (X0 < -IN_HX - 0.05f || X1 > IN_HX + 0.05f || Y0 < -IN_HY - 0.05f || Y1 > IN_HY + 0.05f)
				{
					++Outside;
					Report.Failures.Add(FString::Printf(TEXT("%s pokes out of the house (%.2f..%.2f / %.2f..%.2f)"),
						*Actor->GetActorLabel(), X0, X1, Y0, Y1));
					continue;
				}
				for (const FBand& Band : Bands)
				{
					if (X0 < Band.X1 - 0.01f && X1 > Band.X0 + 0.01f &&
						Y0 < Band.Y1 - 0.01f && Y1 > Band.Y0 + 0.01f)
					{
						++Clipping;
						Report.Failures.Add(FString::Printf(
							TEXT("%s clips into the wall band (%.2f..%.2f / %.2f..%.2f), furniture (%.2f..%.2f / %.2f..%.2f)"),
							*Actor->GetActorLabel(), Band.X0, Band.X1, Band.Y0, Band.Y1, X0, X1, Y0, Y1));
						break;
					}
				}
			}
			Report.Measurements.Add(TEXT("mesh_actors_checked"), static_cast<float>(Checked));
			Report.Measurements.Add(TEXT("mesh_actors_clipping_walls"), static_cast<float>(Clipping));
			Report.Measurements.Add(TEXT("mesh_actors_outside_house"), static_cast<float>(Outside));
			Report.Checks.Add(TEXT("no_furniture_clips_walls"), Clipping == 0 && Outside == 0 && Checked > 20);
		}

		// --- foundation contact: the plinth sits on the terrain around the house.
		{
			FVector Hit;
			float PlinthTop = 0.f;
			if (TraceHitCm(World, FVector(OriginCm.X + 480.f, OriginCm.Y + 460.f, OriginCm.Z + 400.f),
				FVector(OriginCm.X + 480.f, OriginCm.Y + 460.f, OriginCm.Z - 400.f), Hit))
			{
				PlinthTop = (Hit.Z - OriginCm.Z) * 0.01f;
			}
			Report.Measurements.Add(TEXT("plinth_top_m"), PlinthTop);
			Report.Checks.Add(TEXT("foundation_anchors_house"), PlinthTop > 0.10f && PlinthTop <= FLOOR_Z + 0.01f);
		}

		for (const TPair<FString, bool>& Check : Report.Checks)
		{
			if (!Check.Value)
			{
				Report.Failures.AddUnique(Check.Key);
			}
		}
		Report.bAllChecksPassed = Report.Failures.Num() == 0 && Report.Checks.Num() >= 20;
		Report.bSuccess = Report.bAllChecksPassed;
		Report.Message = FString::Printf(TEXT("house validation: %d checks, %d failures"),
			Report.Checks.Num(), Report.Failures.Num());
		return Report;
	}
#endif
}

// ----------------------------------------------------------------------
// Public API
// ----------------------------------------------------------------------
namespace
{
	UWorld* ResolveHouseWorld(UObject* WorldContextObject)
	{
		return GEngine != nullptr
			? GEngine->GetWorldFromContextObject(WorldContextObject, EGetWorldErrorMode::LogAndReturnNull)
			: nullptr;
	}
}

#if WITH_EDITOR
FPhase4B1HouseReport UPhase4B1HouseBuilder::BuildHouseAssets(UObject* WorldContextObject, const FPhase4B1HouseSpec& Spec)
{
	UWorld* World = ResolveHouseWorld(WorldContextObject);
	if (World == nullptr)
	{
		FPhase4B1HouseReport Report;
		Report.Message = TEXT("no world: the house assets were not generated");
		return Report;
	}
	return Phase4B1::BuildHouseAssetsImpl(World, Spec);
}

FPhase4B1HouseReport UPhase4B1HouseBuilder::BuildHouseLayout(UObject* WorldContextObject, const FPhase4B1HouseSpec& Spec)
{
	UWorld* World = ResolveHouseWorld(WorldContextObject);
	if (World == nullptr)
	{
		FPhase4B1HouseReport Report;
		Report.Message = TEXT("no world: the house was not placed");
		return Report;
	}
	return Phase4B1::BuildHouseLayoutImpl(World, Spec);
}

FPhase4B1HouseReport UPhase4B1HouseBuilder::ValidateHouse(UObject* WorldContextObject, const FPhase4B1HouseSpec& Spec)
{
	UWorld* World = ResolveHouseWorld(WorldContextObject);
	if (World == nullptr)
	{
		FPhase4B1HouseReport Report;
		Report.Message = TEXT("no world: the house was not validated");
		return Report;
	}
	return Phase4B1::ValidateHouseImpl(World, Spec);
}

int32 UPhase4B1HouseBuilder::ClearHouseActors(UObject* WorldContextObject)
{
	UWorld* World = ResolveHouseWorld(WorldContextObject);
	return World != nullptr ? Phase4B1::ClearHouseActorsImpl(World) : 0;
}

int32 UPhase4B1HouseBuilder::RemoveLegacyHousePlaceholder(UObject* WorldContextObject)
{
	UWorld* World = ResolveHouseWorld(WorldContextObject);
	return World != nullptr ? Phase4B1::RemoveLegacyHousePlaceholderImpl(World) : 0;
}

float UPhase4B1HouseBuilder::GroundHeightM(UObject* WorldContextObject, float XM, float YM, bool& bHit)
{
	UWorld* World = ResolveHouseWorld(WorldContextObject);
	return World != nullptr ? Phase4B1::GroundHeightMImpl(World, XM, YM, bHit) : 0.f;
}
#else
FPhase4B1HouseReport UPhase4B1HouseBuilder::BuildHouseAssets(UObject* WorldContextObject, const FPhase4B1HouseSpec& Spec)
{
	FPhase4B1HouseReport Report;
	Report.Message = TEXT("Phase 4B-1 asset generation is editor only");
	return Report;
}

FPhase4B1HouseReport UPhase4B1HouseBuilder::BuildHouseLayout(UObject* WorldContextObject, const FPhase4B1HouseSpec& Spec)
{
	FPhase4B1HouseReport Report;
	Report.Message = TEXT("Phase 4B-1 layout is editor only");
	return Report;
}

FPhase4B1HouseReport UPhase4B1HouseBuilder::ValidateHouse(UObject* WorldContextObject, const FPhase4B1HouseSpec& Spec)
{
	FPhase4B1HouseReport Report;
	Report.Message = TEXT("Phase 4B-1 validation is editor only");
	return Report;
}

int32 UPhase4B1HouseBuilder::ClearHouseActors(UObject* WorldContextObject)
{
	return 0;
}

int32 UPhase4B1HouseBuilder::RemoveLegacyHousePlaceholder(UObject* WorldContextObject)
{
	return 0;
}

float UPhase4B1HouseBuilder::GroundHeightM(UObject* WorldContextObject, float XM, float YM, bool& bHit)
{
	bHit = false;
	return 0.f;
}
#endif

