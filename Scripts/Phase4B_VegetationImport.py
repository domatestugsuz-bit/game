# -*- coding: utf-8 -*-
"""Phase 4B - import the production pine family and its materials into Unreal 5.8.3.

Source of truth is the Blender run (C:/Temp/blender_house/veg):
  * v1_report.json    - the eight pine variants (height, trunk radius, triangles, UVs, materials)
  * fbx/Pine_*.fbx    - one static mesh per variant, metres, Z up, base at the origin
  * textures/*.png    - bark albedo / normal / roughness and the needle atlas (colour + alpha)

The step is idempotent and only touches /Game/Game/Environment/Vegetation:
  1. creates the vegetation folder structure
  2. imports the four textures with the compression the material graph expects
  3. creates the two master materials (bark: opaque; needles: masked + two sided, because the
     needle cards are single sided geometry that has to be visible from both sides)
  4. imports the eight pines, assigns bark on slot 0 and needles on slot 1
  5. enables Nanite (the family is 4k - 15k triangles per tree and will be instanced by the
     thousand, which is exactly the Nanite case) and writes the trunk capsule collision
  6. verifies every asset by reading it back and writes Saved/Phase4B/phase4b_vegetation_import.json

The level is NOT touched here: placement is a separate, explicit step.
"""

import json
import os

import unreal

SOURCE_DIR = 'C:/Temp/blender_house/veg'
REPORT_IN = os.path.join(SOURCE_DIR, 'v1_report.json')
FBX_DIR = os.path.join(SOURCE_DIR, 'fbx')
TEXTURE_DIR = os.path.join(SOURCE_DIR, 'textures')
SAVED_DIR = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir()),
                         'Phase4B')
ROOT = '/Game/Game/Environment/Vegetation'
TREES_DIR = ROOT + '/Trees/Pine'
TEXTURES_OUT = ROOT + '/Textures'
MATERIALS_OUT = ROOT + '/Materials'
FOLDERS = [ROOT, TREES_DIR, ROOT + '/Trees', ROOT + '/Shrubs', ROOT + '/Grass', ROOT + '/Rocks',
           ROOT + '/ForestFloor', ROOT + '/FallenTrees', TEXTURES_OUT, MATERIALS_OUT]
BARK_MATERIAL = MATERIALS_OUT + '/M_Veg_PineBark'
NEEDLE_MATERIAL = MATERIALS_OUT + '/M_Veg_PineNeedles'
# FBX round trip: Blender metres -> Unreal centimetres, Z up -> Z up (same convention as the house)
CM_PER_M = 100.0
# the capsule follows the trunk; slightly wider than the trunk itself so it cannot be slipped
TRUNK_RADIUS_FACTOR = 1.15

TEXTURES = [
    # file,        asset name,          sRGB, compression,     sampler type
    ('T_PineBark_BC.png', 'T_Veg_PineBark_BC', True, 'TC_DEFAULT', 'SAMPLERTYPE_COLOR'),
    ('T_PineBark_N.png', 'T_Veg_PineBark_N', False, 'TC_NORMALMAP', 'SAMPLERTYPE_NORMAL'),
    ('T_PineBark_R.png', 'T_Veg_PineBark_R', False, 'TC_MASKS', 'SAMPLERTYPE_MASKS'),
    ('T_PineNeedle_BC.png', 'T_Veg_PineNeedle_BC', True, 'TC_BC7', 'SAMPLERTYPE_COLOR'),
]

report = {'steps': [], 'result': 'FAILED', 'failed': [], 'warnings': []}
asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
editor_assets = unreal.EditorAssetLibrary
mesh_library = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
material_library = unreal.MaterialEditingLibrary


def log(message):
    unreal.log('P4B-VEG: ' + str(message))
    report['steps'].append(str(message))


def fail(message):
    unreal.log_error('P4B-VEG: ' + str(message))
    report['failed'].append(str(message))


def warn(message):
    unreal.log_warning('P4B-VEG: ' + str(message))
    report['warnings'].append(str(message))


