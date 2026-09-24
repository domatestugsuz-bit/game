# -*- coding: utf-8 -*-
"""Phase 6 - ten layer landscape material (textured, slope and height blended).

Replaces the flat colour blockout material of the Phase 4A landscape. Ten layers, each one a
real PBR set (base colour + roughness for every layer, normal maps for the four dominant
ones), blended procedurally:

    kil (clay)  toprak (soil)  cayir (grass)  kuru ot (dry grass)  orman tabani (forest floor)
    igne ortusu (needle litter)  yosun (moss)  cakil (gravel)  kaya (rock)  yol omzu (road shoulder)

* macro/micro variation: the four dominant layers are sampled at a second, 4x finer tiling and
  cross faded, so the ground never reads as one repeating stamp
* slope masking comes from VertexNormalWS, height masking from WorldPosition.Z (metres), and
  the organic pockets from two Noise nodes
* tiling is in real metres per layer (the texture is sampled through WorldPosition / tile_m)

Texture source: the CC0 ambientCG sets already imported for the house (1K) - reused here so the
landscape matches the house material language. Layers without a dedicated pack reuse the
closest set with a tint, which is recorded in the report.

Run in EDITOR mode (headless):
  UnrealEditor-Cmd.exe "<Project>.uproject" -ExecutePythonScript="<this file>"
                       -unattended -nosplash -nullrhi -stdout -NoSourceControl
"""

import json
import os
from datetime import datetime

import unreal

WORLD_DIR = '/Game/Game/Environment/World'
# The material and its instance are rebuilt IN PLACE (same asset identity). Swapping the
# landscape material to a brand new asset leaves the landscape components' saved material
# instances parented to the old one, and a -game (non editor) build then asserts while
# loading: "SetParentEditorOnly() may only be used to initialize (not change) the parent
# outside of the editor" (MaterialInstanceConstant.cpp:81, callstack UnrealEditor-Landscape).
MATERIAL_PATH = WORLD_DIR + '/M_LandscapeBlockout'
INSTANCE_PATH = WORLD_DIR + '/MI_LandscapeBlockout'
SUPERSEDED_PATHS = (WORLD_DIR + '/M_Landscape10Layer', WORLD_DIR + '/MI_Landscape10Layer')
TEX_ROOT = '/Game/Game/Environment/House/Textures'
PACKS = ('Concrete013', 'Concrete046', 'Grass004', 'Gravel043', 'Ground079S', 'Rock051')
REPORT_REL = 'Phase6/'
REPORT_NAME = 'phase6_landscape_material.json'

# name, pack, tile_m, tint, normal (bool), macro (bool)
LAYERS = [
    ('clay', 'Ground079S', 3.0, (0.62, 0.42, 0.30), False, False),
    ('soil', 'Ground079S', 2.4, (0.34, 0.26, 0.19), True, True),
    ('grass', 'Grass004', 2.0, (0.26, 0.34, 0.16), True, True),
    ('dry_grass', 'Grass004', 2.2, (0.48, 0.44, 0.22), False, False),
    ('forest_floor', 'Ground079S', 2.0, (0.26, 0.22, 0.14), False, False),
    ('needles', 'Grass004', 1.1, (0.40, 0.28, 0.13), True, True),
    ('moss', 'Rock051', 1.2, (0.22, 0.32, 0.14), False, False),
    ('gravel', 'Gravel043', 1.4, (0.42, 0.40, 0.36), False, False),
    ('rock', 'Rock051', 2.6, (0.44, 0.43, 0.41), True, True),
    ('road_shoulder', 'Concrete013', 3.2, (0.46, 0.44, 0.40), False, False),
]

report = {'phase': 'Phase 6 - ten layer landscape material', 'timestamp': datetime.now().isoformat(timespec='seconds'),
          'layers': LAYERS and [{'name': entry[0], 'pack': entry[1], 'tile_m': entry[2]} for entry in LAYERS],
          'notes': [], 'result': 'FAILED'}


def log(message):
    print('PHASE6-LAND: ' + str(message))


def asset_tools():
    return unreal.AssetToolsHelpers.get_asset_tools()


def texture(pack, kind):
    return unreal.EditorAssetLibrary.load_asset('{0}/{1}/T_H_{1}_{2}'.format(TEX_ROOT, pack, kind))


def node(material, cls, x, y):
    expression = unreal.MaterialEditingLibrary.create_material_expression(material, cls, x, y)
    if expression is None:
        raise RuntimeError('could not create material expression {0}'.format(cls.__name__))
    return expression


