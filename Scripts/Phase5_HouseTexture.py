# -*- coding: utf-8 -*-
"""Phase 5 - give the production house real PBR materials (texture pass, Unreal side).

The house arrived in Phase 4 with 81 flat colour material instances (no textures at all), which is
why it read as a plastic blockout. The Blender side (p5_texture_pass.py) has since mapped every
material onto a CC0 ambientCG texture set, rebuilt the UVs in real metres and repaired the geometry
defects; p5_export.py exported that state to FBX. This script closes the loop in Unreal:

  1. imports the texture sets (colour / normal / roughness) into House/Textures/<Pack>
  2. builds the master material M_House_PBR with BaseColor / Normal / Roughness texture parameters
  3. reparents every M_House_* material instance to it and feeds it the matching texture set,
     tint, roughness scale and metallic value (p5_materials.json is the truth table)
  4. leaves glass, fabric and foliage instances on the old flat master, where a texture would be
     a downgrade, and leaves the level, actors and meshes untouched (instance paths are stable)

Run (after Phase4_House_Import.py has re-imported the new FBX):
  Run-Phase4Script.ps1 -Script "...\\Scripts\\Phase5_HouseTexture.py" -Log <log>
"""

import json
import os
from datetime import datetime

import unreal

TEX_DIR = 'C:/Temp/blender_house/tex_pack'
MAP_PATH = 'C:/Temp/blender_house/p5/p5_materials.json'
ROOT = '/Game/Game/Environment/House'
TEXTURE_ROOT = ROOT + '/Textures'
MATERIAL_ROOT = ROOT + '/Materials'
MASTER_NAME = 'M_House_PBR'
MASTER_PATH = MATERIAL_ROOT + '/' + MASTER_NAME
OUT_DIR = 'C:/Users/azize/OneDrive/Belgeler/Unreal Projects/MyProject/Saved/Phase5'
OUT = OUT_DIR + '/phase5_house_texture.json'
METALLIC_PACKS = ('Metal063', 'Metal032')

report = {'phase': 'Phase 5 - house texture pass', 'timestamp': datetime.now().isoformat(
    timespec='seconds'), 'textures': [], 'master': {}, 'instances': [], 'skipped': [],
    'warnings': [], 'errors': [], 'result': 'FAILED'}


def log(message):
    print('P5TEX: ' + str(message))


def warn(message):
    report['warnings'].append(str(message))
    log('WARNING ' + str(message))


def fail(message):
    report['errors'].append(str(message))
    log('ERROR ' + str(message))


editor_assets = unreal.EditorAssetLibrary
asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
material_library = unreal.MaterialEditingLibrary
existing_names = {}   # lower-case leaf -> exact leaf, filled by collect_existing()

TEXTURE_SUFFIX = {'color': '_1K-JPG_Color.jpg', 'normal': '_1K-JPG_NormalGL.jpg',
                  'roughness': '_1K-JPG_Roughness.jpg'}


def source_file(pack, kind):
    path = os.path.join(TEX_DIR, pack, pack + TEXTURE_SUFFIX[kind])
    return path if os.path.isfile(path) else None


def import_texture(pack, kind):
    """Import one map of one pack and configure its compression for its role."""
    asset_name = 'T_H_{0}_{1}'.format(pack, kind.upper())
    asset_path = TEXTURE_ROOT + '/' + pack + '/' + asset_name
    existing = editor_assets.load_asset(asset_path)
    source = source_file(pack, kind)
    if source is None:
        return None
    if existing is not None:
        texture = existing
        report['textures'].append({'asset': asset_path, 'reused': True})
    else:
        task = unreal.AssetImportTask()
        task.filename = source
        task.destination_path = TEXTURE_ROOT + '/' + pack
        task.destination_name = asset_name
        task.automated = True
        task.replace_existing = True
        task.save = True
        asset_tools.import_asset_tasks([task])
        texture = editor_assets.load_asset(asset_path)
        if texture is None:
            fail('texture import failed: ' + asset_path)
            return None
        report['textures'].append({'asset': asset_path, 'reused': False})

    settings = {'srgb': kind == 'color'}
    if kind == 'normal':
        settings['compression_settings'] = unreal.TextureCompressionSettings.TC_NORMALMAP
        settings['flip_green_channel'] = True   # Blender exports OpenGL normals, Unreal wants DX
    elif kind == 'roughness':
        settings['compression_settings'] = unreal.TextureCompressionSettings.TC_GRAYSCALE
    for key, value in settings.items():
        try:
            texture.set_editor_property(key, value)
        except Exception as exc:  # noqa: BLE001
            warn('{0}: {1} failed: {2}'.format(asset_path, key, exc))
    try:
        editor_assets.save_loaded_asset(texture)
    except Exception as exc:  # noqa: BLE001
        warn('{0}: save failed: {1}'.format(asset_path, exc))
    return asset_path


