// Copyright Epic Games, Inc. All Rights Reserved.
// Phase 3A - minimal interactable used to validate the interaction chain.
// Implements IInteractableInterface natively; the BP subclass only provides art.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "InteractableInterface.h"
#include "InteractionTestActor.generated.h"

class UStaticMeshComponent;

UCLASS(Blueprintable, meta = (DisplayName = "Interaction Test Object"))
class MYPROJECT_API AInteractionTestActor : public AActor, public IInteractableInterface
{
	GENERATED_BODY()

public:
	AInteractionTestActor();

	// --- IInteractableInterface -------------------------------------------
	virtual bool CanInteract_Implementation(AActor* Interactor) override;
	virtual void Interact_Implementation(AActor* Interactor) override;
	virtual FText GetInteractionText_Implementation(AActor* Interactor) override;

	/** Toggles the visual/logical state of the test object. */
	UFUNCTION(BlueprintCallable, Category = "Interaction|Test")
	void SetActivated(bool bNewActivated);

	UFUNCTION(BlueprintPure, Category = "Interaction|Test")
	bool IsActivated() const { return bActivated; }

	/** How many times this object has been interacted with (used by tests). */
	UFUNCTION(BlueprintPure, Category = "Interaction|Test")
	int32 GetInteractionCount() const { return InteractionCount; }

protected:
	virtual void BeginPlay() override;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Interaction|Test")
	TObjectPtr<UStaticMeshComponent> MeshComponent;

	/** Prompt text while the object is idle. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Interaction|Test")
	FText InteractionText;

	/** Prompt text after the object has been activated. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Interaction|Test")
	FText ActivatedInteractionText;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Interaction|Test")
	FLinearColor InactiveColor;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Interaction|Test")
	FLinearColor ActiveColor;

	UPROPERTY(BlueprintReadOnly, Category = "Interaction|Test")
	bool bActivated;

	UPROPERTY(BlueprintReadOnly, Category = "Interaction|Test")
	int32 InteractionCount;

	/** Blueprint hook for extra reaction (sound, VFX, animation). */
	UFUNCTION(BlueprintImplementableEvent, Category = "Interaction|Test", meta = (DisplayName = "On Activated Changed"))
	void BP_OnActivatedChanged(bool bNewActivated);

private:
	void ApplyVisualState();

	/** Cached dynamic material used for the activation colour feedback. */
	UPROPERTY(Transient)
	TObjectPtr<class UMaterialInstanceDynamic> DynamicMaterial;
};