def link(source, target, to_input='', from_output=''):
    unreal.MaterialEditingLibrary.connect_material_expressions(source, from_output, target, to_input)
    return target


def scalar(material, name, value, x, y):
    expression = node(material, unreal.MaterialExpressionScalarParameter, x, y)
    expression.set_editor_property('parameter_name', name)
    expression.set_editor_property('default_value', value)
    return expression


def constant(material, value, x, y):
    expression = node(material, unreal.MaterialExpressionConstant, x, y)
    expression.set_editor_property('r', value)
    return expression


def constant3(material, colour, x, y):
    expression = node(material, unreal.MaterialExpressionConstant3Vector, x, y)
    expression.set_editor_property('constant', unreal.LinearColor(colour[0], colour[1], colour[2], 1.0))
    return expression


def math(material, cls, inputs, x, y):
    expression = node(material, cls, x, y)
    for index, source in enumerate(inputs):
        link(source, expression, 'AB'[index])
    return expression


def multiply(material, a, b, x, y):
    return math(material, unreal.MaterialExpressionMultiply, (a, b), x, y)


def subtract(material, a, b, x, y):
    return math(material, unreal.MaterialExpressionSubtract, (a, b), x, y)


def divide(material, a, b, x, y):
    return math(material, unreal.MaterialExpressionDivide, (a, b), x, y)


def saturate(material, a, x, y):
    # single input node: its pin name is empty, not 'A' (feeding 'A' leaves the input missing
    # and the whole material fails to compile)
    expression = node(material, unreal.MaterialExpressionSaturate, x, y)
    link(a, expression, '')
    return expression


def lerp(material, a, b, alpha, x, y):
    expression = node(material, unreal.MaterialExpressionLinearInterpolate, x, y)
    link(a, expression, 'A')
    link(b, expression, 'B')
    link(alpha, expression, 'Alpha')
    return expression


def uv_grid(material, world_position, tile_parameter, x, y):
    """World position (cm) divided by a per layer tile size parameter = world aligned UVs."""
    return divide(material, world_position, tile_parameter, x, y)


def mask_above(material, value, threshold, sharpness, x, y):
    return saturate(material, multiply(material, subtract(material, value, constant(material, threshold, x - 120, y + 40),
                                                            x - 60, y), constant(material, sharpness, x - 120, y + 80),
                                       x - 20, y), x + 20, y)


def mask_below(material, value, threshold, sharpness, x, y):
    return saturate(material, multiply(material, subtract(material, constant(material, threshold, x - 120, y + 40), value,
                                                            x - 60, y), constant(material, sharpness, x - 120, y + 80),
                                       x - 20, y), x + 20, y)