def enum_value(enum_type_name, candidates):
    enum = getattr(unreal, enum_type_name, None)
    if enum is None:
        return None
    for candidate in candidates:
        value = getattr(enum, candidate, None)
        if value is not None:
            return value
    return None


def ensure_folder(path):
    if not editor_assets.does_directory_exist(path):
        editor_assets.make_directory(path)


for folder in FOLDERS:
    ensure_folder(folder)
log('folders ready: {0}'.format(len(FOLDERS)))

with open(REPORT_IN, 'r') as handle:
    blender = json.load(handle)
variants = {entry['name']: entry for entry in blender['variants']}
log('blender report: {0} variants, {1} triangles total'.format(len(variants),
                                                               blender.get('total_triangles')))
report['blender_variants'] = {name: {'height_m': entry['height_m'], 'trunk_radius_m': entry['trunk_radius_m'],
                                     'triangles': entry['triangles'], 'dimensions_m': entry['dimensions_m']}
                              for name, entry in sorted(variants.items())}



# ---------------------------------------------------------------- 2. textures
def import_texture(file_name, asset_name, srgb, compression, sampler):
    source = os.path.join(TEXTURE_DIR, file_name)
    if not os.path.isfile(source):
        fail('texture source missing: ' + source)
        return None
    path = TEXTURES_OUT + '/' + asset_name
    if editor_assets.does_asset_exist(path):
        editor_assets.delete_asset(path)
    task = unreal.AssetImportTask()
    task.filename = source
    task.destination_path = TEXTURES_OUT
    task.destination_name = asset_name
    task.automated = True
    task.replace_existing = True
    task.save = False
    try:
        asset_tools.import_asset_tasks([task])
    except Exception as exc:  # noqa: BLE001
        fail('{0}: import failed: {1}'.format(asset_name, exc))
        return None
    texture = editor_assets.load_asset(path)
    if texture is None:
        fail('{0}: imported texture not loadable'.format(asset_name))
        return None

    settings = {}
    for property_name, value in (('srgb', srgb), ('flip_green_channel', compression == 'TC_NORMALMAP'),
                                 ('compression_no_alpha', False), ('never_stream', False)):
        try:
            texture.set_editor_property(property_name, value)
            settings[property_name] = str(value)
        except Exception as exc:  # noqa: BLE001
            warn('{0}: {1} not set: {2}'.format(asset_name, property_name, str(exc)[:100]))
    compression_value = enum_value('TextureCompressionSettings', (compression,))
    if compression_value is not None:
        try:
            texture.set_editor_property('compression_settings', compression_value)
            settings['compression_settings'] = compression
        except Exception as exc:  # noqa: BLE001
            warn('{0}: compression not set: {1}'.format(asset_name, str(exc)[:100]))
    editor_assets.save_loaded_asset(texture)
    log('{0}: imported ({1}, {2}) srgb now {3}'.format(asset_name, 'sRGB' if srgb else 'linear',
                                                      compression, texture.get_editor_property('srgb')))
    return {'path': path, 'settings': settings, 'sampler_type': sampler}


texture_map = {}
for file_name, asset_name, srgb, compression, sampler in TEXTURES:
    info = import_texture(file_name, asset_name, srgb, compression, sampler)
    if info is not None:
        texture_map[asset_name] = info
report['textures'] = texture_map


# ---------------------------------------------------------------- 3. material graph helpers
def create_material(asset_name):
    path = MATERIALS_OUT + '/' + asset_name
    if editor_assets.does_asset_exist(path):
        material = editor_assets.load_asset(path)
    else:
        material = asset_tools.create_asset(asset_name, MATERIALS_OUT, unreal.Material,
                                           unreal.MaterialFactoryNew())
    if material is None:
        fail('could not create material ' + asset_name)
        return None
    return material


