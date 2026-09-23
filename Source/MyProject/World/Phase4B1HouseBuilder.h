// Copyright Epic Games, Inc. All Rights Reserved.
// Phase 4B-1 - realistic rural Turkish detached house.
//
// Phase 4B placed a primitive graybox house (four wall blocks) on the Phase 4A/4B
// home pad. This builder replaces ONLY that structure with a properly constructed
// single storey family house: real floor plan, exterior and interior walls with
// believable thickness, door and window openings with frames/leaves/glass, floor
// slab on a foundation, ceilings, a pitched roof with overhangs, ridge, gutters,
// chimney, plus interiors (skirting, trims, switches, heaters, light fixtures) and
// correctly scaled furniture in every room.
//
// Everything is generated procedurally (editor time) from mesh descriptions and
// placed as level actors; no external art assets are used. The world (landscape,
// lighting, player system, interaction, vehicle, World Partition) is untouched and
// the terrain is not redesigned: the house sits on the existing flat home pad with
// its own foundation and steps.

#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"

#include "Phase4B1HouseBuilder.generated.h"

/**
 * Dimensions of the Phase 4B-1 house in meters. The defaults build a 12.04 x 9.00 m
 * single storey house (94 m2 net interior) centred on the Phase 4B house position,
 * keeping the Phase 4B veranda/yard relationship intact.
 */
USTRUCT(BlueprintType)
struct FPhase4B1HouseSpec
{
	GENERATED_BODY()

	/** World position (meters) of the house centre. */
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B1")
	FVector2D HouseCenter = FVector2D(760.f, 785.8f);

	/** Footprint (meters). 12.04 x 9.00 matches the Phase 4B veranda width. */
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B1")
	FVector2D Footprint = FVector2D(12.04f, 9.0f);

	/** Exterior wall thickness (m). Real masonry: 0.30 m. */
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B1")
	float ExteriorWallT = 0.30f;

	/** Interior partition thickness (m). */
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B1")
	float InteriorWallT = 0.12f;

	/** Finished interior floor level above the terrain pad (m). */
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B1")
	float FloorLevelM = 0.45f;

	/** Interior ceiling height (m), floor surface to ceiling underside. */
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B1")
	float CeilingHeightM = 2.70f;

	/** Ceiling slab thickness (m). */
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B1")
	float CeilingSlabT = 0.22f;

	/** Roof slab thickness (m). */
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B1")
	float RoofSlabT = 0.22f;

	/** Roof pitch (degrees). 26 deg is a common rural Turkish tile roof. */
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B1")
	float RoofPitchDeg = 26.f;

	/** Eaves overhang beyond the wall face (m). */
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B1")
	float EaveOverhangM = 0.55f;

	/** Gable end overhang beyond the wall face (m). */
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B1")
	float GableOverhangM = 0.30f;

	/** Terrain pad height (m). 0 = measure it through collision. */
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B1")
	float PadHeightM = 0.f;

	/** Place interior point lights (one per room + hall). */
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B1")
	bool bInteriorLights = true;

	/** Place the furniture kit. */
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B1")
	bool bFurniture = true;
};

/** One room of the finished floor plan. */
USTRUCT(BlueprintType)
struct FPhase4B1RoomInfo
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B1")
	FString Room;

	/** Inner clear size in meters (X x Y). */
	UPROPERTY(BlueprintReadOnly, Category = "Phase4B1")
	FVector2D SizeM = FVector2D::ZeroVector;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B1")
	float AreaM2 = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B1")
	float CeilingHeightM = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B1")
	int32 Doors = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B1")
	int32 Windows = 0;

	/** Room centre (meters, world XY) and the finished floor height (world Z). */
	UPROPERTY(BlueprintReadOnly, Category = "Phase4B1")
	FVector2D CenterM = FVector2D::ZeroVector;

	/** Description of what the player finds in the room. */
	UPROPERTY(BlueprintReadOnly, Category = "Phase4B1")
	FString Contents;
};

