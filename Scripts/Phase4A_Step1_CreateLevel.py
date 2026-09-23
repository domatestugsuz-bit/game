# -*- coding: utf-8 -*-
"""Phase 4A - step 1: create the WP rural level, blockout material, clear template landscape."""

import json
import os

import unreal

LEVEL = '/Game/Game/Environment/Lvl_Rural'
TEMPLATE = '/Engine/Maps/Templates/OpenWorld'
FOLDER = '/Game/Game/Environment/World'
GAMEMODE = '/Game/Game/Core/BP_GameMode.BP_GameMode_C'
MATERIAL = FOLDER + '/M_LandscapeBlockout'
INSTANCE = FOLDER + '/MI_LandscapeBlockout'

report = {'steps': [], 'result': 'FAILED'}

level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
editor_subsystem = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
asset_tools = unreal.AssetToolsHelpers.get_asset_tools()


def log(message):
    unreal.log('P4A-S1: ' + str(message))
    report['steps'].append(str(message))


def labels():
    return ['{0} [{1}]'.format(a.get_actor_label(), a.get_class().get_name())
            for a in actor_subsystem.get_all_level_actors()]


def make_material():
    """Blockout material: three flat elevation zones blended by world height."""
    if unreal.EditorAssetLibrary.does_asset_exist(MATERIAL):
        return unreal.EditorAssetLibrary.load_asset(MATERIAL)
    if not unreal.EditorAssetLibrary.does_directory_exist(FOLDER):
        unreal.EditorAssetLibrary.make_directory(FOLDER)
    material = asset_tools.create_asset('M_LandscapeBlockout', FOLDER, unreal.Material,
                                        unreal.MaterialFactoryNew())
    if material is None:
        return None
    lib = unreal.MaterialEditingLibrary
    # t = world_z (cm) / 26000  ->  0 .. ~1 across the 0..260 m elevation range
    world_position = lib.create_material_expression(material, unreal.MaterialExpressionWorldPosition, -1500, 0)
    mask = lib.create_material_expression(material, unreal.MaterialExpressionComponentMask, -1300, 0)
    mask.set_editor_properties({'r': False, 'g': False, 'b': True, 'a': False})
    divide = lib.create_material_expression(material, unreal.MaterialExpressionDivide, -1120, 0)
    divide.set_editor_properties({'const_b': 26000.0})
    t2 = lib.create_material_expression(material, unreal.MaterialExpressionMultiply, -940, -120)
    t2.set_editor_properties({'const_b': 2.0})
    clamp2 = lib.create_material_expression(material, unreal.MaterialExpressionClamp, -780, -120)
    t3 = lib.create_material_expression(material, unreal.MaterialExpressionSubtract, -940, 140)
    t3.set_editor_properties({'const_b': 0.5})
    t3b = lib.create_material_expression(material, unreal.MaterialExpressionMultiply, -780, 140)
    t3b.set_editor_properties({'const_b': 2.0})
    clamp3 = lib.create_material_expression(material, unreal.MaterialExpressionClamp, -620, 140)
    low = lib.create_material_expression(material, unreal.MaterialExpressionVectorParameter, -1300, 380)
    low.set_editor_properties({'parameter_name': 'ZoneLow',
                               'default_value': unreal.LinearColor(0.30, 0.36, 0.20, 1.0)})
    mid = lib.create_material_expression(material, unreal.MaterialExpressionVectorParameter, -1300, 540)
    mid.set_editor_properties({'parameter_name': 'ZoneMid',
                               'default_value': unreal.LinearColor(0.21, 0.29, 0.15, 1.0)})
    high = lib.create_material_expression(material, unreal.MaterialExpressionVectorParameter, -1300, 700)
    high.set_editor_properties({'parameter_name': 'ZoneHigh',
                                'default_value': unreal.LinearColor(0.44, 0.43, 0.38, 1.0)})
    lerp_low_mid = lib.create_material_expression(material, unreal.MaterialExpressionLinearInterpolate, -420, 380)
    lerp_all = lib.create_material_expression(material, unreal.MaterialExpressionLinearInterpolate, -200, 380)
    roughness = lib.create_material_expression(material, unreal.MaterialExpressionScalarParameter, -420, 120)
    roughness.set_editor_properties({'parameter_name': 'Roughness', 'default_value': 0.85})

    lib.connect_material_expressions(world_position, '', mask, '')
    lib.connect_material_expressions(mask, '', divide, '')
    lib.connect_material_expressions(divide, '', t2, '')
    lib.connect_material_expressions(t2, '', clamp2, '')
    lib.connect_material_expressions(divide, '', t3, '')
    lib.connect_material_expressions(t3, '', t3b, '')
    lib.connect_material_expressions(t3b, '', clamp3, '')
    lib.connect_material_expressions(low, '', lerp_low_mid, 'A')
    lib.connect_material_expressions(mid, '', lerp_low_mid, 'B')
    lib.connect_material_expressions(clamp2, '', lerp_low_mid, 'Alpha')
    lib.connect_material_expressions(lerp_low_mid, '', lerp_all, 'A')
    lib.connect_material_expressions(high, '', lerp_all, 'B')
    lib.connect_material_expressions(clamp3, '', lerp_all, 'Alpha')
    lib.connect_material_property(lerp_all, '', unreal.MaterialProperty.MP_BASE_COLOR)
    lib.connect_material_property(roughness, '', unreal.MaterialProperty.MP_ROUGHNESS)
    lib.recompile_material(material)
    unreal.EditorAssetLibrary.save_asset(MATERIAL, only_if_is_dirty=False)
    log('created ' + MATERIAL)
    return material


