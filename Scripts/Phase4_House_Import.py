# -*- coding: utf-8 -*-
"""Phase 4 - import the Blender production house kit into Unreal Engine 5.8.3.

Reads the artefacts produced by the Blender export step (C:/Temp/blender_house):
  * p4_manifest.json  - Blender object/material truth (81 materials, bounds, counts)
  * export/export_plan.json - export batches, FBX paths, Blender bounds, leaf hinges

It then, idempotently and with full logging:
  1. creates the Content/Game/Environment/House sub folder structure
  2. creates one material instance per Blender material under House/Materials
     (parent: the existing M_RuralSurface master material - no new master material)
  3. imports every batch FBX as static meshes into the matching House sub folder
  4. sets collision (complex-as-simple for walkable joined kits, bounds for leaves and
     windows), assigns the material instances per slot and reports Nanite decisions
  5. writes Saved/Phase4/phase4_import.json

The level is NOT touched by this script (placement is a separate, explicit step):
PLACE_IN_LEVEL stays False until the imported assets have been validated.

Run:
  Run-Phase4Script.ps1 -Script "...\\Scripts\\Phase4_House_Import.py" -Log <log>
"""

import json
import os
from datetime import datetime

import unreal

PLAN_PATH = 'C:/Temp/blender_house/export/export_plan.json'
MANIFEST_PATH = 'C:/Temp/blender_house/p4_manifest.json'
ROOT = '/Game/Game/Environment/House'
MASTER = '/Game/Game/Environment/Home/M_RuralSurface'
BATCH_FOLDERS = {
    'House_Architecture': 'Architecture',
    'House_Roof': 'Architecture',
    'House_Windows': 'Architecture',
    'House_Interior': 'Interior',
    'House_Lighting': 'Interior',
    'House_Kitchen': 'Kitchen',
    'House_Bathroom': 'Bathroom',
    'House_Bedrooms': 'Bedroom',
    'House_LivingRoom': 'Furniture',
    'House_Props': 'Props',
    'House_Veranda': 'Exterior',
    'House_Yard': 'Exterior',
    'House_Shed': 'Exterior',
    'House_Interactables': 'Interactables',
}
SUBFOLDERS = ('Architecture', 'Interior', 'Exterior', 'Furniture', 'Kitchen', 'Bathroom',
              'Bedroom', 'Props', 'Vegetation', 'Materials', 'Textures', 'Meshes',
              'Interactables', 'Blueprints')
# joined kits that have to stay walkable (door openings, rooms) -> complex as simple
COLLISION_MESH = ('House_Architecture', 'House_Roof', 'House_Interior', 'House_Lighting',
                  'House_Kitchen', 'House_Bathroom', 'House_Bedrooms', 'House_LivingRoom',
                  'House_Props', 'House_Veranda', 'House_Yard', 'House_Shed')
# small separate objects (leaves, windows) -> automatic bounds collision
COLLISION_BOUNDS = ('House_Windows', 'House_Interactables')
NANITE_MIN_TRIANGLES = 20000
PLACE_IN_LEVEL = False

report = {
    'phase': 'Phase 4 - production house import',
    'timestamp': datetime.now().isoformat(timespec='seconds'),
    'batches': {},
    'materials': {'created': 0, 'reused': 0, 'missing_master': False},
    'folders': {},
    'errors': [],
    'warnings': [],
    'notes': [],
    'result': 'FAILED',
}


def log(message):
    text = str(message)
    report['notes'].append(text)
    unreal.log('P4IMPORT: ' + text)


def warn(message):
    text = str(message)
    report['warnings'].append(text)
    unreal.log_warning('P4IMPORT: ' + text)


def fail(message):
    text = str(message)
    report['errors'].append(text)
    unreal.log_error('P4IMPORT: ' + text)


def load_json(path):
    with open(path) as handle:
        return json.load(handle)


def to_cm(value):
    return round(float(value) * 100.0, 3)


def vector_to_cm(values):
    return [to_cm(value) for value in values]


# ---------------------------------------------------------------- 1. folders
editor_assets = unreal.EditorAssetLibrary
asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
material_library = unreal.MaterialEditingLibrary

