// Copyright Epic Games, Inc. All Rights Reserved.
// Phase 4A - large-world terrain blockout builder.
//
// Editor automation helper (Python-callable) that builds the big rural blockout
// landscape: it removes a previously built/imported landscape and creates a new
// ALandscape with a procedurally generated, designed heightfield plus road route
// splines. Terrain and layout only - no environment art.

#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"

#include "Phase4ATerrainBuilder.generated.h"

class UMaterialInterface;

/** Summary of one BuildRuralTerrain() run (values are for reporting/validation). */
USTRUCT(BlueprintType)
struct FPhase4ATerrainBuildResult
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly, Category = "Phase4A")
	bool bSuccess = false;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4A")
	FString Message;

	/** Landscape actor label that was created. */
	UPROPERTY(BlueprintReadOnly, Category = "Phase4A")
	FString LandscapeLabel;

	/** Heightmap (vertex) resolution. */
	UPROPERTY(BlueprintReadOnly, Category = "Phase4A")
	int32 HeightmapSizeX = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4A")
	int32 HeightmapSizeY = 0;

	/** Component/section configuration that was used. */
	UPROPERTY(BlueprintReadOnly, Category = "Phase4A")
	int32 ComponentCountX = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4A")
	int32 ComponentCountY = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4A")
	int32 SectionsPerComponent = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4A")
	int32 QuadsPerSection = 0;

	/** Quads per axis and the resulting world size in meters (square world). */
	UPROPERTY(BlueprintReadOnly, Category = "Phase4A")
	int32 QuadsPerAxis = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4A")
	float WorldSizeMeters = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4A")
	float QuadSizeMeters = 1.f;

	/** Ground elevation samples in meters (world XY in meters is in the key). */
	UPROPERTY(BlueprintReadOnly, Category = "Phase4A")
	TMap<FString, float> ElevationSamplesM;

	/** Route length of the carved home road in meters. */
	UPROPERTY(BlueprintReadOnly, Category = "Phase4A")
	float HomeRoadLengthM = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4A")
	float HomeRoadStartHeightM = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4A")
	float HomeRoadEndHeightM = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4A")
	float HomeRoadMaxGrade = 0.f;

	/** Actors that were removed before building (landscape family + old routes). */
	UPROPERTY(BlueprintReadOnly, Category = "Phase4A")
	int32 ClearedActorCount = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4A")
	TArray<FString> ClearedActorClasses;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4A")
	TArray<FString> RouteActorLabels;

	/** Landscape grid that was edited (measured from the existing landscape). */
	UPROPERTY(BlueprintReadOnly, Category = "Phase4A")
	int32 ComponentSizeQuads = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4A")
	int32 NumSubsections = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4A")
	int32 SubsectionSizeQuads = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4A")
	int32 ProxyCount = 0;

	/** Vertex rect (landscape space) that was filled. */
	UPROPERTY(BlueprintReadOnly, Category = "Phase4A")
	int32 VertexMinX = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4A")
	int32 VertexMinY = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4A")
	int32 VertexMaxX = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4A")
	int32 VertexMaxY = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4A")
	FVector2D WorldMinM = FVector2D::ZeroVector;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4A")
	FVector2D WorldMaxM = FVector2D::ZeroVector;

	/** Terrain statistics measured on the generated field. */
	UPROPERTY(BlueprintReadOnly, Category = "Phase4A")
	float ClearingFlatnessSpreadM = 0.f;

	/** Height values read back from the landscape after the write (proof the edit landed). */
	UPROPERTY(BlueprintReadOnly, Category = "Phase4A")
	TMap<FString, float> ReadbackSamplesM;

	/** Where the home property actually sits (world meters) and its pad height (meters). */
	UPROPERTY(BlueprintReadOnly, Category = "Phase4A")
	FVector2D HomeCenter = FVector2D::ZeroVector;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4A")
	float HomePadHeightM = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4A")
	float TownFlatnessSpreadM = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4A")
	float MaxRoadRiseStepM = 0.f;
};

/**
 * Phase 4A terrain builder. Editor-only implementation (WITH_EDITOR); in a cooked
 * runtime build the functions simply report that they are unavailable.
 */
UCLASS()
class MYPROJECT_API UPhase4ATerrainBuilder : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	/**
	 * Removes landscape-family actors (ALandscape, ALandscapeStreamingProxy,
	 * ALandscapePlaceholder, ...) and previously created Phase 4A route actors from the
	 * current level so that a build can be repeated. Returns the number of removed actors.
	 */
	UFUNCTION(BlueprintCallable, Category = "MyProject|Phase4A")
	static int32 ClearPreviousTerrain(UObject* WorldContextObject);

	/**
	 * Creates the large rural blockout landscape (default: 4032 m x 4032 m square world,
	 * 1 m quad spacing, 16 x 16 components of 63-quad sections) with the designed
	 * elevation layout and the carved home road corridor, plus route splines.
	 *
	 * @param WorldContextObject any object with a world (editor world from Python).
	 * @param LandscapeMaterial  material to assign to the landscape (blockout material).
	 */
	UFUNCTION(BlueprintCallable, Category = "MyProject|Phase4A")
	static FPhase4ATerrainBuildResult BuildRuralTerrain(UObject* WorldContextObject, UMaterialInterface* LandscapeMaterial);
};
