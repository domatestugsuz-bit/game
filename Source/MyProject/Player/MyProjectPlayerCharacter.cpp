// Copyright Epic Games, Inc. All Rights Reserved.

#include "MyProjectPlayerCharacter.h"

#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "EnhancedInputComponent.h"
#include "EnhancedInputSubsystems.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/Controller.h"
#include "GameFramework/PlayerController.h"
#include "InputAction.h"
#include "InputActionValue.h"
#include "Interaction/InteractionComponent.h"
#include "Interaction/InteractionConfig.h"
#include "Vehicles/VehicleBase.h"

AMyProjectPlayerCharacter::AMyProjectPlayerCharacter()
	: EyeHeight(64.0f)
	, ControlMode(EPlayerControlMode::OnFoot)
	, bMovementStateSaved(false)
	, SavedMovementMode(MOVE_Walking)
{
	// ---------------- first person movement ----------------
	bUseControllerRotationPitch = false;
	bUseControllerRotationYaw = true;
	bUseControllerRotationRoll = false;

	GetCapsuleComponent()->InitCapsuleSize(34.0f, 88.0f);

	UCharacterMovementComponent* Movement = GetCharacterMovement();
	Movement->bOrientRotationToMovement = false;
	Movement->MaxWalkSpeed = 420.0f;
	Movement->MaxAcceleration = 2048.0f;
	Movement->BrakingDecelerationWalking = 2048.0f;
	Movement->JumpZVelocity = 420.0f;
	Movement->AirControl = 0.25f;

	// ---------------- eye level camera ----------------
	FirstPersonCamera = CreateDefaultSubobject<UCameraComponent>(TEXT("FirstPersonCamera"));
	FirstPersonCamera->SetupAttachment(GetCapsuleComponent());
	FirstPersonCamera->SetRelativeLocation(FVector(0.0f, 0.0f, EyeHeight));
	FirstPersonCamera->bUsePawnControlRotation = true;
	FirstPersonCamera->SetFieldOfView(90.0f);

	// ---------------- invisible body, visible shadow ----------------
	// The game is first person only: the mesh must never be seen by its owner,
	// but it still has to be a physical presence in the world (shadows).
	if (USkeletalMeshComponent* BodyMesh = GetMesh())
	{
		BodyMesh->SetOwnerNoSee(true);
		BodyMesh->SetCastShadow(true);
		BodyMesh->bCastHiddenShadow = true;
		BodyMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		BodyMesh->SetRelativeLocation(FVector(0.0f, 0.0f, -88.0f));
		BodyMesh->SetRelativeRotation(FRotator(0.0f, -90.0f, 0.0f));
	}

	// ---------------- interaction ----------------
	InteractionComponent = CreateDefaultSubobject<UInteractionComponent>(TEXT("InteractionComponent"));
}

void AMyProjectPlayerCharacter::BeginPlay()
{
	Super::BeginPlay();

	if (DefaultMappingContext)
	{
		if (const APlayerController* PlayerController = Cast<APlayerController>(GetController()))
		{
			if (UEnhancedInputLocalPlayerSubsystem* InputSubsystem =
				ULocalPlayer::GetSubsystem<UEnhancedInputLocalPlayerSubsystem>(PlayerController->GetLocalPlayer()))
			{
				InputSubsystem->AddMappingContext(DefaultMappingContext, 0);
			}
		}
	}
}

void AMyProjectPlayerCharacter::SetupPlayerInputComponent(UInputComponent* PlayerInputComponent)
{
	Super::SetupPlayerInputComponent(PlayerInputComponent);

	if (UEnhancedInputComponent* EnhancedInput = Cast<UEnhancedInputComponent>(PlayerInputComponent))
	{
		if (MoveAction)
		{
			EnhancedInput->BindAction(MoveAction, ETriggerEvent::Triggered, this, &AMyProjectPlayerCharacter::OnMove);
		}
		if (LookAction)
		{
			EnhancedInput->BindAction(LookAction, ETriggerEvent::Triggered, this, &AMyProjectPlayerCharacter::OnLook);
		}
		if (JumpAction)
		{
			EnhancedInput->BindAction(JumpAction, ETriggerEvent::Started, this, &AMyProjectPlayerCharacter::OnJumpStarted);
			EnhancedInput->BindAction(JumpAction, ETriggerEvent::Completed, this, &AMyProjectPlayerCharacter::OnJumpStopped);
		}
		if (InteractAction)
		{
			EnhancedInput->BindAction(InteractAction, ETriggerEvent::Started, this, &AMyProjectPlayerCharacter::OnInteractInput);
		}
	}
}

void AMyProjectPlayerCharacter::OnMove(const FInputActionValue& Value)
{
	if (Value.GetValueType() != EInputActionValueType::Axis2D)
	{
		return;
	}

	const FVector2D MovementVector = Value.Get<FVector2D>();

	// While driving, the same WASD input drives the vehicle (X = steer, Y = throttle).
	if (ControlMode == EPlayerControlMode::Driving)
	{
		if (AVehicleBase* Vehicle = CurrentVehicle.Get())
		{
			Vehicle->SetDriveInput(MovementVector.Y, MovementVector.X);
		}
		return;
	}

	if (Controller && !MovementVector.IsNearlyZero())
	{
		const FRotator YawRotation(0.0f, Controller->GetControlRotation().Yaw, 0.0f);
		const FVector ForwardDirection = FRotationMatrix(YawRotation).GetUnitAxis(EAxis::X);
		const FVector RightDirection = FRotationMatrix(YawRotation).GetUnitAxis(EAxis::Y);

		AddMovementInput(ForwardDirection, MovementVector.Y);
		AddMovementInput(RightDirection, MovementVector.X);
	}
}

