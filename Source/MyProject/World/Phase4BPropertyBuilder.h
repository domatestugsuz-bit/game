// Copyright Epic Games, Inc. All Rights Reserved.
// Phase 4B - player home property builder (house, veranda, garage, shed, concrete
// yard, driveway and the surrounding pine forest).
//
// Editor automation helper (Python-callable). It works on the terrain that Phase 4A
// created: the home pad is preserved, only the immediate property region is refined
// (the flat pad melts into a natural shoulder instead of reading as a plateau) and
// the driveway is graded out of it. Everything outside that region stays untouched.
// The property structures and the pine forest are generated procedurally - no
// external art assets are needed and none were available at this stage.

#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"

#include "Phase4BPropertyBuilder.generated.h"

class UMaterialInterface;

/**
 * Dimensions and anchors of the home property. All values are meters in world space:
 * +X is east, +Y is north, Z is up. The defaults are the Phase 4B design values for
 * the Phase 4A home pad at (750, 750).
 */
USTRUCT(BlueprintType)
struct FPhase4BHomeSpec
{
	GENERATED_BODY()

	/** Phase 4A home pad centre; the whole property is built around it. */
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B")
	FVector2D PropertyCenter = FVector2D(750.f, 750.f);

	/** Levelled construction footprint (house + veranda + yard + garage + shed). */
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B")
	FVector2D WorkAreaMin = FVector2D(720.f, 735.f);

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B")
	FVector2D WorkAreaMax = FVector2D(776.f, 800.f);

	/** Distance over which the pad blends back into the natural shoulder. */
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B")
	float WorkAreaBlendM = 12.f;

	/** How much the work area edge and the clearing outline are broken up. */
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B")
	float EdgeNoiseM = 4.f;

	// ---------------------------------------------------------------- house
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|House")
	FVector2D HouseCenter = FVector2D(760.f, 786.f);

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|House")
	float HouseLengthX = 11.6f;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|House")
	float HouseWidthY = 8.6f;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|House")
	float HouseWallHeight = 3.05f;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|House")
	float HouseRoofRise = 2.2f;

	/** Visible foundation height below the floor level of house/garage/shed. */
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|House")
	float FoundationHeight = 0.35f;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|House")
	float EaveOverhang = 0.55f;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|House")
	float GableOverhang = 0.45f;

	// ---------------------------------------------------------------- veranda
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|Veranda")
	float VerandaDepthY = 3.3f;

	/** Open (paved) outdoor living space north of the covered veranda. */
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|Veranda")
	float VerandaApronDepthY = 4.0f;

	// ---------------------------------------------------------------- garage
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|Garage")
	FVector2D GarageCenter = FVector2D(750.f, 746.7f);

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|Garage")
	float GarageWidthX = 8.6f;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|Garage")
	float GarageDepthY = 6.6f;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|Garage")
	float GarageWallHeight = 2.75f;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|Garage")
	float GarageRoofRise = 1.6f;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|Garage")
	float GarageDoorWidth = 3.1f;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|Garage")
	float GarageDoorHeight = 2.45f;

	// ---------------------------------------------------------------- shed
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|Shed")
	FVector2D ShedCenter = FVector2D(729.f, 744.f);

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|Shed")
	float ShedWidthX = 6.4f;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|Shed")
	float ShedDepthY = 4.0f;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|Shed")
	float ShedWallHeightLow = 2.15f;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|Shed")
	float ShedWallHeightHigh = 2.8f;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|Shed")
	float ShedDoorWidth = 2.6f;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|Shed")
	float ShedDoorHeight = 2.05f;

	// ---------------------------------------------------------------- yard
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|Yard")
	FVector2D YardMin = FVector2D(733.f, 750.f);

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|Yard")
	FVector2D YardMax = FVector2D(771.f, 782.f);

	/** Height of the concrete surface above the terrain pad. */
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|Yard")
	float YardTopOffsetM = 0.06f;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|Yard")
	float YardThicknessM = 0.26f;

	/** Concrete panels across the yard (each panel poured separately => joint lines). */
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|Yard")
	int32 YardPanelsX = 6;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|Yard")
	int32 YardPanelsY = 5;

	// ---------------------------------------------------------------- driveway
	/** Driveway centre line (world meters). Empty -> the default Phase 4B route. */
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|Driveway")
	TArray<FVector2D> DrivewayPoints;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|Driveway")
	float DrivewayHalfWidthM = 3.1f;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|Driveway")
	float DrivewayFalloffM = 9.f;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|Driveway")
	float DrivewayMaxGrade = 0.075f;

