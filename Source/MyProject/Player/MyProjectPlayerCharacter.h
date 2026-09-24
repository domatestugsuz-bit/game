// Copyright Epic Games, Inc. All Rights Reserved.
// Phase 3A - first-person player character.
// CAMERA RULE: this game is first person only. The skeletal mesh is never visible
// to its owner (SetOwnerNoSee + bCastHiddenShadow), so the player has a physical
// presence (shadows) without ever seeing arms, legs or body.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "MyProjectPlayerCharacter.generated.h"

class UCameraComponent;
class UInteractionComponent;
class UInputAction;
class UInputMappingContext;
class AVehicleBase;
struct FInputActionValue;

/** Minimal control state for the vehicle vertical slice. */
UENUM(BlueprintType)
enum class EPlayerControlMode : uint8
{
	OnFoot	UMETA(DisplayName = "On Foot"),
	Driving	UMETA(DisplayName = "Driving")
};


UCLASS(Blueprintable, meta = (DisplayName = "MyProject First Person Character"))
class MYPROJECT_API AMyProjectPlayerCharacter : public ACharacter
{
	GENERATED_BODY()

public:
	AMyProjectPlayerCharacter();

	/** Eye-level first-person camera (the only camera this game will ever have). */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Player|Camera")
	TObjectPtr<UCameraComponent> FirstPersonCamera;

	/** Interaction detection component (trace + prompt). */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Player|Interaction")
	TObjectPtr<UInteractionComponent> InteractionComponent;

	/** Enhanced Input context registered on BeginPlay. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Player|Input")
	TObjectPtr<UInputMappingContext> DefaultMappingContext;

	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Player|Input")
	TObjectPtr<UInputAction> MoveAction;

	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Player|Input")
	TObjectPtr<UInputAction> LookAction;

	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Player|Input")
	TObjectPtr<UInputAction> JumpAction;

	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Player|Input")
	TObjectPtr<UInputAction> InteractAction;

	/** Eye height above the capsule centre, in cm (defaults to the template value). */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Player|Camera")
	float EyeHeight;

	/** Interacts with the focused object (also useful from Blueprint / tests). */
	UFUNCTION(BlueprintCallable, Category = "Player|Interaction")
	bool Interact();

	/** Exposes the interaction component to other systems without casting. */
	UFUNCTION(BlueprintPure, Category = "Player|Interaction")
	UInteractionComponent* GetInteractionComponent() const { return InteractionComponent; }

	// ------------------------------------------------------- vehicle (Phase 3B)
	UFUNCTION(BlueprintPure, Category = "Player|Vehicle")
	EPlayerControlMode GetControlMode() const { return ControlMode; }

	UFUNCTION(BlueprintPure, Category = "Player|Vehicle")
	AVehicleBase* GetCurrentVehicle() const { return CurrentVehicle.Get(); }

	/** Boards the given vehicle (called by the vehicle interaction). */
	UFUNCTION(BlueprintCallable, Category = "Player|Vehicle")
	bool EnterVehicle(AVehicleBase* Vehicle);

	/** Leaves the current vehicle and returns to on-foot movement. */
	UFUNCTION(BlueprintCallable, Category = "Player|Vehicle")
	bool ExitVehicle();

protected:
	virtual void BeginPlay() override;
	virtual void SetupPlayerInputComponent(UInputComponent* PlayerInputComponent) override;

	void OnMove(const FInputActionValue& Value);
	void OnLook(const FInputActionValue& Value);
	void OnJumpStarted();
	void OnJumpStopped();
	void OnInteractInput();

	/** Legacy mouse axis fallback for looking around.
	 *
	 * The Enhanced Input look only works when this class' SetupPlayerInputComponent() actually
	 * runs and the pawn's LookAction is assigned. A Blueprint child can override
	 * SetupPlayerInputComponent(), and then nothing here is bound at all - which is exactly the
	 * "I can walk but I cannot turn" symptom. These axes are bound on the PlayerController's own
	 * input component in BeginPlay, so mouse look survives that case too.
	 */
	void OnTurnAxis(float Value);
	void OnLookUpAxis(float Value);

	/** How many diagnostic look lines are still printed to the log. */
	int32 LookLogBudget;

	/** Current control mode: on foot or driving. */
	UPROPERTY(BlueprintReadOnly, Category = "Player|Vehicle")
	EPlayerControlMode ControlMode;

	/** Vehicle being driven (weak: the vehicle is owned by the level). */
	UPROPERTY(Transient, BlueprintReadOnly, Category = "Player|Vehicle")
	TWeakObjectPtr<AVehicleBase> CurrentVehicle;

	/** Movement state saved while driving, restored on exit. */
	UPROPERTY(Transient)
	bool bMovementStateSaved;
	UPROPERTY(Transient)
	TEnumAsByte<EMovementMode> SavedMovementMode;
};