for folder in SUBFOLDERS:
    path = ROOT + '/' + folder
    if not editor_assets.does_directory_exist(path):
        editor_assets.make_directory(path)
        log('created folder ' + path)
    report['folders'][path] = len(editor_assets.list_assets(path, recursive=False, include_folder=False))

# ---------------------------------------------------------------- 2. material instances
manifest = load_json(MANIFEST_PATH)
plan = load_json(PLAN_PATH)
master = editor_assets.load_asset(MASTER)
if master is None:
    report['materials']['missing_master'] = True
    fail('master material missing: {0} (material instances cannot be created)'.format(MASTER))
else:
    log('master material: {0}'.format(MASTER))


def profile_key(base, roughness, metallic):
    return (round(base[0], 3), round(base[1], 3), round(base[2], 3),
            round(roughness, 2), round(metallic, 2))


def ensure_material_instance(asset_name, base, roughness, metallic):
    """One material instance per unique Blender material profile (existing ones reused)."""
    path = ROOT + '/Materials/' + asset_name
    existing = editor_assets.load_asset(path)
    if existing is not None:
        report['materials']['reused'] += 1
        return existing
    if master is None:
        return None
    instance = asset_tools.create_asset(asset_name, ROOT + '/Materials',
                                        unreal.MaterialInstanceConstant,
                                        unreal.MaterialInstanceConstantFactoryNew())
    if instance is None:
        fail('could not create material instance ' + path)
        return None
    try:
        instance.set_editor_property('parent', master)
    except Exception as exc:  # noqa: BLE001
        fail('could not set parent of {0}: {1}'.format(path, exc))
    vector_parameters = (('BaseColor', unreal.LinearColor(base[0], base[1], base[2], 1.0)),
                         ('MottleColor', unreal.LinearColor(base[0] * 0.85, base[1] * 0.85,
                                                            base[2] * 0.85, 1.0)))
    for parameter, value in vector_parameters:
        try:
            material_library.set_material_instance_vector_parameter_value(instance, parameter, value)
        except Exception as exc:  # noqa: BLE001
            warn('{0}: vector parameter {1} failed: {2}'.format(asset_name, parameter, exc))
    scalar_parameters = (('Roughness', roughness), ('Metallic', metallic),
                         ('MottleScale', 0.6), ('MottleStrength', 0.35))
    for parameter, value in scalar_parameters:
        try:
            material_library.set_material_instance_scalar_parameter_value(instance, parameter,
                                                                          float(value))
        except Exception as exc:  # noqa: BLE001
            warn('{0}: scalar parameter {1} failed: {2}'.format(asset_name, parameter, exc))
    editor_assets.save_loaded_asset(instance)
    report['materials']['created'] += 1
    return instance


material_map = {}
profiles = {}
for entry in sorted(manifest.get('materials', []), key=lambda item: item['name']):
    base = entry.get('p_base') or [0.7, 0.7, 0.68, 1.0]
    roughness = entry.get('p_roughness', 0.8)
    metallic = entry.get('p_metallic', 0.0)
    key = profile_key(base, roughness, metallic)
    if key in profiles:
        material_map[entry['name']] = profiles[key]
        continue
    asset_name = 'MI_H_' + entry['name']
    instance = ensure_material_instance(asset_name, base, roughness, metallic)
    if instance is None:
        continue
    path = ROOT + '/Materials/' + asset_name
    profiles[key] = path
    material_map[entry['name']] = path
log('material instances: {0} created, {1} reused, {2} Blender materials mapped'.format(
    report['materials']['created'], report['materials']['reused'], len(material_map)))
report['materials']['map'] = material_map


# ---------------------------------------------------------------- 3. FBX import
def enum_value(enum_type_name, candidates):
    enum = getattr(unreal, enum_type_name, None)
    if enum is None:
        return None
    for candidate in candidates:
        value = getattr(enum, candidate, None)
        if value is not None:
            return value
    return None


COLLISION_MESH_ENUM = enum_value('FbxCollisionType', ('FBCT_USE_MESH', 'USE_MESH'))
COLLISION_BOUNDS_ENUM = enum_value('FbxCollisionType', ('FBCT_USE_BOUNDS', 'USE_BOUNDS'))
STATIC_MESH_ENUM = enum_value('FBXImportType', ('FBXIT_STATIC_MESH', 'STATIC_MESH'))
log('collision enums: mesh={0} bounds={1}'.format(COLLISION_MESH_ENUM, COLLISION_BOUNDS_ENUM))