def ensure_master():
    """Master material: colour/normal/roughness texture parameters, tint, roughness scale and a
    metallic scalar. Rebuilt in place on every run so the graph is deterministic."""
    material = editor_assets.load_asset(MASTER_PATH)
    created = False
    if material is None:
        material = asset_tools.create_asset(MASTER_NAME, MATERIAL_ROOT, unreal.Material,
                                            unreal.MaterialFactoryNew())
        created = True
    if material is None:
        fail('could not create master material ' + MASTER_PATH)
        return None
    material_library.delete_all_material_expressions(material)
    try:
        material.set_editor_property('blend_mode', unreal.BlendMode.BLEND_OPAQUE)
        material.set_editor_property('two_sided', False)
    except Exception as exc:  # noqa: BLE001
        warn('master material settings failed: {0}'.format(exc))

    uv = material_library.create_material_expression(
        material, unreal.MaterialExpressionTextureCoordinate, -900, 0)
    uv.set_editor_property('coordinate_index', 0)

    color = material_library.create_material_expression(
        material, unreal.MaterialExpressionTextureSampleParameter2D, -550, 300)
    color.set_editor_property('parameter_name', 'BaseColorTexture')
    color.set_editor_property('sampler_type', unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)

    tint = material_library.create_material_expression(
        material, unreal.MaterialExpressionVectorParameter, -550, 620)
    tint.set_editor_property('parameter_name', 'BaseColorTint')
    tint.set_editor_property('default_value', unreal.LinearColor(1.0, 1.0, 1.0, 1.0))

    tinted = material_library.create_material_expression(
        material, unreal.MaterialExpressionMultiply, -250, 420)

    normal = material_library.create_material_expression(
        material, unreal.MaterialExpressionTextureSampleParameter2D, -550, 60)
    normal.set_editor_property('parameter_name', 'NormalTexture')
    normal.set_editor_property('sampler_type', unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)

    roughness = material_library.create_material_expression(
        material, unreal.MaterialExpressionTextureSampleParameter2D, -550, -220)
    roughness.set_editor_property('parameter_name', 'RoughnessTexture')
    roughness.set_editor_property('sampler_type', unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_GRAYSCALE)

    # A parameter with no default texture falls back to the engine's default *colour* texture,
    # which does not match the normal / grayscale sampler type and makes the whole master fail
    # to compile for PCD3D_SM6 (Unreal then uses the default material for the master itself).
    # Giving every parameter a matching default texture keeps the master compilable.
    for expression, kind in ((color, 'COLOR'), (normal, 'NORMAL'), (roughness, 'ROUGHNESS')):
        default_texture = editor_assets.load_asset('{0}/Concrete013/T_H_Concrete013_{1}'.format(TEXTURE_ROOT, kind))
        if default_texture is None:
            warn('default texture missing for {0}'.format(kind))
            continue
        try:
            expression.set_editor_property('texture', default_texture)
        except Exception as exc:  # noqa: BLE001
            warn('could not set the default texture for {0}: {1}'.format(kind, exc))

    roughness_scale = material_library.create_material_expression(
        material, unreal.MaterialExpressionScalarParameter, -550, -470)
    roughness_scale.set_editor_property('parameter_name', 'RoughnessScale')
    roughness_scale.set_editor_property('default_value', 1.0)

    roughness_mul = material_library.create_material_expression(
        material, unreal.MaterialExpressionMultiply, -250, -300)

    metallic = material_library.create_material_expression(
        material, unreal.MaterialExpressionScalarParameter, -250, -560)
    metallic.set_editor_property('parameter_name', 'MetallicValue')
    metallic.set_editor_property('default_value', 0.0)

    connections = (
        (uv, 'UV', color, 'UVs'),
        (uv, 'UV', normal, 'UVs'),
        (uv, 'UV', roughness, 'UVs'),
        (color, 'RGB', tinted, 'A'),
        (tint, '', tinted, 'B'),
        (roughness, 'R', roughness_mul, 'A'),
        (roughness_scale, '', roughness_mul, 'B'),
    )
    for source_expression, source_output, target_expression, target_input in connections:
        try:
            material_library.connect_material_expressions(source_expression, source_output,
                                                          target_expression, target_input)
        except Exception as exc:  # noqa: BLE001
            fail('connect {0} -> {1} failed: {2}'.format(source_output, target_input, exc))

    for expression, output, prop in ((tinted, '', unreal.MaterialProperty.MP_BASE_COLOR),
                                     (normal, 'RGB', unreal.MaterialProperty.MP_NORMAL),
                                     (roughness_mul, '', unreal.MaterialProperty.MP_ROUGHNESS),
                                     (metallic, '', unreal.MaterialProperty.MP_METALLIC)):
        try:
            material_library.connect_material_property(expression, output, prop)
        except Exception as exc:  # noqa: BLE001
            fail('connect property {0} failed: {1}'.format(prop, exc))

    material_library.recompile_material(material)
    try:
        editor_assets.save_loaded_asset(material)
    except Exception as exc:  # noqa: BLE001
        warn('master save failed: {0}'.format(exc))
    parameters = {}
    for getter, key in ((material_library.get_texture_parameter_names, 'textures'),
                        (material_library.get_scalar_parameter_names, 'scalars'),
                        (material_library.get_vector_parameter_names, 'vectors')):
        try:
            parameters[key] = sorted(str(name) for name in getter(material))
        except Exception as exc:  # noqa: BLE001
            parameters[key] = 'n/a: ' + str(exc)[:80]
    report['master'] = {'path': MASTER_PATH, 'created': created, 'parameters': parameters}
    log('master material {0}: {1}'.format(MASTER_PATH, parameters))
    return material