def sample(material, texture_asset, uv, name, x, y, kind='COLOR'):
    expression = node(material, unreal.MaterialExpressionTextureSampleParameter2D, x, y)
    expression.set_editor_property('parameter_name', name)
    expression.set_editor_property('texture', texture_asset)
    if kind == 'NORMAL':
        expression.set_editor_property('sampler_type', unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
    elif kind == 'GRAYSCALE':
        expression.set_editor_property('sampler_type', unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_GRAYSCALE)
    link(uv, expression, 'UV')
    return expression


def build_material():
    material = unreal.EditorAssetLibrary.load_asset(MATERIAL_PATH)
    if material is None:
        material = asset_tools().create_asset('M_LandscapeBlockout', WORLD_DIR, unreal.Material,
                                             unreal.MaterialFactoryNew())
    if material is None:
        raise RuntimeError('could not create ' + MATERIAL_PATH)
    # rebuilt in place: the asset keeps its identity so the landscape keeps referencing it
    unreal.MaterialEditingLibrary.delete_all_material_expressions(material)
    material.set_editor_property('two_sided', False)
    try:
        material.set_editor_property('blend_mode', unreal.BlendMode.BLEND_OPAQUE)
    except Exception:
        pass

    world = node(material, unreal.MaterialExpressionWorldPosition, -2600, 0)
    vertex_normal = node(material, unreal.MaterialExpressionVertexNormalWS, -2600, 220)
    up = constant3(material, (0.0, 0.0, 1.0), -2400, 300)
    dot_n = math(material, unreal.MaterialExpressionDotProduct, (vertex_normal, up), -2200, 240)
    flat = mask_above(material, dot_n, 0.85, 6.0, -1900, 140)
    steep = mask_below(material, dot_n, 0.84, 6.0, -1900, 400)
    mid = multiply(material, mask_above(material, dot_n, 0.60, 5.0, -1900, 640),
                   mask_below(material, dot_n, 0.96, 5.0, -1900, 860), -1750, 740)
    height = divide(material, channel(material, world, 'B', -2400, 520),
                    constant(material, 20000.0, -2300, 560), -2200, 520)
    noise_uv = divide(material, world, constant(material, 1000.0, -2400, 660), -2300, 660)
    noise_a = node(material, unreal.MaterialExpressionNoise, -2100, 660)
    noise_a.set_editor_property('scale', 3.5)
    noise_a.set_editor_property('levels', 3)
    link(noise_uv, noise_a, 'Position')
    noise_b = node(material, unreal.MaterialExpressionNoise, -2100, 820)
    noise_b.set_editor_property('scale', 0.9)
    noise_b.set_editor_property('levels', 3)
    link(noise_uv, noise_b, 'Position')

    masks = {
        # height is world Z / 200 m: the valley floor is ~10 m, the home property ~150 m and
        # the ridges ~180 m, so the bands are wide enough for the ground to read as grass over
        # most of the world (the first attempt used far too narrow bands and everything turned
        # into dry grass).
        'clay': multiply(material, flat, mask_below(material, height, 0.030, 20.0, -1500, 60), -1300, 60),
        'soil': constant(material, 1.0, -1300, 180),
        'grass': multiply(material, flat, mask_below(material, height, 0.86, 8.0, -1500, 300), -1300, 300),
        'dry_grass': multiply(material, flat, mask_above(material, height, 0.84, 6.0, -1500, 440), -1300, 440),
        'forest_floor': multiply(material, mid, multiply(material, mask_above(material, height, 0.20, 6.0, -1500, 600),
                                                         noise_a, -1400, 600), -1300, 580),
        'needles': multiply(material, mask_above(material, height, 0.35, 5.0, -1500, 760), noise_a, -1300, 760),
        'moss': multiply(material, mid, noise_b, -1300, 900),
        'gravel': multiply(material, mid, mask_above(material, noise_a, 0.62, 6.0, -1500, 1040), -1300, 1040),
        'rock': steep,
        'road_shoulder': multiply(material, multiply(material, flat,
                                                    mask_above(material, height, 0.55, 8.0, -1500, 1180), -1300, 1180),
                                  mask_above(material, noise_b, 0.48, 4.0, -1500, 1320), -1250, 1250),
    }

    colour = None
    roughness = None
    normal_chain = None
    for index, (name, pack, tile_m, tint, use_normal, use_macro) in enumerate(LAYERS):
        base_y = index * 340
        tile = scalar(material, 'L{0}_Tile'.format(index + 1), tile_m * 100.0, -1060, base_y)
        uv = uv_grid(material, world, tile, -920, base_y)
        tint_node = constant3(material, tint, -900, base_y - 130)
        colour_sample = sample(material, texture(pack, 'COLOR'), uv, 'L{0}_Color'.format(index + 1), -760, base_y)
        tinted = multiply(material, colour_sample, tint_node, -620, base_y)
        if use_macro:
            # Macro variation without a second sampler: a slow noise modulates the brightness,
            # so the ground does not read as one stamp repeated over kilometres (the earlier
            # 4x fine tiling attempt produced moire instead and was removed).
            variation = lerp(material, constant(material, 0.80, -900, base_y - 260),
                             constant(material, 1.20, -900, base_y - 320), noise_b, -480, base_y - 220)
            tinted = multiply(material, tinted, variation, -480, base_y)
        rough_sample = sample(material, texture(pack, 'ROUGHNESS'), uv, 'L{0}_Rough'.format(index + 1),
                              -760, base_y + 130, 'GRAYSCALE')
        rough_value = channel(material, rough_sample, 'R', -620, base_y + 130)
        if colour is None:
            colour = tinted
            roughness = rough_value
        else:
            colour = lerp(material, colour, tinted, masks[name], -340, base_y)
            roughness = lerp(material, roughness, rough_value, masks[name], -340, base_y + 130)
        if use_normal:
            normal_sample = sample(material, texture(pack, 'NORMAL'), uv, 'L{0}_Normal'.format(index + 1),
                                   -760, base_y - 60, 'NORMAL')
            normal_chain = normal_sample if normal_chain is None else lerp(
                material, normal_chain, normal_sample, masks[name], -340, base_y - 60)

    unreal.MaterialEditingLibrary.connect_material_property(colour, '', unreal.MaterialProperty.MP_BASE_COLOR)
    unreal.MaterialEditingLibrary.connect_material_property(roughness, '', unreal.MaterialProperty.MP_ROUGHNESS)
    if normal_chain is not None:
        unreal.MaterialEditingLibrary.connect_material_property(normal_chain, '', unreal.MaterialProperty.MP_NORMAL)
    try:
        unreal.MaterialEditingLibrary.layout_material_expressions(material)
    except Exception as exc:
        report['notes'].append('layout failed: {0}'.format(exc))
    unreal.MaterialEditingLibrary.recompile_material(material)
    unreal.EditorAssetLibrary.save_loaded_asset(material, only_if_is_dirty=False)
    log('material built: {0}'.format(MATERIAL_PATH))
    return material


def channel(material, source, channel_letter, x, y):
    expression = node(material, unreal.MaterialExpressionComponentMask, x, y)
    expression.set_editor_property('r', channel_letter == 'R')
    expression.set_editor_property('g', channel_letter == 'G')
    expression.set_editor_property('b', channel_letter == 'B')
    expression.set_editor_property('a', channel_letter == 'A')
    link(source, expression)
    return expression


def build_instance(material):
    instance = unreal.EditorAssetLibrary.load_asset(INSTANCE_PATH)
    if instance is None:
        instance = asset_tools().create_asset('MI_LandscapeBlockout', WORLD_DIR, unreal.MaterialInstanceConstant,
                                              unreal.MaterialInstanceConstantFactoryNew())
    if instance is None:
        raise RuntimeError('could not create ' + INSTANCE_PATH)
    instance.set_editor_property('parent', material)

    missing = []
    for index, (_name, pack, tile_m, _tint, use_normal, use_macro) in enumerate(LAYERS):
        wanted = [('L{0}_Color'.format(index + 1), 'COLOR'), ('L{0}_Rough'.format(index + 1), 'ROUGHNESS')]
        if use_normal:
            wanted.append(('L{0}_Normal'.format(index + 1), 'NORMAL'))
        for parameter, kind in wanted:
            texture_asset = texture(pack, kind)
            if texture_asset is None:
                missing.append('{0}/{1}'.format(pack, kind))
                continue
            unreal.MaterialEditingLibrary.set_material_instance_texture_parameter_value(instance, parameter,
                                                                                        texture_asset)
        unreal.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(
            instance, 'L{0}_Tile'.format(index + 1), tile_m * 100.0)
        if use_macro:
            unreal.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(
                instance, 'L{0}_DetailScale'.format(index + 1), 1.0 / (tile_m * 100.0 * 4.0))
    unreal.EditorAssetLibrary.save_loaded_asset(instance, only_if_is_dirty=False)
    report['missing_textures'] = sorted(set(missing))
    log('instance built: {0} (missing textures: {1})'.format(INSTANCE_PATH, report['missing_textures']))
    return instance


def assign_to_landscape(instance):
    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    assigned = []
    for actor in actor_subsystem.get_all_level_actors():
        class_name = actor.get_class().get_name()
        if class_name not in ('Landscape', 'LandscapeStreamingProxy'):
            continue
        try:
            actor.set_editor_property('landscape_material', instance)
            assigned.append('{0}[{1}]'.format(actor.get_actor_label(), class_name))
        except Exception as exc:
            report['notes'].append('{0}: {1}'.format(actor.get_actor_label(), exc))
    log('material assigned to {0} landscape actor(s)'.format(len(assigned)))
    return assigned


def main():
    out_dir = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir() + REPORT_REL)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    level_subsystem.load_level('/Game/Game/Environment/Lvl_Rural')
    log('level loaded')

    material = build_material()
    instance = build_instance(material)
    report['assigned'] = assign_to_landscape(instance)
    # the superseded assets from the first attempt are removed so the project keeps exactly one
    # landscape material (the landscape now references the rebuilt MI_LandscapeBlockout)
    removed = []
    for path in SUPERSEDED_PATHS:
        if unreal.EditorAssetLibrary.does_asset_exist(path) and unreal.EditorAssetLibrary.delete_asset(path):
            removed.append(path)
    report['removed_superseded'] = removed
    try:
        level_subsystem.save_current_level()
        report['level_saved'] = True
    except Exception as exc:
        report['level_saved'] = False
        report['notes'].append('save level failed: {0}'.format(exc))

    report['material_path'] = MATERIAL_PATH
    report['instance_path'] = INSTANCE_PATH
    report['layer_count'] = len(LAYERS)
    report['result'] = 'OK' if report['assigned'] and not report['missing_textures'] else 'FAILED'
    path = os.path.join(out_dir, REPORT_NAME)
    with open(path, 'w') as handle:
        json.dump(report, handle, indent=2)
    log('result={0} notes={1}'.format(report['result'], report['notes']))
    print('PHASE6_LANDSCAPE_DONE ' + path)


if __name__ == '__main__':
    main()

