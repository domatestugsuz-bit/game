// Copyright Epic Games, Inc. All Rights Reserved.
// Phase 3A - data-driven interaction settings.
// Trace distance / radius / prompt format live in a Data Asset so designers can
// tune them per project (or per character) without touching code or graphs.

#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "InteractionConfig.generated.h"

class UInteractionPromptWidget;

UCLASS(BlueprintType)
class MYPROJECT_API UInteractionConfig : public UPrimaryDataAsset
{
	GENERATED_BODY()

public:
	UInteractionConfig();

	/** Maximum distance of the interaction trace, in cm. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Interaction",
		meta = (ClampMin = "50.0", ClampMax = "1000.0", UIMin = "50.0", UIMax = "500.0"))
	float TraceDistance;

	/** Sphere radius used for the interaction trace (0 = plain line trace), in cm. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Interaction",
		meta = (ClampMin = "0.0", ClampMax = "50.0", UIMin = "0.0", UIMax = "30.0"))
	float TraceRadius;

	/** How often (seconds) the trace is refreshed while the player keeps looking. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Interaction",
		meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float TraceInterval;

	/** Prompt format; {0} is replaced with the interactable text. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Interaction")
	FText PromptFormat;

	/** Optional: only actors in these channels block/interact. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Interaction")
	TEnumAsByte<ECollisionChannel> TraceChannel;

	/** Widget class used to show the prompt (BP subclass of UInteractionPromptWidget). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Interaction")
	TSubclassOf<UInteractionPromptWidget> PromptWidgetClass;

	/** Use a sphere trace instead of a line trace (easier to target small objects). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Interaction")
	bool bUseSphereTrace;
};