# ---------------------------------------------------------------- instances
def collect_existing():
    """Cache the exact leaf names of the material folder: UE resolves asset paths case
    insensitively on Windows, so 'MI_H_m_metal' and 'MI_H_M_Metal' cannot coexist."""
    for asset_path in editor_assets.list_assets(MATERIAL_ROOT, recursive=False,
                                                include_folder=False):
        leaf = str(asset_path).rsplit('/', 1)[-1].split('.')[0]
        existing_names[leaf.lower()] = leaf


def ensure_instance(blender_material, master):
    """One material instance per Blender material, parented to the textured master. The name keeps
    the Phase 4 convention (MI_H_<BlenderMaterial>) unless that name is already claimed by a
    material that only differs in letter case."""
    desired = 'MI_H_' + blender_material
    claimed = existing_names.get(desired.lower())
    if claimed is not None and claimed != desired:
        desired = desired + '_V2'
        warn('{0}: name taken by {1}, using {2}'.format(blender_material, claimed, desired))
    asset_path = MATERIAL_ROOT + '/' + desired
    instance = editor_assets.load_asset(asset_path)
    reused = instance is not None
    if instance is None:
        instance = asset_tools.create_asset(desired, MATERIAL_ROOT,
                                            unreal.MaterialInstanceConstant,
                                            unreal.MaterialInstanceConstantFactoryNew())
    if instance is None:
        fail('could not create material instance ' + asset_path)
        return None, None
    try:
        instance.set_editor_property('parent', master)
    except Exception as exc:  # noqa: BLE001
        fail('{0}: parent set failed: {1}'.format(asset_path, exc))
        return None, None
    existing_names[desired.lower()] = desired
    return instance, {'path': asset_path, 'reused': reused, 'asset_name': desired}


def apply_instance(instance, entry):
    """Feed the texture set, tint, roughness scale and metallic value of one Blender material."""
    textures = {}
    for kind, parameter in (('color', 'BaseColorTexture'), ('normal', 'NormalTexture'),
                            ('roughness', 'RoughnessTexture')):
        asset_path = import_texture(entry['pack'], kind)
        if asset_path is None:
            continue
        texture = editor_assets.load_asset(asset_path)
        if texture is None:
            continue
        textures[parameter] = asset_path
        try:
            material_library.set_material_instance_texture_parameter_value(instance, parameter,
                                                                           texture)
        except Exception as exc:  # noqa: BLE001
            fail('texture parameter {0} failed: {1}'.format(parameter, exc))
    tint = entry.get('tint') or [1.0, 1.0, 1.0]
    try:
        material_library.set_material_instance_vector_parameter_value(
            instance, 'BaseColorTint', unreal.LinearColor(tint[0], tint[1], tint[2], 1.0))
    except Exception as exc:  # noqa: BLE001
        fail('BaseColorTint failed: {1}'.format(exc))
    scale = entry.get('roughness_scale')
    metallic = 0.85 if str(entry.get('pack', '')).startswith('Metal') else 0.0
    for parameter, value in (('RoughnessScale', float(scale) if scale else 1.0),
                             ('MetallicValue', metallic)):
        try:
            material_library.set_material_instance_scalar_parameter_value(instance, parameter, value)
        except Exception as exc:  # noqa: BLE001
            fail('{0} failed: {1}'.format(parameter, exc))
    return textures


