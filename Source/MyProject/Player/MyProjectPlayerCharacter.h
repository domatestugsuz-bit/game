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
struct FInputActionValue;

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

protected:
	virtual void BeginPlay() override;
	virtual void SetupPlayerInputComponent(UInputComponent* PlayerInputComponent) override;

	void OnMove(const FInputActionValue& Value);
	void OnLook(const FInputActionValue& Value);
	void OnJumpStarted();
	void OnJumpStopped();
	void OnInteractInput();
};