def make_instance(material):
    if unreal.EditorAssetLibrary.does_asset_exist(INSTANCE):
        return unreal.EditorAssetLibrary.load_asset(INSTANCE)
    if material is None:
        return None
    instance = asset_tools.create_asset('MI_LandscapeBlockout', FOLDER,
                                        unreal.MaterialInstanceConstant,
                                        unreal.MaterialInstanceConstantFactoryNew())
    if instance is None:
        return None
    lib = unreal.MaterialEditingLibrary
    lib.set_material_instance_parent(instance, material)
    lib.update_material_instance(instance)
    unreal.EditorAssetLibrary.save_asset(INSTANCE, only_if_is_dirty=False)
    log('created ' + INSTANCE)
    return instance


# ------------------------------------------------------------------ level
if unreal.EditorAssetLibrary.does_asset_exist(LEVEL):
    log('level exists, loading ' + LEVEL)
    level_subsystem.load_level(LEVEL)
else:
    created = level_subsystem.new_level_from_template(LEVEL, TEMPLATE)
    log('new_level_from_template -> ' + str(created))
    level_subsystem.save_current_level()

world = editor_subsystem.get_editor_world()
report['world'] = world.get_name() if world else 'none'
report['world_path'] = world.get_path_name() if world else 'none'

settings = world.get_world_settings()
partition = settings.get_editor_property('world_partition')
report['world_partition_is_none'] = (partition is None)
report['world_partition'] = 'none' if partition is None else str(partition)

game_mode = unreal.load_class(None, GAMEMODE)
if game_mode is not None:
    settings.set_editor_property('default_game_mode', game_mode)
    report['game_mode'] = str(settings.get_editor_property('default_game_mode'))
else:
    report['game_mode'] = 'BP_GameMode_C not found'

report['actors_before'] = len(labels())
log('actors before cleanup: {0}'.format(report['actors_before']))
report['actors_before_list'] = labels()
after = labels()

# ------------------------------------------------------------------ material
material = make_material()
instance = make_instance(material)
report['landscape_material_instance'] = instance.get_path_name() if instance else 'none'

# --------------------- clear the template landscape (KEEP IT: it is our terrain)
# Phase 4A shapes the landscape that ships with the engine's OpenWorld template
# (World Partition + streaming proxies), so nothing is cleared here.
report['cleared_actors'] = 0
report['landscape_actors_after'] = [x for x in after if 'Landscape' in x]
report['actors_after_list'] = after

level_subsystem.save_current_level()
report['saved'] = True
log('level saved')

level_subsystem.load_level(LEVEL)
reloaded = labels()
report['actors_after_reload'] = len(reloaded)
report['landscape_actors_after_reload'] = [x for x in reloaded if 'Landscape' in x]
report['ok'] = (len(report['landscape_actors_after_reload']) >= 1
                and report['saved'] and not report['world_partition_is_none'])
report['result'] = 'OK' if report['ok'] else 'CHECK'

out_dir = os.path.join(os.environ.get('TEMP', '.'), 'MyProject_Phase4A')
if not os.path.isdir(out_dir):
    os.makedirs(out_dir)
with open(os.path.join(out_dir, 'phase4a_step1.json'), 'w') as handle:
    json.dump(report, handle, indent=2, default=str)
log('report written, result=' + report['result'])