/** Result of a Phase 4B-1 build / validation step. */
USTRUCT(BlueprintType)
struct FPhase4B1HouseReport
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B1")
	bool bSuccess = false;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B1")
	FString Message;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B1")
	TArray<FString> Warnings;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B1")
	TArray<FString> CreatedAssets;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B1")
	TArray<FString> CreatedActors;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B1")
	TArray<FString> RemovedActors;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B1")
	TArray<FPhase4B1RoomInfo> Rooms;

	// ------------------------------------------------------------- dimensions
	UPROPERTY(BlueprintReadOnly, Category = "Phase4B1")
	float PadHeightM = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B1")
	float FloorLevelM = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B1")
	float EaveHeightM = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B1")
	float RidgeHeightM = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B1")
	float ChimneyTopM = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B1")
	float GrossFootprintM2 = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B1")
	float NetInteriorM2 = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B1")
	float RoomAreaTotalM2 = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B1")
	float InteriorWallVolumeM2 = 0.f;

	// ----------------------------------------------------------- element counts
	UPROPERTY(BlueprintReadOnly, Category = "Phase4B1")
	int32 ExteriorWallPanels = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B1")
	int32 InteriorWallPanels = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B1")
	int32 Doors = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B1")
	int32 Windows = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B1")
	int32 FurnitureItems = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B1")
	int32 LightFixtures = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B1")
	int32 MeshTriangles = 0;

	// -------------------------------------------------------------- validation
	UPROPERTY(BlueprintReadOnly, Category = "Phase4B1")
	TMap<FString, bool> Checks;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B1")
	TMap<FString, float> Measurements;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B1")
	TArray<FString> Failures;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B1")
	bool bAllChecksPassed = false;
};

/**
 * Phase 4B-1 house builder (editor only). In a cooked runtime build the functions
 * report that they are unavailable.
 */
UCLASS()
class MYPROJECT_API UPhase4B1HouseBuilder : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	/**
	 * Generates the house asset kit into /Game/Game/Environment/House:
	 * Architecture (foundation, exterior/interior walls, floors, ceilings, roof,
	 * chimney, door frames, window frames, glass, trim, wall details),
	 * Interior (three door leaves) and Furniture/Props (every furniture item and
	 * prop the layout places). Existing assets with the same name are replaced.
	 */
	UFUNCTION(BlueprintCallable, Category = "MyProject|Phase4B1")
	static FPhase4B1HouseReport BuildHouseAssets(UObject* WorldContextObject, const FPhase4B1HouseSpec& Spec);

	/**
	 * Places the house in the level: the architecture meshes sit at the house
	 * origin, every door leaf, furniture piece, prop and interior light is placed
	 * individually, and the Phase 4B graybox house actor (SM_P4B_House) is removed
	 * once the new house exists. Only Phase 4B-1 actors and that single placeholder
	 * are touched.
	 */
	UFUNCTION(BlueprintCallable, Category = "MyProject|Phase4B1")
	static FPhase4B1HouseReport BuildHouseLayout(UObject* WorldContextObject, const FPhase4B1HouseSpec& Spec);

	/**
	 * Measures the finished house through collision: exterior size, floor/ceiling/
	 * roof heights, room floors and ceilings, doorway clearances, furniture inside
	 * its room and a walkability check that sweeps from the entrance through the
	 * hall/corridor into every room.
	 */
	UFUNCTION(BlueprintCallable, Category = "MyProject|Phase4B1")
	static FPhase4B1HouseReport ValidateHouse(UObject* WorldContextObject, const FPhase4B1HouseSpec& Spec);

	/** Removes the Phase 4B-1 actors (P4B1_*) so a build can be repeated. */
	UFUNCTION(BlueprintCallable, Category = "MyProject|Phase4B1")
	static int32 ClearHouseActors(UObject* WorldContextObject);

	/** Removes the Phase 4B graybox house placeholder (SM_P4B_House / P4B_House). */
	UFUNCTION(BlueprintCallable, Category = "MyProject|Phase4B1")
	static int32 RemoveLegacyHousePlaceholder(UObject* WorldContextObject);

	/** Terrain height (meters) at a world position (meters) measured through collision. */
	UFUNCTION(BlueprintCallable, Category = "MyProject|Phase4B1")
	static float GroundHeightM(UObject* WorldContextObject, float XM, float YM, bool& bHit);
};