imported = {}
for batch_name in sorted(BATCH_FOLDERS.keys()):
    entry = plan.get('batches', {}).get(batch_name) or {}
    fbx = entry.get('fbx')
    destination = ROOT + '/' + BATCH_FOLDERS[batch_name]
    if not fbx or not os.path.isfile(fbx):
        fail('{0}: FBX missing ({1})'.format(batch_name, fbx))
        continue
    options = unreal.FbxImportUI()
    options.import_materials = False
    options.import_textures = False
    options.import_as_skeletal = False
    options.automated_import_should_detect_type = False
    if STATIC_MESH_ENUM is not None:
        options.mesh_type_to_import = STATIC_MESH_ENUM
    data = unreal.FbxStaticMeshImportData()
    data.combine_meshes = False
    data.remove_degenerates = True
    try:
        data.auto_compute_normals = True
    except Exception:  # noqa: BLE001
        pass
    collision = COLLISION_BOUNDS_ENUM if batch_name in COLLISION_BOUNDS else COLLISION_MESH_ENUM
    if collision is not None:
        try:
            data.collision_type = collision
        except Exception as exc:  # noqa: BLE001
            warn('{0}: could not set collision_type: {1}'.format(batch_name, exc))
    options.static_mesh_import_data = data

    task = unreal.AssetImportTask()
    task.filename = fbx
    task.destination_path = destination
    task.destination_name = batch_name
    task.automated = True
    task.replace_existing = True
    task.save = True
    task.options = options
    try:
        asset_tools.import_asset_tasks([task])
    except Exception as exc:  # noqa: BLE001
        fail('{0}: import_asset_tasks failed: {1}'.format(batch_name, exc))
        continue
    paths = [str(path) for path in task.get_editor_property('imported_object_paths')]
    if not paths:
        fail('{0}: import produced no assets'.format(batch_name))
        continue
    imported[batch_name] = {'paths': sorted(paths), 'destination': destination,
                            'collision_requested': ('bounds' if batch_name in COLLISION_BOUNDS
                                                    else 'complex_as_simple'),
                            'blender_bounds_min': entry.get('bounds_min'),
                            'blender_bounds_max': entry.get('bounds_max'),
                            'blender_triangles': entry.get('triangles'),
                            'blender_source_objects': entry.get('source_objects')}
    log('{0}: imported {1} asset(s) -> {2}'.format(batch_name, len(paths), destination))
report['imported'] = imported


# ---------------------------------------------------------------- 4. post processing
COMPLEX_FLAG = enum_value('CollisionTraceFlag', ('CTF_USE_COMPLEX_AS_SIMPLE',))
DEFAULT_FLAG = enum_value('CollisionTraceFlag', ('CTF_USE_DEFAULT', 'CTF_USE_SIMPLE_AND_COMPLEX'))
report['editor_collision_api'] = [name for name in dir(unreal.EditorStaticMeshLibrary)
                                  if 'collision' in name.lower()]


def mesh_bounds_cm(mesh):
    box = mesh.get_bounding_box()
    low = [round(box.min.x, 3), round(box.min.y, 3), round(box.min.z, 3)]
    high = [round(box.max.x, 3), round(box.max.y, 3), round(box.max.z, 3)]
    return low, high


summary = {'meshes': 0, 'materials_assigned': 0, 'materials_missing': 0, 'scale_mismatch': 0,
           'collision_ok': 0, 'collision_missing': 0, 'nanite_enabled': 0}
