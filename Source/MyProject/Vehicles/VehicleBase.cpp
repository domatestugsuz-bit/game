// Copyright Epic Games, Inc. All Rights Reserved.

#include "VehicleBase.h"

#include "Components/SceneComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Materials/MaterialInterface.h"
#include "Player/MyProjectPlayerCharacter.h"
#include "UObject/ConstructorHelpers.h"

AVehicleBase::AVehicleBase()
	: MaxSpeed(600.0f)
	, ReverseSpeedFactor(0.45f)
	, SpeedInterpSpeed(1.6f)
	, CoastInterpSpeed(1.2f)
	, SteerInterpSpeed(6.0f)
	, MaxYawRate(75.0f)
	, HandbrakeFactor(6.0f)
	, bSweepMovement(true)
	, BoardPromptText(FText::FromString(TEXT("Araca bin")))
	, ExitPromptText(FText::FromString(TEXT("Ara\u00e7tan in")))
	, CurrentSpeed(0.0f)
	, SmoothedSteer(0.0f)
	, ThrottleInput(0.0f)
	, SteerInput(0.0f)
	, bHandbrake(false)
{
	PrimaryActorTick.bCanEverTick = true;

	// Unscaled root so that seat / exit anchors use plain centimetre offsets.
	USceneComponent* Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	SetRootComponent(Root);

	BodyMesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Body"));
	BodyMesh->SetupAttachment(Root);
	BodyMesh->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
	BodyMesh->SetCollisionResponseToAllChannels(ECR_Block);
	BodyMesh->SetCastShadow(true);
	BodyMesh->SetRelativeScale3D(FVector(4.4f, 1.9f, 1.0f));

	CabinMesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Cabin"));
	CabinMesh->SetupAttachment(Root);
	CabinMesh->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
	CabinMesh->SetCollisionResponseToAllChannels(ECR_Block);
	CabinMesh->SetCastShadow(true);
	CabinMesh->SetRelativeLocation(FVector(0.0f, 0.0f, 78.0f));
	CabinMesh->SetRelativeScale3D(FVector(2.2f, 1.7f, 0.72f));

	// Engine placeholder shapes keep the prototype free of imported art.
	static ConstructorHelpers::FObjectFinder<UStaticMesh> CubeMesh(TEXT("/Engine/BasicShapes/Cube.Cube"));
	if (CubeMesh.Succeeded())
	{
		BodyMesh->SetStaticMesh(CubeMesh.Object);
		CabinMesh->SetStaticMesh(CubeMesh.Object);
	}

	static ConstructorHelpers::FObjectFinder<UMaterialInterface> BasicMaterial(
		TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
	if (BasicMaterial.Succeeded())
	{
		BodyMesh->SetMaterial(0, BasicMaterial.Object);
		CabinMesh->SetMaterial(0, BasicMaterial.Object);
	}

	// Driver seat: left hand side of the car (left hand drive), at eye level.
	DriverSeat = CreateDefaultSubobject<USceneComponent>(TEXT("DriverSeat"));
	DriverSeat->SetupAttachment(Root);
	DriverSeat->SetRelativeLocation(FVector(30.0f, -45.0f, 45.0f));

	// Exit point: next to the driver door, at ground level, facing away from the vehicle.
	ExitPoint = CreateDefaultSubobject<USceneComponent>(TEXT("ExitPoint"));
	ExitPoint->SetupAttachment(Root);
	ExitPoint->SetRelativeLocation(FVector(-20.0f, -175.0f, -75.0f));
	ExitPoint->SetRelativeRotation(FRotator(0.0f, -90.0f, 0.0f));
}

void AVehicleBase::BeginPlay()
{
	Super::BeginPlay();

	// Prototype visual: give the graybox body a distinct colour.
	if (BodyMesh)
	{
		if (UMaterialInstanceDynamic* Dynamic = BodyMesh->CreateAndSetMaterialInstanceDynamic(0))
		{
			Dynamic->SetVectorParameterValue(TEXT("Color"), FLinearColor(0.55f, 0.06f, 0.07f));
		}
	}
}

void AVehicleBase::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	// The prototype only moves while somebody is driving it.
	if (Occupant.IsValid())
	{
		ApplyDriveStep(DeltaSeconds);
	}
}

