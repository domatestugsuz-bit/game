// Copyright Epic Games, Inc. All Rights Reserved.
// Phase 3A - interaction detection, focus state and prompt ownership.

#include "InteractionComponent.h"

#include "Blueprint/UserWidget.h"
#include "Camera/CameraComponent.h"
#include "Components/PrimitiveComponent.h"
#include "Engine/World.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "InteractableInterface.h"
#include "InteractionConfig.h"
#include "InteractionPromptWidget.h"

namespace
{
	/** Builds the display text ("[E] Etkilesim") from the configurable format. */
	FText BuildPromptText(const UInteractionConfig* InConfig, const FText& InInteractableText)
	{
		const FString FormatString = InConfig ? InConfig->PromptFormat.ToString() : TEXT("[E] {0}");
		const FTextFormat Format = FTextFormat::FromString(FormatString);

		FFormatOrderedArguments Args;
		Args.Add(InInteractableText);
		return FText::Format(Format, Args);
	}
}

UInteractionComponent::UInteractionComponent()
	: Config(nullptr)
	, TraceSourceOverride(nullptr)
	, PromptWidget(nullptr)
	, CachedTraceSource(nullptr)
	, TraceAccumulator(0.0f)
{
	PrimaryComponentTick.bCanEverTick = true;
	PrimaryComponentTick.TickInterval = 0.0f;
}

void UInteractionComponent::BeginPlay()
{
	Super::BeginPlay();

	EnsurePromptWidget();
	RefreshFocus();
}

void UInteractionComponent::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	if (PromptWidget)
	{
		PromptWidget->RemoveFromParent();
		PromptWidget = nullptr;
	}

	Super::EndPlay(EndPlayReason);
}

void UInteractionComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);

	const UInteractionConfig* EffectiveConfig = GetEffectiveConfig();
	const float Interval = EffectiveConfig ? FMath::Max(EffectiveConfig->TraceInterval, 0.0f) : 0.05f;

	TraceAccumulator += DeltaTime;
	if (TraceAccumulator >= Interval)
	{
		TraceAccumulator = 0.0f;
		RefreshFocus();
	}
}

const UInteractionConfig* UInteractionComponent::GetEffectiveConfig() const
{
	return Config;
}

UCameraComponent* UInteractionComponent::ResolveTraceSource()
{
	if (TraceSourceOverride)
	{
		return TraceSourceOverride;
	}
	if (CachedTraceSource)
	{
		return CachedTraceSource;
	}
	if (const AActor* Owner = GetOwner())
	{
		CachedTraceSource = Owner->FindComponentByClass<UCameraComponent>();
	}
	return CachedTraceSource;
}

bool UInteractionComponent::TraceForInteractable(FHitResult& OutHit)
{
	UWorld* World = GetWorld();
	UCameraComponent* Camera = ResolveTraceSource();
	if (!World || !Camera)
	{
		return false;
	}

	const UInteractionConfig* EffectiveConfig = GetEffectiveConfig();
	const float Distance = EffectiveConfig ? EffectiveConfig->TraceDistance : 250.0f;
	const ECollisionChannel Channel = EffectiveConfig ? EffectiveConfig->TraceChannel.GetValue() : ECC_Visibility;
	const bool bSphereTrace = EffectiveConfig ? EffectiveConfig->bUseSphereTrace : true;
	const float Radius = EffectiveConfig ? EffectiveConfig->TraceRadius : 12.0f;

	const FVector Start = Camera->GetComponentLocation();
	const FVector End = Start + Camera->GetForwardVector() * Distance;

	FCollisionQueryParams Params(SCENE_QUERY_STAT(InteractionTrace), /*bTraceComplex=*/false, GetOwner());

	if (bSphereTrace && Radius > 0.0f)
	{
		return World->SweepSingleByChannel(OutHit, Start, End, FQuat::Identity, Channel,
			FCollisionShape::MakeSphere(Radius), Params);
	}
	return World->LineTraceSingleByChannel(OutHit, Start, End, Channel, Params);
}

void UInteractionComponent::RefreshFocus()
{
	AActor* NewInteractable = nullptr;
	FText NewPromptText = FText::GetEmpty();

	FHitResult Hit;
	if (TraceForInteractable(Hit))
	{
		AActor* HitActor = Hit.GetActor();
		if (!HitActor && Hit.GetComponent())
		{
			HitActor = Hit.GetComponent()->GetOwner();
		}

		if (HitActor && HitActor->GetClass()->ImplementsInterface(UInteractableInterface::StaticClass()))
		{
			AActor* Interactor = GetOwner();
			if (IInteractableInterface::Execute_CanInteract(HitActor, Interactor))
			{
				NewInteractable = HitActor;
				NewPromptText = IInteractableInterface::Execute_GetInteractionText(HitActor, Interactor);
			}
		}
	}

	SetFocus(NewInteractable, NewPromptText);
}

void UInteractionComponent::SetFocus(AActor* NewInteractable, const FText& NewPromptText)
{
	const bool bFocusChanged = (FocusedInteractable.Get() != NewInteractable);

	FocusedInteractable = NewInteractable;
	FocusedPromptText = NewPromptText;

	const FText DisplayText = NewInteractable
		? BuildPromptText(GetEffectiveConfig(), NewPromptText)
		: FText::GetEmpty();

	if (PromptWidget)
	{
		if (NewInteractable)
		{
			PromptWidget->ShowPrompt(DisplayText);
		}
		else
		{
			PromptWidget->HidePrompt();
		}
	}

	if (bFocusChanged)
	{
		OnInteractableFocusChanged.Broadcast(NewInteractable, DisplayText);
	}
}

bool UInteractionComponent::TryInteract()
{
	AActor* Target = FocusedInteractable.Get();
	if (!Target)
	{
		RefreshFocus();
		Target = FocusedInteractable.Get();
	}
	if (!Target || !Target->GetClass()->ImplementsInterface(UInteractableInterface::StaticClass()))
	{
		return false;
	}

	AActor* Interactor = GetOwner();
	if (!IInteractableInterface::Execute_CanInteract(Target, Interactor))
	{
		return false;
	}

	IInteractableInterface::Execute_Interact(Target, Interactor);
	OnInteractionPerformed.Broadcast(Target);

	// Interaction may change the object's state (opened door, picked up item...).
	RefreshFocus();
	return true;
}

AActor* UInteractionComponent::GetFocusedInteractable() const
{
	return FocusedInteractable.Get();
}

bool UInteractionComponent::HasFocusedInteractable() const
{
	return FocusedInteractable.IsValid();
}

void UInteractionComponent::EnsurePromptWidget()
{
	if (PromptWidget)
	{
		return;
	}

	const UInteractionConfig* EffectiveConfig = GetEffectiveConfig();
	if (!EffectiveConfig || !EffectiveConfig->PromptWidgetClass)
	{
		return;
	}

	APawn* OwnerPawn = Cast<APawn>(GetOwner());
	if (!OwnerPawn || !OwnerPawn->IsLocallyControlled())
	{
		return;
	}

	APlayerController* PlayerController = Cast<APlayerController>(OwnerPawn->GetController());
	if (!PlayerController)
	{
		return;
	}

	PromptWidget = CreateWidget<UInteractionPromptWidget>(PlayerController, EffectiveConfig->PromptWidgetClass);
	if (PromptWidget)
	{
		PromptWidget->AddToViewport(0);
		PromptWidget->HidePrompt();
	}
}
