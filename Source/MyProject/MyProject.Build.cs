// Copyright Epic Games, Inc. All Rights Reserved.
// Phase 3A - module rules for the MyProject gameplay module.

using UnrealBuildTool;

public class MyProject : ModuleRules
{
	public MyProject(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

		// Sub-folder headers are referenced with their folder prefix
		// (e.g. #include "Interaction/InteractionComponent.h"); these paths keep the
		// short form working too, which makes the module easier to navigate.
		PublicIncludePaths.AddRange(new string[]
		{
			"MyProject",
			"MyProject/Interaction",
			"MyProject/Player"
		});

		PublicDependencyModuleNames.AddRange(new string[]
		{
			"Core",
			"CoreUObject",
			"Engine",
			"InputCore",
			"EnhancedInput",   // interaction input action (IA_Interact)
			"UMG"              // interaction prompt widget
		});

		PrivateDependencyModuleNames.AddRange(new string[]
		{
			"Slate",
			"SlateCore"
		});
	}
}
