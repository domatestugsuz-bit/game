// Copyright Epic Games, Inc. All Rights Reserved.
// Phase 3B - vehicle vertical slice.
// Minimal vehicle actor: transform, graybox visuals, prototype movement,
// driver seat, exit point and the boarding interaction (IInteractableInterface).
// Intentionally NOT final vehicle physics and NOT a fuel/electrical/thermal system.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Interaction/InteractableInterface.h"
#include "VehicleBase.generated.h"

class UStaticMeshComponent;
class USceneComponent;
class AMyProjectPlayerCharacter;

UCLASS(Blueprintable, meta = (DisplayName = "Vehicle Base"))
class MYPROJECT_API AVehicleBase : public AActor, public IInteractableInterface
{
	GENERATED_BODY()

public:
	AVehicleBase();

	// ---------------------------------------------------------------- interface
	virtual bool CanInteract_Implementation(AActor* Interactor) override;
	virtual void Interact_Implementation(AActor* Interactor) override;
	virtual FText GetInteractionText_Implementation(AActor* Interactor) override;

	// ------------------------------------------------------------- occupant API
	UFUNCTION(BlueprintPure, Category = "Vehicle")
	bool IsOccupied() const { return Occupant.IsValid(); }

	UFUNCTION(BlueprintPure, Category = "Vehicle")
	AActor* GetOccupant() const { return Occupant.Get(); }

	/** Set by the player character when it (un)boards. */
	UFUNCTION(BlueprintCallable, Category = "Vehicle")
	void SetOccupant(AActor* NewOccupant) { Occupant = NewOccupant; }

	// --------------------------------------------------------------- anchors
	UFUNCTION(BlueprintPure, Category = "Vehicle")
	USceneComponent* GetDriverSeat() const { return DriverSeat; }

	UFUNCTION(BlueprintPure, Category = "Vehicle")
	USceneComponent* GetExitPoint() const { return ExitPoint; }

	// -------------------------------------------------------------- driving
	/** throttle -1..1 (reverse .. forward), steer -1..1 (left .. right). */
	UFUNCTION(BlueprintCallable, Category = "Vehicle|Driving")
	void SetDriveInput(float InThrottle, float InSteer);

	UFUNCTION(BlueprintCallable, Category = "Vehicle|Driving")
	void SetHandbrake(bool bInHandbrake) { bHandbrake = bInHandbrake; }

	UFUNCTION(BlueprintPure, Category = "Vehicle|Driving")
	float GetCurrentSpeed() const { return CurrentSpeed; }

	UFUNCTION(BlueprintPure, Category = "Vehicle|Driving")
	float GetCurrentSteer() const { return SmoothedSteer; }

	/** Advances the prototype movement; called from Tick and usable by automation. */
	UFUNCTION(BlueprintCallable, Category = "Vehicle|Driving")
	void ApplyDriveStep(float DeltaSeconds);

	/** Stops the vehicle immediately (used when leaving). */
	UFUNCTION(BlueprintCallable, Category = "Vehicle|Driving")
	void StopVehicle();

protected:
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

	/** Graybox body, also the root (collision enabled so it can be looked at). */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Vehicle|Mesh")
	TObjectPtr<UStaticMeshComponent> BodyMesh;

	/** Graybox cabin. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Vehicle|Mesh")
	TObjectPtr<UStaticMeshComponent> CabinMesh;

	/** Driver seat anchor: the first person camera is placed here. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Vehicle|Seat")
	TObjectPtr<USceneComponent> DriverSeat;

	/** Safe spot outside the vehicle where the player is placed on exit. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Vehicle|Seat")
	TObjectPtr<USceneComponent> ExitPoint;

	// -------------------------------------------------- prototype tuning
	/** Forward speed at full throttle (cm/s). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vehicle|Driving", meta = (ClampMin = "50.0"))
	float MaxSpeed;

	/** Reverse speed as a fraction of MaxSpeed. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vehicle|Driving", meta = (ClampMin = "0.1", ClampMax = "1.0"))
	float ReverseSpeedFactor;

	/** How quickly the speed follows the throttle (interp speed). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vehicle|Driving", meta = (ClampMin = "0.1"))
	float SpeedInterpSpeed;

	/** How quickly the vehicle stops when there is no throttle (interp speed). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vehicle|Driving", meta = (ClampMin = "0.1"))
	float CoastInterpSpeed;

	/** Steering interpolation speed (digital keys feel smoother). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vehicle|Driving", meta = (ClampMin = "0.1"))
	float SteerInterpSpeed;

	/** Maximum yaw rate at full steer and full speed (deg/s). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vehicle|Driving", meta = (ClampMin = "1.0"))
	float MaxYawRate;

	/** Handbrake deceleration multiplier. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vehicle|Driving", meta = (ClampMin = "1.0"))
	float HandbrakeFactor;

	/** Sweep the movement so the prototype cannot drive through walls. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vehicle|Driving")
	bool bSweepMovement;

	// ------------------------------------------------------- prompts
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vehicle|Prompt")
	FText BoardPromptText;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vehicle|Prompt")
	FText ExitPromptText;

private:
	UPROPERTY(Transient)
	TWeakObjectPtr<AActor> Occupant;

	/** Cached cast helper (single typed hand-off to our own C++ character base). */
	AMyProjectPlayerCharacter* AsPlayerCharacter(AActor* Actor) const;

	float CurrentSpeed;
	float SmoothedSteer;
	float ThrottleInput;
	float SteerInput;
	bool bHandbrake;
};