	// ---------------------------------------------------------------- forest
	/** Distance from the property centre inside which there is never a tree. */
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|Forest")
	float ForestInnerM = 24.f;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|Forest")
	float ForestDenseM = 135.f;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|Forest")
	float ForestMidM = 255.f;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|Forest")
	float ForestOuterM = 430.f;

	/** The tree line follows the hill: no trees below this ground height. */
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|Forest")
	float ForestMinHeightM = 92.f;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|Forest")
	float TreeSpacingDenseM = 6.6f;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|Forest")
	float TreeSpacingMidM = 8.2f;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|Forest")
	float TreeSpacingOuterM = 10.5f;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|Forest")
	int32 MaxTrees = 3200;

	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|Forest")
	int32 RandomSeed = 20260923;

	/** World-Partition friendly cell size used to group the instanced trees. */
	UPROPERTY(BlueprintReadWrite, EditAnywhere, Category = "Phase4B|Forest")
	float TreeCellSizeM = 260.f;
};

/** Report of one Phase 4B build step (values are for verification/reporting). */
USTRUCT(BlueprintType)
struct FPhase4BPropertyResult
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	bool bSuccess = false;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	FString Message;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	FVector2D PropertyCenter = FVector2D::ZeroVector;

	/** Terrain pad height the property sits on (meters). */
	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	float PadHeightM = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	int32 EditedComponentCount = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	int32 RemovedActors = 0;

	/** Flatness inside the construction area (should be ~0) and of the natural slope outside it. */
	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	float WorkAreaSpreadM = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	float NaturalSlopeSpreadM = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	float NaturalSlopeMaxPercent = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	float DrivewayLengthM = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	float DrivewayStartHeightM = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	float DrivewayEndHeightM = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	float DrivewayMaxGrade = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	TArray<FVector> DrivewayPointsCm;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	TArray<FString> CreatedAssets;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	TArray<FString> CreatedActors;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	TArray<FString> Warnings;

	/** Forest statistics. */
	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	int32 TreeInstanceCount = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	TMap<FString, int32> TreeInstancesPerVariant;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	float TreeNearestToPropertyM = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	int32 TreesInsideOpenArea = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	TMap<FString, float> ElevationSamplesM;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	TMap<FString, float> ReadbackSamplesM;
};

/**
 * Phase 4B property builder. Editor only: in a cooked runtime build the functions
 * report that they are unavailable.
 */
UCLASS()
class MYPROJECT_API UPhase4BPropertyBuilder : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	/**
	 * Refines the terrain around the Phase 4A home pad: the construction area stays
	 * level, the rest of the pad melts into a natural shoulder (no artificial
	 * plateau) and the driveway is graded out of the property towards the Phase 4A
	 * road. Only the property region is edited; the world outside stays untouched.
	 */
	UFUNCTION(BlueprintCallable, Category = "MyProject|Phase4B")
	static FPhase4BPropertyResult RefineHomeTerrain(UObject* WorldContextObject, const FPhase4BHomeSpec& Spec);

	/**
	 * Generates the property blockout meshes (house, veranda, garage, shed, concrete
	 * yard, walkway, driveway, grill, pine variants) into
	 * /Game/Game/Environment/Home. Existing assets with the same name are replaced.
	 */
	UFUNCTION(BlueprintCallable, Category = "MyProject|Phase4B")
	static FPhase4BPropertyResult BuildPropertyAssets(UObject* WorldContextObject, const FPhase4BHomeSpec& Spec);

	/**
	 * Fills the hillside around the property with instanced pine trees: dense right
	 * outside the property, thinning with distance and stopping at the tree line the
	 * hill defines. Replaces the trees of a previous Phase 4B run.
	 */
	UFUNCTION(BlueprintCallable, Category = "MyProject|Phase4B")
	static FPhase4BPropertyResult PlacePineForest(UObject* WorldContextObject, const FPhase4BHomeSpec& Spec);

	/** Removes the Phase 4B actors (P4B_*) so a build can be repeated. */
	UFUNCTION(BlueprintCallable, Category = "MyProject|Phase4B")
	static int32 ClearPropertyActors(UObject* WorldContextObject);

	/** Terrain height (meters) at a world position (meters) measured through collision. */
	UFUNCTION(BlueprintCallable, Category = "MyProject|Phase4B")
	static float GroundHeightM(UObject* WorldContextObject, float XM, float YM, bool& bHit);
};
