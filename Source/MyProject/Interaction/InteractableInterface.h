// Copyright Epic Games, Inc. All Rights Reserved.
// Phase 3A - interaction contract (interface-first architecture).
// The Blueprint-facing name of this interface is "Interactable Interface".
// Any actor (C++ or Blueprint) can implement it; the InteractionComponent only
// ever talks to this contract, never to concrete classes.

#pragma once

#include "CoreMinimal.h"
#include "UObject/Interface.h"
#include "InteractableInterface.generated.h"

UINTERFACE(MinimalAPI, BlueprintType, Blueprintable, meta = (DisplayName = "Interactable Interface"))
class UInteractableInterface : public UInterface
{
	GENERATED_BODY()
};

/**
 * Contract implemented by everything the player can look at and interact with.
 * Kept intentionally small; future systems (vehicles, doors, tools, fuel caps,
 * engine parts) will implement this same interface.
 */
class MYPROJECT_API IInteractableInterface
{
	GENERATED_BODY()

public:
	/** Can this object be interacted with right now, by this interactor? */
	UFUNCTION(BlueprintNativeEvent, BlueprintCallable, Category = "Interaction")
	bool CanInteract(AActor* Interactor);
	virtual bool CanInteract_Implementation(AActor* Interactor) { return true; }

	/** Perform the interaction (called when the player presses the interact input). */
	UFUNCTION(BlueprintNativeEvent, BlueprintCallable, Category = "Interaction")
	void Interact(AActor* Interactor);
	virtual void Interact_Implementation(AActor* Interactor) {}

	/** Prompt text shown to the player while this object is focused. */
	UFUNCTION(BlueprintNativeEvent, BlueprintCallable, Category = "Interaction")
	FText GetInteractionText(AActor* Interactor);
	virtual FText GetInteractionText_Implementation(AActor* Interactor) { return FText::GetEmpty(); }
};