for batch_name in sorted(imported.keys()):
    info = imported[batch_name]
    for path in info['paths']:
        mesh = editor_assets.load_asset(path)
        if mesh is None:
            fail('{0}: imported asset not loadable'.format(path))
            continue
        summary['meshes'] += 1
        facts = {}
        low, high = mesh_bounds_cm(mesh)
        size = [round(high[index] - low[index], 3) for index in range(3)]
        facts['ue_bounds_min_cm'] = low
        facts['ue_bounds_max_cm'] = high
        facts['ue_size_cm'] = size
        blender_low = info.get('blender_bounds_min')
        blender_high = info.get('blender_bounds_max')
        if batch_name in COLLISION_MESH and blender_low and blender_high:
            expect = [to_cm(blender_high[index] - blender_low[index]) for index in range(3)]
            ratio = [round(size[index] / expect[index], 4) if expect[index] > 1.0 else None
                     for index in range(3)]
            facts['blender_size_cm'] = expect
            facts['scale_ratio'] = ratio
            facts['scale_ok'] = all(value is None or abs(value - 1.0) <= 0.02 for value in ratio)
            if not facts['scale_ok']:
                summary['scale_mismatch'] += 1
                fail('{0}: scale mismatch, Blender {1} cm vs Unreal {2} cm'.format(
                    path, expect, size))
        facts['blender_triangles'] = info.get('blender_triangles')

        body = mesh.get_editor_property('body_setup')
        facts['collision_before'] = str(body.get_editor_property('collision_trace_flag')) \
            if body is not None else None
        if body is None:
            summary['collision_missing'] += 1
            warn('{0}: no body setup after import (no collision)'.format(path))
        else:
            target_flag = COMPLEX_FLAG if batch_name in COLLISION_MESH else DEFAULT_FLAG
            if target_flag is not None:
                try:
                    body.set_editor_property('collision_trace_flag', target_flag)
                except Exception as exc:  # noqa: BLE001
                    warn('{0}: collision flag failed: {1}'.format(path, exc))
            facts['collision_after'] = str(body.get_editor_property('collision_trace_flag'))
            if 'CTF_NO_COLLISION' in facts['collision_after']:
                summary['collision_missing'] += 1
                warn('{0}: collision is disabled'.format(path))
            else:
                summary['collision_ok'] += 1

        assigned = []
        missing = []
        slots = mesh.get_editor_property('static_materials') or []
        for index, slot in enumerate(slots):
            slot_name = str(slot.get_editor_property('material_slot_name'))
            target = material_map.get(slot_name)
            if target is None:
                missing.append(slot_name)
                continue
            material = editor_assets.load_asset(target)
            if material is None:
                missing.append(slot_name)
                continue
            try:
                mesh.set_material(index, material)
                assigned.append(slot_name)
            except Exception as exc:  # noqa: BLE001
                warn('{0}: could not set slot {1}: {2}'.format(path, slot_name, exc))
        facts['material_slots'] = len(slots)
        facts['materials_assigned'] = assigned
        facts['materials_missing'] = missing
        summary['materials_assigned'] += len(assigned)
        summary['materials_missing'] += len(missing)
        if missing:
            warn('{0}: {1} slot(s) without a material instance: {2}'.format(
                path, len(missing), ', '.join(sorted(set(missing)))))

        triangles = info.get('blender_triangles') or 0
        if batch_name in COLLISION_MESH:
            facts['nanite'] = ('disabled - the mesh relies on complex-as-simple collision, '
                               'which Nanite cannot query')
        elif triangles >= NANITE_MIN_TRIANGLES:
            settings = mesh.get_editor_property('nanite_settings')
            settings.enabled = True
            try:
                mesh.set_editor_property('nanite_settings', settings)
                facts['nanite'] = 'enabled ({0} triangles)'.format(triangles)
                summary['nanite_enabled'] += 1
            except Exception as exc:  # noqa: BLE001
                facts['nanite'] = 'enable failed: ' + str(exc)[:120]
        else:
            facts['nanite'] = 'disabled - {0} triangles, below the {1} threshold'.format(
                triangles, NANITE_MIN_TRIANGLES)

        editor_assets.save_loaded_asset(mesh)
        report['batches'].setdefault(batch_name, {})[path] = facts
    log('{0}: post processed {1} mesh(es)'.format(batch_name, len(info['paths'])))

report['summary'] = summary
report['result'] = 'FAILED' if report['errors'] else 'OK'

saved_dir = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir())
out_dir = os.path.join(saved_dir, 'Phase4')
os.makedirs(out_dir, exist_ok=True)
out_path = os.path.join(out_dir, 'phase4_import.json')
with open(out_path, 'w') as handle:
    handle.write(json.dumps(report, indent=2, sort_keys=True))
log('report written: {0}'.format(out_path))
log('summary: {0}'.format(json.dumps(summary)))
unreal.log('P4IMPORT: result = {0}'.format(report['result']))