void AMyProjectPlayerCharacter::OnLook(const FInputActionValue& Value)
{
	if (Value.GetValueType() != EInputActionValueType::Axis2D)
	{
		return;
	}

	const FVector2D LookVector = Value.Get<FVector2D>();
	AddControllerYawInput(LookVector.X);
	AddControllerPitchInput(LookVector.Y);
}

void AMyProjectPlayerCharacter::OnJumpStarted()
{
	// Space doubles as the handbrake while driving.
	if (ControlMode == EPlayerControlMode::Driving)
	{
		if (AVehicleBase* Vehicle = CurrentVehicle.Get())
		{
			Vehicle->SetHandbrake(true);
		}
		return;
	}

	Jump();
}

void AMyProjectPlayerCharacter::OnJumpStopped()
{
	if (ControlMode == EPlayerControlMode::Driving)
	{
		if (AVehicleBase* Vehicle = CurrentVehicle.Get())
		{
			Vehicle->SetHandbrake(false);
		}
		return;
	}

	StopJumping();
}

void AMyProjectPlayerCharacter::OnInteractInput()
{
	Interact();
}

bool AMyProjectPlayerCharacter::Interact()
{
	return InteractionComponent ? InteractionComponent->TryInteract() : false;
}

bool AMyProjectPlayerCharacter::EnterVehicle(AVehicleBase* Vehicle)
{
	if (!Vehicle || ControlMode == EPlayerControlMode::Driving)
	{
		return false;
	}

	USceneComponent* Seat = Vehicle->GetDriverSeat();
	if (!Seat)
	{
		return false;
	}

	// Remember the walking state so it can be restored on exit. A character that has
	// not been initialised yet (or a spectator pawn) can report MOVE_None: treat that
	// as "walking" so leaving a vehicle can never freeze the player in place.
	EMovementMode CurrentMovementMode = MOVE_Walking;
	if (const UCharacterMovementComponent* Movement = GetCharacterMovement())
	{
		const EMovementMode ReportedMode = Movement->MovementMode;
		CurrentMovementMode = (ReportedMode == MOVE_None) ? MOVE_Walking : ReportedMode;
	}
	SavedMovementMode = CurrentMovementMode;
	bMovementStateSaved = true;

	// The driver is a passenger while seated: no walking, no capsule collision.
	if (UCharacterMovementComponent* Movement = GetCharacterMovement())
	{
		Movement->StopMovementImmediately();
		Movement->DisableMovement();
	}
	if (UCapsuleComponent* Capsule = GetCapsuleComponent())
	{
		Capsule->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	}

	// Sit on the seat: the first person camera stays exactly where the seat is.
	AttachToComponent(Seat, FAttachmentTransformRules::SnapToTargetNotIncludingScale);
	SetActorRelativeLocation(FVector(0.0f, 0.0f, -EyeHeight));
	SetActorRelativeRotation(FRotator::ZeroRotator);

	CurrentVehicle = Vehicle;
	ControlMode = EPlayerControlMode::Driving;
	Vehicle->SetOccupant(this);
	Vehicle->StopVehicle();

	// Keep using the same interaction pipeline: it now reports "[E] Araçtan in".
	if (InteractionComponent)
	{
		InteractionComponent->SetForcedInteractable(Vehicle);
	}

	UE_LOG(LogTemp, Display, TEXT("[Vehicle] %s entered %s"), *GetName(), *Vehicle->GetName());
	return true;
}

bool AMyProjectPlayerCharacter::ExitVehicle()
{
	AVehicleBase* Vehicle = CurrentVehicle.Get();
	if (!Vehicle || ControlMode != EPlayerControlMode::Driving)
	{
		return false;
	}

	Vehicle->StopVehicle();
	Vehicle->SetOccupant(nullptr);

	DetachFromActor(FDetachmentTransformRules::KeepWorldTransform);

	// Place the player at the vehicle's exit point so it never ends up inside the car.
	FVector ExitLocation = GetActorLocation() + GetActorForwardVector() * 120.0f;
	if (USceneComponent* Exit = Vehicle->GetExitPoint())
	{
		ExitLocation = Exit->GetComponentLocation();
		SetActorRotation(Exit->GetComponentRotation());
	}
	if (const UCapsuleComponent* Capsule = GetCapsuleComponent())
	{
		ExitLocation.Z += Capsule->GetScaledCapsuleHalfHeight() + 2.0f;
	}
	SetActorLocation(ExitLocation, false, nullptr, ETeleportType::TeleportPhysics);

	// Restore on-foot movement.
	if (UCapsuleComponent* Capsule = GetCapsuleComponent())
	{
		Capsule->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
	}
	if (UCharacterMovementComponent* Movement = GetCharacterMovement())
	{
		const EMovementMode RestoreMode = bMovementStateSaved
			? static_cast<EMovementMode>(SavedMovementMode.GetValue())
			: MOVE_Walking;
		Movement->SetMovementMode(RestoreMode);
	}
	bMovementStateSaved = false;

	CurrentVehicle = nullptr;
	ControlMode = EPlayerControlMode::OnFoot;

	if (InteractionComponent)
	{
		InteractionComponent->SetForcedInteractable(nullptr);
	}

	UE_LOG(LogTemp, Display, TEXT("[Vehicle] %s left %s"), *GetName(), *Vehicle->GetName());
	return true;
}
