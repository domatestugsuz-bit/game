// Copyright Epic Games, Inc. All Rights Reserved.
// Phase 3A - interaction prompt widget base class.
// Hidden by default; only shown while the InteractionComponent reports a focus.

#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "InteractionPromptWidget.generated.h"

class UTextBlock;
class UWidget;

UCLASS(Abstract, BlueprintType, Blueprintable, meta = (DisplayName = "Interaction Prompt Widget"))
class MYPROJECT_API UInteractionPromptWidget : public UUserWidget
{
	GENERATED_BODY()

public:
	/** Makes the prompt visible and shows the given text. */
	UFUNCTION(BlueprintCallable, Category = "Interaction|UI")
	void ShowPrompt(const FText& InPromptText);

	/** Hides the prompt (collapsed, so it never blocks input or takes layout space). */
	UFUNCTION(BlueprintCallable, Category = "Interaction|UI")
	void HidePrompt();

	/** True while the prompt is being displayed. */
	UFUNCTION(BlueprintPure, Category = "Interaction|UI")
	bool IsPromptVisible() const;

	/** Updates the text without changing visibility. */
	UFUNCTION(BlueprintCallable, Category = "Interaction|UI")
	void SetPromptText(const FText& InPromptText);

protected:
	virtual void NativeConstruct() override;

	/** Auto-bound when the widget blueprint contains a TextBlock called "PromptText". */
	UPROPERTY(BlueprintReadOnly, Category = "Interaction|UI", meta = (BindWidgetOptional))
	TObjectPtr<UTextBlock> PromptText;

	/** Optional container that is toggled instead of the whole widget. */
	UPROPERTY(BlueprintReadOnly, Category = "Interaction|UI", meta = (BindWidgetOptional))
	TObjectPtr<UWidget> PromptRoot;

	/** Blueprint hook so BP subclasses can drive animations/VFX on visibility changes. */
	UFUNCTION(BlueprintImplementableEvent, Category = "Interaction|UI", meta = (DisplayName = "On Prompt Visibility Changed"))
	void BP_OnPromptVisibilityChanged(bool bNewVisible);

	/** Blueprint hook for custom text formatting. */
	UFUNCTION(BlueprintImplementableEvent, Category = "Interaction|UI", meta = (DisplayName = "On Prompt Text Changed"))
	void BP_OnPromptTextChanged(const FText& InPromptText);

	/** Blueprint hook so subclasses can define their own "hidden" presentation. */
	UFUNCTION(BlueprintNativeEvent, Category = "Interaction|UI", meta = (DisplayName = "Apply Prompt Visibility"))
	void ApplyPromptVisibility(bool bNewVisible);
	virtual void ApplyPromptVisibility_Implementation(bool bNewVisible);

private:
	/**
	 * Builds a default TextBlock at runtime when the widget blueprint does not
	 * provide one. Keeps the prompt functional without any manual UMG editing.
	 */
	void EnsurePromptTextBlock();
};
