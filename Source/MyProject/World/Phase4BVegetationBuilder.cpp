// Copyright Epic Games, Inc. All Rights Reserved.
#include "World/Phase4BVegetationBuilder.h"

#include "Engine/StaticMesh.h"
#include "PhysicsEngine/AggregateGeom.h"
#include "PhysicsEngine/BodySetup.h"
#include "PhysicsEngine/SphylElem.h"
#include "UObject/Class.h"
#include "UObject/Package.h"

#if WITH_EDITOR
#include "Misc/PackageName.h"
#include "UObject/SavePackage.h"
#endif

namespace Phase4BVegetation
{
	/** Simple shapes of a body setup, counted for the report. */
	static int32 CountSimpleShapes(const UBodySetup* Body)
	{
		if (Body == nullptr)
		{
			return 0;
		}
		const FKAggregateGeom& Geometry = Body->AggGeom;
		return Geometry.SphereElems.Num() + Geometry.BoxElems.Num() + Geometry.SphylElems.Num()
			+ Geometry.ConvexElems.Num();
	}

	/** The trace flag as text: StaticEnum() is not linked for this enum in a game module. */
	static FString DescribeTraceFlag(ECollisionTraceFlag Flag)
	{
		switch (Flag)
		{
		case ECollisionTraceFlag::CTF_UseDefault:          return TEXT("CTF_UseDefault");
		case ECollisionTraceFlag::CTF_UseSimpleAndComplex: return TEXT("CTF_UseSimpleAndComplex");
		case ECollisionTraceFlag::CTF_UseSimpleAsComplex:  return TEXT("CTF_UseSimpleAsComplex");
		case ECollisionTraceFlag::CTF_UseComplexAsSimple:  return TEXT("CTF_UseComplexAsSimple");
		default: return FString::Printf(TEXT("unknown(%d)"), static_cast<int32>(Flag));
		}
	}
}

FPhase4BTrunkCollisionResult UPhase4BVegetationBuilder::AddTrunkCapsuleCollision(UStaticMesh* Mesh,
                                                                                float HeightCm,
                                                                                float RadiusCm,
                                                                                bool bSave)
{
	FPhase4BTrunkCollisionResult Result;
	if (Mesh == nullptr)
	{
		Result.Message = TEXT("no static mesh given");
		return Result;
	}

	Result.Steps.Add(FString::Printf(TEXT("mesh %s: height %.1f cm, trunk radius %.1f cm"),
	                                 *Mesh->GetName(), HeightCm, RadiusCm));

#if WITH_EDITOR
	UBodySetup* Body = Mesh->GetBodySetup();
	if (Body == nullptr)
	{
		Result.Message = TEXT("mesh has no body setup - collision cannot be authored");
		return Result;
	}

	Result.ShapesBefore = Phase4BVegetation::CountSimpleShapes(Body);
	Result.TraceFlag = Phase4BVegetation::DescribeTraceFlag(Body->CollisionTraceFlag);
	Result.Steps.Add(FString::Printf(TEXT("before: %d simple shape(s), trace flag %s"),
	                                 Result.ShapesBefore, *Result.TraceFlag));

	// The imported FBX has no collision art, and anything the importer generated (bounds boxes,
	// hulls over the crown) would be wrong for a tree: start from a clean slate.
	Body->AggGeom.EmptyElements();
	Body->CollisionTraceFlag = ECollisionTraceFlag::CTF_UseSimpleAndComplex;
	Body->bDoubleSidedGeometry = false;

	// A capsule around the trunk: the cylinder part covers the trunk, the caps close it off.
	// The total height is Length + 2 * Radius, so Length has to be reduced by both caps.
	const float Radius = FMath::Clamp(RadiusCm, 2.f, FMath::Max(2.f, HeightCm * 0.5f));
	const float CylinderLength = FMath::Max(1.f, HeightCm - 2.f * Radius);

	FKSphylElem Capsule;
	Capsule.Radius = Radius;
	Capsule.Length = CylinderLength;
	Capsule.SetTransform(FTransform(FVector(0.f, 0.f, HeightCm * 0.5f)));
	Body->AggGeom.SphylElems.Add(Capsule);

	Result.CapsuleRadiusCm = Radius;
	Result.CapsuleLengthCm = CylinderLength;
	Result.CapsuleCentreZCm = HeightCm * 0.5f;

	// Simple collision changed: drop the cooked data and rebuild the runtime meshes so the
	// change is in effect for the very next trace, not only after a restart.
	Body->InvalidatePhysicsData();
	Body->CreatePhysicsMeshes();

	Result.ShapesAfter = Phase4BVegetation::CountSimpleShapes(Body);
	Result.TraceFlag = Phase4BVegetation::DescribeTraceFlag(Body->CollisionTraceFlag);

	// Nanite cannot query complex collision, so a Nanite mesh has to be simple-only. This is a
	// check, not a switch: the capsule above is exactly what makes it valid.
	Result.bNaniteSupportsCapsule = (Result.ShapesAfter == 1);

	Mesh->MarkPackageDirty();

	if (bSave)
	{
		UPackage* Package = Mesh->GetOutermost();
		const FString PackageName = Package->GetName();
		const FString FileName = FPackageName::LongPackageNameToFilename(
			PackageName, FPackageName::GetAssetPackageExtension());
		FSavePackageArgs SaveArgs;
		SaveArgs.TopLevelFlags = RF_Public | RF_Standalone;
		const bool bSaved = UPackage::SavePackage(Package, Mesh, *FileName, SaveArgs);
		Result.Steps.Add(FString::Printf(TEXT("saved %s: %s"), *PackageName,
		                                 bSaved ? TEXT("ok") : TEXT("failed")));
		if (!bSaved)
		{
			Result.Message = TEXT("capsule written but the package could not be saved");
			return Result;
		}
	}

	Result.Steps.Add(FString::Printf(TEXT("after: %d simple shape(s), trace flag %s"),
	                                 Result.ShapesAfter, *Result.TraceFlag));
	Result.bSuccess = (Result.ShapesAfter >= 1);
	Result.Message = Result.bSuccess
		? FString::Printf(TEXT("trunk capsule %.0f cm radius, %.0f cm tall written"), Radius, HeightCm)
		: TEXT("capsule was not written");
	return Result;
#else
	Result.Message = TEXT("editor only helper");
	return Result;
#endif
}