def assign_slots(instance_map, material_map):
    """Assign the resolved instances per slot: the slot NAME stored in the mesh decides which
    material belongs there, because the import does not keep Blender's slot order."""
    plan_path = 'C:/Temp/blender_house/export/export_plan.json'
    if not os.path.isfile(plan_path):
        warn('export plan missing, slots not reassigned: ' + plan_path)
        return
    with open(plan_path) as handle:
        plan = json.load(handle)
    folders = {
        'House_Architecture': 'Architecture', 'House_Roof': 'Architecture',
        'House_Windows': 'Architecture', 'House_Interior': 'Interior',
        'House_Lighting': 'Interior', 'House_Kitchen': 'Kitchen',
        'House_Bathroom': 'Bathroom', 'House_Bedrooms': 'Bedroom',
        'House_LivingRoom': 'Furniture', 'House_Props': 'Props',
        'House_Veranda': 'Exterior', 'House_Garden': 'Exterior', 'House_Yard': 'Exterior',
        'House_Shed': 'Exterior', 'House_Interactables': 'Interactables',
    }
    assigned = 0
    missing = 0
    for batch_name, batch in sorted(plan.get('batches', {}).items()):
        folder = folders.get(batch_name)
        if folder is None:
            continue
        folder_path = ROOT + '/' + folder
        by_name = {}
        for asset_path in editor_assets.list_assets(folder_path, recursive=False,
                                                    include_folder=False):
            # list_assets returns '/Game/.../House_Architecture.House_Architecture'
            leaf = str(asset_path).rsplit('/', 1)[-1].split('.')[0]
            by_name[leaf] = str(asset_path)
        for record in batch.get('slot_materials', []):
            object_name = record.get('object')
            asset_path = by_name.get(object_name)
            if asset_path is None:
                continue
            mesh = editor_assets.load_asset(asset_path)
            if mesh is None:
                continue
            changed = False
            # Neither the FBX nor the Interchange import keeps Blender's slot order, so the material
            # is resolved from the slot NAME that Phase 4 wrote into the mesh, never from the index
            # that Blender used.
            for index, slot in enumerate(mesh.get_editor_property('static_materials') or []):
                try:
                    slot_name = str(slot.get_editor_property('material_slot_name'))
                except Exception as exc:  # noqa: BLE001
                    warn('{0} slot {1}: name unreadable: {2}'.format(asset_path, index, exc))
                    continue
                target = instance_map.get(slot_name) or material_map.get(slot_name)
                if target is None:
                    fallback = ROOT + '/Materials/MI_H_' + slot_name
                    if not editor_assets.does_asset_exist(fallback):
                        missing += 1
                        continue
                    target = fallback
                material = editor_assets.load_asset(target)
                if material is None:
                    missing += 1
                    continue
                try:
                    mesh.set_material(index, material)
                    assigned += 1
                    changed = True
                except Exception as exc:  # noqa: BLE001
                    warn('{0} slot {1} ({2}): {3}'.format(asset_path, index, slot_name, exc))
            if changed:
                try:
                    editor_assets.save_loaded_asset(mesh)
                except Exception as exc:  # noqa: BLE001
                    warn('{0}: save failed: {1}'.format(asset_path, exc))
    report['slots'] = {'assigned': assigned, 'missing': missing}
    log('slots reassigned: {0} ok, {1} without a textured instance'.format(assigned, missing))


def main():
    if not os.path.isfile(MAP_PATH):
        fail('material map missing: ' + MAP_PATH)
        return
    with open(MAP_PATH) as handle:
        material_map = json.load(handle)
    entries = material_map.get('materials', [])
    log('material map: {0} textured materials from {1}'.format(len(entries), MAP_PATH))
    master = ensure_master()
    if master is None:
        return
    collect_existing()

    instance_map = {}
    for entry in sorted(entries, key=lambda item: item['material']):
        blender_material = entry['material']
        instance, facts = ensure_instance(blender_material, master)
        if instance is None:
            continue
        textures = apply_instance(instance, entry)
        try:
            editor_assets.save_loaded_asset(instance)
        except Exception as exc:  # noqa: BLE001
            warn('{0}: save failed: {1}'.format(facts['path'], exc))
        instance_map[blender_material] = facts['path']
        record = dict(facts)
        record.update({'material': blender_material, 'pack': entry['pack'],
                       'tile_m': entry['tile_m'], 'tint': entry.get('tint'),
                       'roughness_scale': entry.get('roughness_scale'), 'textures': textures})
        report['instances'].append(record)
    report['instance_map'] = instance_map
    log('material instances textured: {0}'.format(len(instance_map)))

    assign_slots(instance_map, material_map)

    report['kept_flat'] = list(material_map.get('materials_kept', []))
    report['result'] = 'PASSED' if not report['errors'] else 'FAILED'
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT, 'w') as handle:
        json.dump(report, handle, indent=2)
    log('result {0}, evidence {1}'.format(report['result'], OUT))


main()