def texture_parameter(material, parameter_name, asset_name, sampler_type, position_y=0):
    expression = material_library.create_material_expression(
        material, unreal.MaterialExpressionTextureSampleParameter2D, -700, position_y)
    expression.set_editor_property('parameter_name', parameter_name)
    texture = editor_assets.load_asset(texture_map[asset_name]['path'])
    if texture is None:
        fail('{0}: texture missing for parameter {1}'.format(material.get_name(), parameter_name))
        return expression
    expression.set_editor_property('texture', texture)
    sampler = enum_value('MaterialSamplerType', (sampler_type,))
    if sampler is not None:
        try:
            expression.set_editor_property('sampler_type', sampler)
        except Exception as exc:  # noqa: BLE001
            warn('{0}: sampler type not set: {1}'.format(parameter_name, str(exc)[:100]))
    return expression


def scalar_parameter(material, parameter_name, value, position_y):
    expression = material_library.create_material_expression(
        material, unreal.MaterialExpressionScalarParameter, -450, position_y)
    expression.set_editor_property('parameter_name', parameter_name)
    expression.set_editor_property('default_value', value)
    return expression


def property_enum(name):
    value = getattr(unreal.MaterialProperty, name, None)
    return value if value is not None else name


def connect(source, source_output, destination=None, destination_input=None, property_name=None):
    try:
        if property_name:
            material_library.connect_material_property(source, source_output, property_enum(property_name))
        else:
            material_library.connect_material_expressions(source, source_output, destination,
                                                          destination_input)
        return True
    except Exception as exc:  # noqa: BLE001
        fail('connection failed ({0} -> {1}): {2}'.format(source_output, property_name or destination_input,
                                                         str(exc)[:140]))
        return False


def multiply(material, texture, texture_output, scalar, position_y=0):
    """texture channel * scalar -> one value, the pattern the project's masters use."""
    node = material_library.create_material_expression(material, unreal.MaterialExpressionMultiply,
                                                       -200, position_y)
    material_library.connect_material_expressions(texture, texture_output, node, 'A')
    material_library.connect_material_expressions(scalar, '', node, 'B')
    return node


# ---------------------------------------------------------------- 4. bark master material
bark = create_material('M_Veg_PineBark')
report['materials'] = {'created': [], 'ok': {}}
if bark is not None:
    material_library.delete_all_material_expressions(bark)
    bark_base = texture_parameter(bark, 'BaseColorTexture', 'T_Veg_PineBark_BC', 'SAMPLERTYPE_COLOR', 0)
    bark_rough = texture_parameter(bark, 'RoughnessTexture', 'T_Veg_PineBark_R', 'SAMPLERTYPE_MASKS', 300)
    bark_normal = texture_parameter(bark, 'NormalTexture', 'T_Veg_PineBark_N', 'SAMPLERTYPE_NORMAL', 600)
    bark_roughness = scalar_parameter(bark, 'RoughnessScale', 1.0, 900)
    bark_rough_mix = multiply(bark, bark_rough, 'R', bark_roughness, 900)
    connect(bark_base, 'RGB', property_name='MP_BASE_COLOR')
    connect(bark_rough_mix, '', property_name='MP_ROUGHNESS')
    connect(bark_normal, 'RGB', property_name='MP_NORMAL')
    try:
        bark.set_editor_property('blend_mode', enum_value('BlendMode', ('BLEND_OPAQUE',)))
        bark.set_editor_property('two_sided', False)
        bark.set_editor_property('shading_model',
                                 enum_value('MaterialShadingModel', ('MSM_DEFAULT_LIT',)))
    except Exception as exc:  # noqa: BLE001
        warn('bark material settings: ' + str(exc)[:140])
    material_library.recompile_material(bark)
    editor_assets.save_loaded_asset(bark)
    report['materials']['created'].append(BARK_MATERIAL)
    log('bark material ready: {0}'.format(BARK_MATERIAL))

