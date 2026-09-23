// Copyright Epic Games, Inc. All Rights Reserved.
// Phase 3A - interaction detection component.
// Owns the camera trace, the focus state and the interaction prompt widget.
// It only ever communicates through IInteractableInterface (interface-first).

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "InteractionComponent.generated.h"

class UInteractionConfig;
class UInteractionPromptWidget;
class UCameraComponent;

DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnInteractableFocusChanged, AActor*, Interactable, const FText&, PromptText);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnInteractionPerformed, AActor*, Interactable);

UCLASS(ClassGroup = (MyProject), BlueprintType, meta = (BlueprintSpawnableComponent, DisplayName = "Interaction Component"))
class MYPROJECT_API UInteractionComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UInteractionComponent();

	/** Data-driven tuning (trace distance, radius, prompt format, widget class...). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Interaction")
	TObjectPtr<UInteractionConfig> Config;

	/** Optional explicit trace source; defaults to the owning pawn's active camera. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Interaction")
	TObjectPtr<UCameraComponent> TraceSourceOverride;

	/** Broadcast whenever the focused interactable changes (null = nothing focused). */
	UPROPERTY(BlueprintAssignable, Category = "Interaction")
	FOnInteractableFocusChanged OnInteractableFocusChanged;

	/** Broadcast after a successful interaction. */
	UPROPERTY(BlueprintAssignable, Category = "Interaction")
	FOnInteractionPerformed OnInteractionPerformed;

	/** Performs the interaction on the currently focused object (bound to the interact input). */
	UFUNCTION(BlueprintCallable, Category = "Interaction")
	bool TryInteract();

	UFUNCTION(BlueprintPure, Category = "Interaction")
	AActor* GetFocusedInteractable() const;

	UFUNCTION(BlueprintPure, Category = "Interaction")
	bool HasFocusedInteractable() const;

	UFUNCTION(BlueprintPure, Category = "Interaction")
	FText GetFocusedPromptText() const { return FocusedPromptText; }

	/** Forces an immediate focus refresh (used by tests and by the input handler). */
	UFUNCTION(BlueprintCallable, Category = "Interaction")
	void RefreshFocus();

protected:
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

private:
	void SetFocus(AActor* NewInteractable, const FText& NewPromptText);
	void EnsurePromptWidget();
	UCameraComponent* ResolveTraceSource();
	const UInteractionConfig* GetEffectiveConfig() const;
	bool TraceForInteractable(FHitResult& OutHit);

	/** Currently focused interactable, weak so we never keep destroyed actors alive. */
	UPROPERTY(Transient)
	TWeakObjectPtr<AActor> FocusedInteractable;

	/** Cached prompt text for the current focus. */
	UPROPERTY(Transient)
	FText FocusedPromptText;

	/** Active prompt widget instance (local player only, hidden when nothing is focused). */
	UPROPERTY(Transient)
	TObjectPtr<UInteractionPromptWidget> PromptWidget;

	UPROPERTY(Transient)
	TObjectPtr<UCameraComponent> CachedTraceSource;

	/** Time accumulator for the configurable trace interval. */
	float TraceAccumulator;
};
