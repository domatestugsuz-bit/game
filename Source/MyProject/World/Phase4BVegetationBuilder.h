// Copyright Epic Games, Inc. All Rights Reserved.
// Phase 4B - server side helper for the upgraded forest.
//
// Why this file exists: the new pine assets are ONE mesh per tree (trunk + branch hierarchy +
// needle cards in a single static mesh), which is what keeps the forest affordable. That also
// means the automatic bounds collision of the old trunk/canopy split is unusable - a box round
// the whole tree would be a 7 m invisible wall that also blocks the space under the crown.
// The trees therefore get an explicit capsule that hugs the trunk: cheap for the player and the
// vehicle to collide against, and honest about what a player can walk through.

#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"

#include "Phase4BVegetationBuilder.generated.h"

class UStaticMesh;

/** Result of one trunk collision pass (reporting / validation). */
USTRUCT(BlueprintType)
struct FPhase4BTrunkCollisionResult
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	bool bSuccess = false;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	FString Message;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	TArray<FString> Steps;

	/** Simple shapes present before / after the pass. */
	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	int32 ShapesBefore = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	int32 ShapesAfter = 0;

	/** The capsule that was written (cm), including the transform Z of its centre. */
	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	float CapsuleRadiusCm = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	float CapsuleLengthCm = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	float CapsuleCentreZCm = 0.f;

	/** Collision trace flag after the pass, as text (validation reads it back). */
	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	FString TraceFlag;

	UPROPERTY(BlueprintReadOnly, Category = "Phase4B")
	bool bNaniteSupportsCapsule = false;
};

/**
 * Phase 4B vegetation asset helper. Editor-only implementation (WITH_EDITOR); the runtime build
 * simply reports that the helper is unavailable.
 */
UCLASS()
class MYPROJECT_API UPhase4BVegetationBuilder : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	/**
	 * Replaces all simple collision of a static mesh with a single vertical capsule that follows
	 * the trunk: radius at the base, height up to the crown tip. Complex collision is removed at
	 * the same time (Nanite meshes cannot use it). Saves the asset when bSave is true.
	 */
	UFUNCTION(BlueprintCallable, Category = "MyProject|Phase4B")
	static FPhase4BTrunkCollisionResult AddTrunkCapsuleCollision(UStaticMesh* Mesh, float HeightCm,
	                                                            float RadiusCm, bool bSave);
};
