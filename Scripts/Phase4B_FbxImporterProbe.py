# -*- coding: utf-8 -*-
"""Why does the engine report fewer triangles than Blender?

Blender re-imports its own FBX with the full 9820 triangles for Pine_Mature_C (bark 5830 +
needles 3990), while the imported asset reports 3609. This probe compares the two importers the
engine ships - the Interchange pipeline and the legacy FBX factory - on the same file, so the
decision (which importer Phase 4B vegetation uses) is based on measurement, not on taste.
"""

import json
import os

import unreal

FBX = 'C:/Temp/blender_house/veg/fbx/Pine_Mature_C.fbx'
PROBE_DIR = '/Game/Dev/VegetationProbe'
editor_assets = unreal.EditorAssetLibrary
asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
mesh_library = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()


def log(message):
    unreal.log_warning('P4B-VEGPROBE: ' + str(message))


def measure(asset_path):
    mesh = editor_assets.load_asset(asset_path)
    if mesh is None:
        return 'missing'
    slots = mesh.get_editor_property('static_materials')
    return {
        'triangles': mesh.get_num_triangles(0),
        'vertices': mesh.get_num_vertices(0),
        'lod_count': mesh_library.get_lod_count(mesh),
        'slots': len(slots),
        'bounds_cm': [round(float(value), 1) for value in
                      (mesh.get_bounding_box().max.z - mesh.get_bounding_box().min.z,)],
    }


report = {'existing': measure('/Game/Game/Environment/Vegetation/Trees/Pine/SM_Veg_Pine_Mature_C')}
if not editor_assets.does_directory_exist(PROBE_DIR):
    editor_assets.make_directory(PROBE_DIR)

MESH_LIBRARY = mesh_library


def import_to(destination_path, name, dele, nanite):
    """Import the FBX, optionally deleting first, optionally enabling Nanite afterwards."""
    path = destination_path + '/' + name
    if dele and editor_assets.does_asset_exist(path):
        deleted = editor_assets.delete_asset(path)
        report.setdefault('delete_results', {})[name] = str(deleted)
    unreal.SystemLibrary.execute_console_command(world, 'Interchange.FeatureFlags.Import.FBX 1')
    options = unreal.FbxImportUI()
    options.import_materials = False
    options.import_textures = False
    options.import_as_skeletal = False
    options.automated_import_should_detect_type = False
    data = unreal.FbxStaticMeshImportData()
    data.combine_meshes = False
    data.remove_degenerates = False
    try:
        data.auto_compute_normals = True
    except Exception:  # noqa: BLE001
        pass
    options.static_mesh_import_data = data
    task = unreal.AssetImportTask()
    task.filename = FBX
    task.destination_path = destination_path
    task.destination_name = name
    task.automated = True
    task.replace_existing = True
    task.save = True
    task.options = options
    try:
        asset_tools.import_asset_tasks([task])
    except Exception as exc:  # noqa: BLE001
        return {'error': str(exc)[:200]}
    steps = {'after_import': measure(path)}
    if nanite:
        mesh = editor_assets.load_asset(path)
        if mesh is not None:
            settings = mesh_library.get_nanite_settings(mesh)
            settings.enabled = True
            mesh_library.set_nanite_settings(mesh, settings, True)
            steps['after_nanite'] = measure(path)
    return steps


report['reimport_existing_asset'] = import_to(PROBE_DIR, 'SM_Probe_Reimport', True, False)
report['reimport_then_nanite'] = import_to(PROBE_DIR, 'SM_Probe_Nanite', True, True)
report['blender_truth'] = {'triangles': 9820, 'bark': 5830, 'needles': 3990}
log(json.dumps(report, default=str))

for name in ('SM_Probe_Interchange', 'SM_Probe_Legacy'):
    path = PROBE_DIR + '/' + name
    if editor_assets.does_asset_exist(path):
        editor_assets.delete_asset(path)

out_path = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir()),
                        'Phase4B', 'phase4b_fbx_importer_probe.json')
with open(out_path, 'w') as handle:
    json.dump(report, handle, indent=2, default=str)
log('written ' + out_path)
