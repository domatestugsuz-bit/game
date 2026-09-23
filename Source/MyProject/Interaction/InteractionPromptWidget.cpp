// Copyright Epic Games, Inc. All Rights Reserved.

#include "InteractionPromptWidget.h"

#include "Blueprint/WidgetTree.h"
#include "Components/CanvasPanel.h"
#include "Components/PanelWidget.h"
#include "Components/TextBlock.h"
#include "Components/Widget.h"

void UInteractionPromptWidget::NativeConstruct()
{
	Super::NativeConstruct();

	EnsurePromptTextBlock();
	ApplyPromptVisibility(false);
}

void UInteractionPromptWidget::EnsurePromptTextBlock()
{
	// A designer-provided "PromptText" TextBlock always wins (BindWidgetOptional).
	if (PromptText || !WidgetTree)
	{
		return;
	}

	UWidgetTree* Tree = WidgetTree;
	UPanelWidget* Panel = Cast<UPanelWidget>(Tree->RootWidget);
	if (!Panel)
	{
		UCanvasPanel* NewRoot = NewObject<UCanvasPanel>(Tree, UCanvasPanel::StaticClass(), TEXT("PromptCanvas"));
		if (!NewRoot)
		{
			return;
		}
		Tree->RootWidget = NewRoot;
		Panel = NewRoot;
	}

	UTextBlock* CreatedText = NewObject<UTextBlock>(Tree, UTextBlock::StaticClass(), TEXT("PromptText"));
	if (!CreatedText)
	{
		return;
	}

	FSlateFontInfo FontInfo = CreatedText->GetFont();
	FontInfo.Size = 22;
	CreatedText->SetFont(FontInfo);
	CreatedText->SetColorAndOpacity(FSlateColor(FLinearColor::White));
	CreatedText->SetShadowOffset(FVector2D(1.0f, 1.0f));
	CreatedText->SetShadowColorAndOpacity(FLinearColor(0.0f, 0.0f, 0.0f, 0.85f));

	Panel->AddChild(CreatedText);
	PromptText = CreatedText;
}

void UInteractionPromptWidget::ShowPrompt(const FText& InPromptText)
{
	SetPromptText(InPromptText);
	ApplyPromptVisibility(true);
	BP_OnPromptVisibilityChanged(true);
}

void UInteractionPromptWidget::HidePrompt()
{
	ApplyPromptVisibility(false);
	BP_OnPromptVisibilityChanged(false);
}

bool UInteractionPromptWidget::IsPromptVisible() const
{
	const ESlateVisibility CurrentVisibility = GetVisibility();
	if (PromptRoot)
	{
		const ESlateVisibility RootVisibility = PromptRoot->GetVisibility();
		return RootVisibility != ESlateVisibility::Collapsed && RootVisibility != ESlateVisibility::Hidden;
	}
	return CurrentVisibility != ESlateVisibility::Collapsed && CurrentVisibility != ESlateVisibility::Hidden;
}

void UInteractionPromptWidget::SetPromptText(const FText& InPromptText)
{
	if (PromptText)
	{
		PromptText->SetText(InPromptText);
	}

	BP_OnPromptTextChanged(InPromptText);
}

void UInteractionPromptWidget::ApplyPromptVisibility_Implementation(bool bNewVisible)
{
	const ESlateVisibility NewVisibility = bNewVisible
		? ESlateVisibility::HitTestInvisible
		: ESlateVisibility::Collapsed;

	if (PromptRoot)
	{
		PromptRoot->SetVisibility(NewVisibility);
	}
	else
	{
		SetVisibility(NewVisibility);
	}
}
