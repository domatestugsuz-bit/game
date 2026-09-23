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
			"MyProject/Player",
			"MyProject/World"
		});

		PublicDependencyModuleNames.AddRange(new string[]
		{
			"Core",
			"CoreUObject",
			"Engine",
			"InputCore",
			"EnhancedInput",   // interaction input action (IA_Interact)
			"UMG",             // interaction prompt widget
			"Landscape",       // Phase 4A large-world terrain blockout builder
			"Foliage"          // needed by LandscapeEdit.h (landscape bulk edit interface)
		});

		PrivateDependencyModuleNames.AddRange(new string[]
		{
			"Slate",
			"SlateCore"
		});

		if (Target.bBuildEditor)
		{
			// Phase 4B builds the home property blockout at editor time: the procedural
			// property meshes are created from mesh descriptions, saved as static mesh
			// assets and registered with the asset registry so the editor can use them.
			PrivateDependencyModuleNames.AddRange(new string[]
			{
				"MeshDescription",
				"StaticMeshDescription",
				"AssetRegistry",
				"UnrealEd"
			});
		}
	}
}