# ---------------------------------------------------------------- 5. needles master material
needles = create_material('M_Veg_PineNeedles')
if needles is not None:
    material_library.delete_all_material_expressions(needles)
    needle_base = texture_parameter(needles, 'BaseColorTexture', 'T_Veg_PineNeedle_BC', 'SAMPLERTYPE_COLOR', 0)
    needle_roughness = scalar_parameter(needles, 'RoughnessScale', 0.62, 300)
    connect(needle_base, 'RGB', property_name='MP_BASE_COLOR')
    connect(needle_base, 'A', property_name='MP_OPACITY_MASK')
    connect(needle_roughness, '', property_name='MP_ROUGHNESS')
    try:
        needles.set_editor_property('blend_mode', enum_value('BlendMode', ('BLEND_MASKED',)))
        # the needle cards are single sided planes: without two sided shading half the crown
        # would be invisible from one side, which is exactly what billboard foliage must not do
        needles.set_editor_property('two_sided', True)
        needles.set_editor_property('shading_model',
                                    enum_value('MaterialShadingModel', ('MSM_DEFAULT_LIT',)))
        needles.set_editor_property('opacity_mask_clip_value', 0.33)
    except Exception as exc:  # noqa: BLE001
        warn('needle material settings: ' + str(exc)[:140])
    material_library.recompile_material(needles)
    editor_assets.save_loaded_asset(needles)
    report['materials']['created'].append(NEEDLE_MATERIAL)
    log('needle material ready: {0}'.format(NEEDLE_MATERIAL))

for name, material in (('bark', bark), ('needles', needles)):
    if material is None:
        continue
    report['materials']['ok'][name] = {
        'path': MATERIALS_OUT + '/' + material.get_name(),
        'blend_mode': str(material.get_editor_property('blend_mode')),
        'two_sided': str(material.get_editor_property('two_sided')),
        'opacity_mask_clip': material.get_editor_property('opacity_mask_clip_value'),
        'texture_parameters': sorted(material_library.get_texture_parameter_names(material)),
        'scalar_parameters': sorted(material_library.get_scalar_parameter_names(material)),
        'expressions': material_library.get_num_material_expressions(material),
    }


# ---------------------------------------------------------------- 6. FBX import
COLLISION_NONE = enum_value('FbxCollisionType', ('FBCT_NONE', 'FBCT_USE_NONE', 'NONE'))
STATIC_MESH_ENUM = enum_value('FBXImportType', ('FBXIT_STATIC_MESH', 'STATIC_MESH'))
log('fbx enums: collision none={0} static mesh={1}'.format(COLLISION_NONE, STATIC_MESH_ENUM))

imported = {}
for variant in sorted(variants.keys()):
    fbx = os.path.join(FBX_DIR, variant + '.fbx')
    asset_name = 'SM_Veg_' + variant
    if not os.path.isfile(fbx):
        fail('{0}: FBX missing ({1})'.format(variant, fbx))
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
    # Degenerate removal must stay OFF: measured on this exact FBX it deleted 63 % of the
    # triangles (the thin needle sprays and card edges are flagged as degenerate), which would
    # have imported a bare trunk skeleton instead of a pine. Verified by re-importing the same
    # file with the flag off: 9820 triangles, exactly Blender's count.
    data.remove_degenerates = False
    try:
        data.auto_compute_normals = True
    except Exception:  # noqa: BLE001
        pass
    if COLLISION_NONE is not None:
        try:
            # the trees get their own trunk capsule below; any collision the importer would
            # invent (hulls, or a box round the crown) has to be avoided
            data.collision_type = COLLISION_NONE
        except Exception as exc:  # noqa: BLE001
            warn('{0}: could not clear collision type: {1}'.format(variant, str(exc)[:120]))
    options.static_mesh_import_data = data

    task = unreal.AssetImportTask()
    task.filename = fbx
    task.destination_path = TREES_DIR
    task.destination_name = asset_name
    task.automated = True
    task.replace_existing = True
    task.save = False
    task.options = options
    # Reimporting over an existing static mesh made the engine reuse the previous translated
    # payload (measured: the 3609 triangle version kept coming back), so the asset is removed
    # first and always imported from scratch. Deleting is what made the probe reproduce
    # Blender's exact 9820 triangles.
    existing = TREES_DIR + '/' + asset_name
    if editor_assets.does_asset_exist(existing):
        editor_assets.delete_asset(existing)
    try:
        asset_tools.import_asset_tasks([task])
    except Exception as exc:  # noqa: BLE001
        fail('{0}: import_asset_tasks failed: {1}'.format(variant, exc))
        continue
    paths = [str(path) for path in task.get_editor_property('imported_object_paths')]
    if not paths:
        fail('{0}: import produced no assets'.format(variant))
        continue
    imported[variant] = {'asset_path': TREES_DIR + '/' + asset_name, 'files': paths,
                         'blender': report['blender_variants'][variant]}
    log('{0}: imported -> {1}'.format(variant, imported[variant]['asset_path']))