AMyProjectPlayerCharacter* AVehicleBase::AsPlayerCharacter(AActor* Actor) const
{
	// Single, explicit hand-off: the vehicle only ever talks to our own C++
	// character base class (never to a specific Blueprint instance).
	return Cast<AMyProjectPlayerCharacter>(Actor);
}

bool AVehicleBase::CanInteract_Implementation(AActor* Interactor)
{
	// Free seat: anybody may board. Occupied: only the driver may leave.
	return !Occupant.IsValid() || Occupant.Get() == Interactor;
}

FText AVehicleBase::GetInteractionText_Implementation(AActor* Interactor)
{
	if (Occupant.IsValid() && Occupant.Get() == Interactor)
	{
		return ExitPromptText;
	}
	return BoardPromptText;
}

void AVehicleBase::Interact_Implementation(AActor* Interactor)
{
	AMyProjectPlayerCharacter* Player = AsPlayerCharacter(Interactor);
	if (!Player)
	{
		UE_LOG(LogTemp, Warning, TEXT("[Vehicle] %s is not a supported driver"), *GetNameSafe(Interactor));
		return;
	}

	if (Occupant.IsValid() && Occupant.Get() == Interactor)
	{
		Player->ExitVehicle();
	}
	else if (!Occupant.IsValid())
	{
		Player->EnterVehicle(this);
	}
}

void AVehicleBase::SetDriveInput(float InThrottle, float InSteer)
{
	ThrottleInput = FMath::Clamp(InThrottle, -1.0f, 1.0f);
	SteerInput = FMath::Clamp(InSteer, -1.0f, 1.0f);
}

void AVehicleBase::StopVehicle()
{
	CurrentSpeed = 0.0f;
	ThrottleInput = 0.0f;
	SteerInput = 0.0f;
	SmoothedSteer = 0.0f;
	bHandbrake = false;
}

void AVehicleBase::ApplyDriveStep(float DeltaSeconds)
{
	if (DeltaSeconds <= 0.0f)
	{
		return;
	}

	// ---- speed: simple arcade interpolation towards the requested throttle ----
	const float TargetSpeed = (ThrottleInput >= 0.0f)
		? ThrottleInput * MaxSpeed
		: ThrottleInput * MaxSpeed * ReverseSpeedFactor;

	const bool bCoasting = FMath::IsNearlyZero(ThrottleInput, 0.05f) || bHandbrake;
	float InterpSpeed = bCoasting ? CoastInterpSpeed : SpeedInterpSpeed;
	if (bHandbrake)
	{
		InterpSpeed *= HandbrakeFactor;
	}

	CurrentSpeed = FMath::FInterpTo(CurrentSpeed, TargetSpeed, DeltaSeconds, InterpSpeed);

	// ---- steering: the car can only turn while it is moving ------------------
	SmoothedSteer = FMath::FInterpTo(SmoothedSteer, SteerInput, DeltaSeconds, SteerInterpSpeed);

	const float SpeedRatio = FMath::Clamp(FMath::Abs(CurrentSpeed) / FMath::Max(MaxSpeed, 1.0f), 0.0f, 1.0f);
	if (SpeedRatio > KINDA_SMALL_NUMBER && !FMath::IsNearlyZero(SmoothedSteer, 0.01f))
	{
		const float Direction = (CurrentSpeed < 0.0f) ? -1.0f : 1.0f;   // steering flips in reverse
		const float YawDelta = SmoothedSteer * MaxYawRate * SpeedRatio * Direction * DeltaSeconds;
		AddActorWorldRotation(FRotator(0.0f, YawDelta, 0.0f));
	}

	// ---- translation ---------------------------------------------------------
	if (!FMath::IsNearlyZero(CurrentSpeed, 0.1f))
	{
		const FVector Delta = GetActorForwardVector() * CurrentSpeed * DeltaSeconds;
		SetActorLocation(GetActorLocation() + Delta, bSweepMovement);
	}
}
