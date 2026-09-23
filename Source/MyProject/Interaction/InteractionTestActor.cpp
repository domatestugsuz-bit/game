// Copyright Epic Games, Inc. All Rights Reserved.

#include "InteractionTestActor.h"

#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "UObject/ConstructorHelpers.h"

AInteractionTestActor::AInteractionTestActor()
	: InteractionText(FText::FromString(TEXT("A\u00e7")))
	, ActivatedInteractionText(FText::FromString(TEXT("Kapat")))
	, InactiveColor(0.75f, 0.35f, 0.10f)
	, ActiveColor(0.15f, 0.60f, 0.25f)
	, bActivated(false)
	, InteractionCount(0)
	, DynamicMaterial(nullptr)
{
	PrimaryActorTick.bCanEverTick = false;

	MeshComponent = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Mesh"));
	SetRootComponent(MeshComponent);
	MeshComponent->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
	MeshComponent->SetCollisionResponseToAllChannels(ECR_Block);
	MeshComponent->SetGenerateOverlapEvents(false);
	MeshComponent->SetCastShadow(true);

	// Engine content keeps the prototype free of imported art (Phase 3A is a slice,
	// not a final asset pass).
	static ConstructorHelpers::FObjectFinder<UStaticMesh> CubeMesh(TEXT("/Engine/BasicShapes/Cube.Cube"));
	if (CubeMesh.Succeeded())
	{
		MeshComponent->SetStaticMesh(CubeMesh.Object);
	}

	static ConstructorHelpers::FObjectFinder<UMaterialInterface> BaseMaterial(TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
	if (BaseMaterial.Succeeded())
	{
		MeshComponent->SetMaterial(0, BaseMaterial.Object);
	}
}

void AInteractionTestActor::BeginPlay()
{
	Super::BeginPlay();

	if (MeshComponent)
	{
		DynamicMaterial = MeshComponent->CreateAndSetMaterialInstanceDynamic(0);
	}
	ApplyVisualState();
}

bool AInteractionTestActor::CanInteract_Implementation(AActor* Interactor)
{
	return true;
}

FText AInteractionTestActor::GetInteractionText_Implementation(AActor* Interactor)
{
	return bActivated ? ActivatedInteractionText : InteractionText;
}

void AInteractionTestActor::Interact_Implementation(AActor* Interactor)
{
	++InteractionCount;
	SetActivated(!bActivated);

	UE_LOG(LogTemp, Display,
		TEXT("[Interaction] %s -> %s (count=%d, activated=%s)"),
		*GetNameSafe(Interactor), *GetName(), InteractionCount,
		bActivated ? TEXT("true") : TEXT("false"));
}

void AInteractionTestActor::SetActivated(bool bNewActivated)
{
	if (bActivated == bNewActivated)
	{
		return;
	}

	bActivated = bNewActivated;
	ApplyVisualState();
	BP_OnActivatedChanged(bActivated);
}

void AInteractionTestActor::ApplyVisualState()
{
	if (!MeshComponent)
	{
		return;
	}

	if (!DynamicMaterial)
	{
		DynamicMaterial = MeshComponent->CreateAndSetMaterialInstanceDynamic(0);
	}

	if (DynamicMaterial)
	{
		DynamicMaterial->SetVectorParameterValue(TEXT("Color"), bActivated ? ActiveColor : InactiveColor);
	}
}