report['imported'] = imported


# ---------------------------------------------------------------- 7. post processing
helper_class = getattr(unreal, 'Phase4BVegetationBuilder', None)
if helper_class is None:
    fail('Phase4BVegetationBuilder is not exposed to Python - the C++ module needs a rebuild')
report['helper'] = helper_class is not None

summary = {'meshes': 0, 'material_slots_ok': 0, 'nanite_enabled': 0, 'capsule_written': 0,
           'heights_ok': 0, 'triangles_ok': 0, 'problems': []}
for variant in sorted(imported.keys()):
    info = imported[variant]
    mesh = editor_assets.load_asset(info['asset_path'])
    if mesh is None:
        fail('{0}: imported asset not loadable'.format(info['asset_path']))
        continue
    summary['meshes'] += 1

    # Material slots: the FBX carries bark on slot 0 and needles on slot 1 (Blender's order).
    for index, material_path in ((0, BARK_MATERIAL), (1, NEEDLE_MATERIAL)):
        material = editor_assets.load_asset(material_path)
        if material is None:
            fail('{0}: material missing {1}'.format(variant, material_path))
            continue
        try:
            mesh.set_material(index, material)
        except Exception as exc:  # noqa: BLE001
            fail('{0}: slot {1} not assignable: {2}'.format(variant, index, str(exc)[:120]))

    # The source triangles are read BEFORE Nanite is switched on: enabling Nanite generates a
    # fallback mesh and rewrites LOD0's render data with it (measured: 9820 -> 3609 triangles),
    # so the import check has to look at the source data or it would be checking the fallback.
    source_triangles = mesh.get_num_triangles(0)
    source_vertices = mesh.get_num_vertices(0)

    settings = mesh_library.get_nanite_settings(mesh)
    settings.enabled = True
    try:
        # thin needle cards are exactly what a fallback simplification likes to erase
        settings.preserve_area = True
    except Exception:  # noqa: BLE001
        pass
    mesh_library.set_nanite_settings(mesh, settings, True)
    fallback_triangles = mesh.get_num_triangles(0)

    height_cm = float(info['blender']['dimensions_m'][2]) * CM_PER_M
    radius_cm = float(info['blender']['trunk_radius_m']) * CM_PER_M * TRUNK_RADIUS_FACTOR
    collision = None
    if report['helper']:
        collision = helper_class.add_trunk_capsule_collision(mesh, height_cm, radius_cm, False)

    box = mesh.get_bounding_box()
    size_m = [round(float(box.max.x - box.min.x) / CM_PER_M, 2),
              round(float(box.max.y - box.min.y) / CM_PER_M, 2),
              round(float(box.max.z - box.min.z) / CM_PER_M, 2)]
    slots = mesh.get_editor_property('static_materials')
    facts = {
        'source_triangles': source_triangles,
        'source_vertices': source_vertices,
        'fallback_triangles_after_nanite': fallback_triangles,
        'material_slots': [str(slot.get_editor_property('material_interface')) for slot in slots],
        'slot_count': len(slots),
        'nanite': str(mesh_library.get_nanite_settings(mesh).enabled),
        'simple_collision_shapes': mesh_library.get_simple_collision_count(mesh),
        'bounds_m': size_m,
        'blender_height_m': info['blender']['height_m'],
        'capsule': None,
    }
    if collision is not None:
        facts['capsule'] = {
            'success': bool(collision.get_editor_property('bSuccess')),
            'radius_cm': collision.get_editor_property('capsuleRadiusCm'),
            'length_cm': collision.get_editor_property('capsuleLengthCm'),
            'shapes_before': collision.get_editor_property('shapesBefore'),
            'shapes_after': collision.get_editor_property('shapesAfter'),
            'trace_flag': collision.get_editor_property('traceFlag'),
            'message': collision.get_editor_property('message'),
        }
        if facts['capsule']['success']:
            summary['capsule_written'] += 1
    if facts['slot_count'] >= 2 and all(MATERIALS_OUT in str(slot) for slot in facts['material_slots']):
        summary['material_slots_ok'] += 1
    if facts['nanite'] == 'True':
        summary['nanite_enabled'] += 1
    if abs(size_m[2] - float(info['blender']['height_m'])) <= max(0.8, 0.06 * float(info['blender']['height_m'])):
        summary['heights_ok'] += 1
    else:
        summary['problems'].append('{0}: imported height {1} m vs Blender {2} m'.format(
            variant, size_m[2], info['blender']['height_m']))
    if abs(source_triangles - int(info['blender']['triangles'])) <= int(info['blender']['triangles']) * 0.02:
        summary['triangles_ok'] += 1
    else:
        summary['problems'].append('{0}: imported {1} triangles vs Blender {2}'.format(
            variant, source_triangles, info['blender']['triangles']))
    info['facts'] = facts
    editor_assets.save_loaded_asset(mesh)
    log('{0}: source {1} triangles ({2} after the nanite fallback), slots {3}, nanite {4}, '
        'shapes {5}, size {6} m'.format(variant, source_triangles, fallback_triangles,
                                        facts['slot_count'], facts['nanite'],
                                        facts['simple_collision_shapes'], size_m))
