// Copyright Epic Games, Inc. All Rights Reserved.

#include "InteractionConfig.h"
#include "InteractionPromptWidget.h"

UInteractionConfig::UInteractionConfig()
	: TraceDistance(250.0f)
	, TraceRadius(12.0f)
	, TraceInterval(0.05f)
	, PromptFormat(FText::FromString(TEXT("[E] {0}")))
	, TraceChannel(ECC_Visibility)
	, PromptWidgetClass(nullptr)
	, bUseSphereTrace(true)
{
}
