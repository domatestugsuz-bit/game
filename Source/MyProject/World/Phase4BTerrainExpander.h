// Copyright Epic Games, Inc. All Rights Reserved.
// Phase 4B - non-destructive expansion of the World Partition landscape to ~4032 m.
//
// Why this file exists: the editor's landscape "Resize" tool is not available in
// World Partition levels and ALandscapeProxy::Import() only works on a blank landscape
// (it asserts when components already exist). The expansion therefore reuses the exact
// route the editor's own "Add New Landscape Component" tool takes
// (FLandscapeToolStrokeAddComponent):
//   * ULandscapeSubsystem::FindOrAddLandscapeProxy() decides which
//     ALandscapeStreamingProxy owns a component base,
//   * ULandscapeComponent::Init() creates the component,
//   * FLandscapeEditDataInterface::SetHeightData() writes the heightfield.
// Every existing component is left untouched, so the home property, the road and the
// garage keep the exact heights they were built on.

#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"

#include "Phase4BTerrainExpander.generated.h"

/** Result of one Phase 4B terrain expansion pass (reporting / validation). */
USTRUCT(BlueprintType)
struct FPhase4BTerrainExpansionResult
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	bool bSuccess = false;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	FString Message;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	TArray<FString> Steps;

	/** Landscape grid measured before the expansion (landscape vertex space). */
	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	FIntPoint OldVertexMin = FIntPoint::ZeroValue;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	FIntPoint OldVertexMax = FIntPoint::ZeroValue;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	FVector2D OldWorldMinM = FVector2D::ZeroVector;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	FVector2D OldWorldMaxM = FVector2D::ZeroVector;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	int32 OldComponentCount = 0;

	/** Landscape grid after the expansion. */
	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	FIntPoint NewVertexMin = FIntPoint::ZeroValue;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	FIntPoint NewVertexMax = FIntPoint::ZeroValue;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	FVector2D NewWorldMinM = FVector2D::ZeroVector;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	FVector2D NewWorldMaxM = FVector2D::ZeroVector;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	float NewWorldSizeM = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	FIntPoint NewComponentCount = FIntPoint::ZeroValue;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	int32 ComponentsCreated = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	int32 StripsWritten = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	int32 StreamingProxiesAfter = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	int32 ComponentSizeQuads = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	int32 NumSubsections = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	int32 SubsectionSizeQuads = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	float HeightmapZScale = 0.f;

	/** Height samples taken inside the original 2016 m world (before / after, metres). */
	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	TMap<FString, float> PreservedBeforeM;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	TMap<FString, float> PreservedAfterM;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	float MaxPreservedDeltaM = 0.f;

	/** Height samples taken in the newly added area (metres). */
	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	TMap<FString, float> OuterSamplesM;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	TMap<FString, float> OuterReliefM;

	/** Heightmap backup (verbatim uint16 grid of the original world). */
	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	FString HeightmapBackupPath;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	int32 BackupBytes = 0;
};

/**
 * Phase 4B terrain expansion. Editor-only implementation (WITH_EDITOR); the runtime
 * build simply reports that the helper is unavailable.
 */
UCLASS()
class MYPROJECT_API UPhase4BTerrainExpander : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	/**
	 * Reads the heightfield of a vertex rect into a backup file (the raw uint16 grid) plus a
	 * sidecar that records the rect, the component configuration and the heightmap Z scale.
	 * The sidecar is the single source of truth for the block ExpandWorldTo4032() preserves.
	 * Nothing in the level is modified.
	 */
	UFUNCTION(BlueprintCallable, Category = "MyProject|Phase4B")
	static FPhase4BTerrainExpansionResult BackupLandscapeRegion(UObject* WorldContextObject, FIntPoint MinVertex,
	                                                            FIntPoint MaxVertex, const FString& BackupPath);

	/**
	 * Grows the landscape to a ~4032 m x 4032 m world by adding components around the
	 * existing ones (existing components keep their data bit for bit) and writes the new
	 * heightfield: the original 2016 m block is copied verbatim, the new area is generated
	 * with the Phase 4B outer relief and blended into the original block.
	 */
	UFUNCTION(BlueprintCallable, Category = "MyProject|Phase4B")
	static FPhase4BTerrainExpansionResult ExpandWorldTo4032(UObject* WorldContextObject, const FString& BackupPath);

	/**
	 * Writes the heights recorded in the backup file straight back over the block they came
	 * from. Used as a repair pass: earlier expansion attempts wrote height data outside the
	 * components they had created, which zeroed the neighbouring rows of the heightfield and
	 * left the world edge sitting at raw 0 (a -255 m drop). The restore is exact: the raw
	 * uint16 grid from the backup is copied back verbatim.
	 */
	UFUNCTION(BlueprintCallable, Category = "MyProject|Phase4B")
	static FPhase4BTerrainExpansionResult RestorePreservedBlock(UObject* WorldContextObject, const FString& BackupPath);
};