report['summary'] = summary


# ---------------------------------------------------------------- 8. verification / report
expected_mesh_count = len(variants)
textures_ok = len(texture_map) == len(TEXTURES)
needles_ok = report['materials']['ok'].get('needles', {})
bark_ok = report['materials']['ok'].get('bark', {})
imported_count = len(imported)
checks = {
    'all_textures_imported': textures_ok,
    'needle_atlas_keeps_alpha': str(needles_ok.get('blend_mode', '')).find('BLEND_MASKED') >= 0,
    'needle_material_two_sided': str(needles_ok.get('two_sided')) == 'True',
    'bark_material_has_albedo_normal_roughness': all(
        name in (bark_ok.get('texture_parameters') or [])
        for name in ('BaseColorTexture', 'NormalTexture', 'RoughnessTexture')),
    'needle_material_has_atlas': 'BaseColorTexture' in (needles_ok.get('texture_parameters') or []),
    'material_graphs_built': (bark_ok.get('expressions') or 0) > 0 and (needles_ok.get('expressions') or 0) > 0,
    'all_pines_imported': imported_count == expected_mesh_count,
    'cxx_helper_available': bool(report['helper']),
    'material_slots_assigned': summary['material_slots_ok'] == imported_count,
    'nanite_enabled_on_all_pines': summary['nanite_enabled'] == imported_count,
    'trunk_capsules_written': summary['capsule_written'] == imported_count,
    'import_scale_correct': summary['heights_ok'] == imported_count,
    'triangle_counts_match_blender': summary['triangles_ok'] == imported_count,
    'no_failures': len(report['failed']) == 0,
}
report['checks'] = checks
report['ok'] = all(checks.values())
report['result'] = 'OK' if report['ok'] else 'CHECK'
log('checks: {0}'.format(json.dumps(checks)))
log('result: {0}'.format(report['result']))

if not os.path.isdir(SAVED_DIR):
    os.makedirs(SAVED_DIR)
out_path = os.path.join(SAVED_DIR, 'phase4b_vegetation_import.json')
with open(out_path, 'w') as handle:
    json.dump(report, handle, indent=2, default=str)
log('report written: {0}'.format(out_path))

report['summary'] = summary

