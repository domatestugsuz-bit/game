# -*- coding: utf-8 -*-
"""Phase 3A - build the graybox gameplay prototype level.

Run in EDITOR mode (headless), with an empty startup map so the template level is
never touched:
  UnrealEditor-Cmd.exe "<Project>.uproject" /Engine/Maps/Entry
                       -ExecutePythonScript="<this file>"
                       -unattended -nosplash -nullrhi -stdout -NoSourceControl

Creates: Content/Game/Environment/Lvl_GameplayPrototype
  * forest / semi-rural ground (graybox)
  * small house + garage blocks
  * car parking area with a placeholder vehicle body
  * placeholder trees / vegetation
  * PlayerStart, directional light, sky light, height fog
  * the interaction test object placed in front of the spawn point
  * World Settings override pointing at BP_GameMode

Idempotent: if the level already exists the script reports it and stops.
Existing template assets are never modified.
"""

import json
import os
from datetime import datetime

import unreal

LEVEL_PATH = '/Game/Game/Environment/Lvl_GameplayPrototype'
GAME_MODE_PATH = '/Game/Game/Core/BP_GameMode.BP_GameMode_C'
TEST_OBJECT_PATH = '/Game/Game/Interaction/BP_InteractionTestObject.BP_InteractionTestObject_C'

CUBE = '/Engine/BasicShapes/Cube.Cube'
CYLINDER = '/Engine/BasicShapes/Cylinder.Cylinder'
SPHERE = '/Engine/BasicShapes/Sphere.Sphere'

report = {
    'phase': 'Phase 3A - prototype level',
    'timestamp': datetime.now().isoformat(timespec='seconds'),
    'level': LEVEL_PATH,
    'spawned': [],
    'failed': [],
    'notes': [],
    'result': 'FAILED',
}


def log(message):
    unreal.log('PHASE3A-LEVEL: ' + str(message))


def warn(message):
    unreal.log_warning('PHASE3A-LEVEL: ' + str(message))
    report['notes'].append(str(message))


def fail(message):
    unreal.log_error('PHASE3A-LEVEL: ' + str(message))
    report['failed'].append(str(message))


def level_subsystem():
    return unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)


def actor_subsystem():
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def load_mesh(path):
    mesh = unreal.EditorAssetLibrary.load_asset(path)
    if mesh is None:
        warn('mesh not found: {0}'.format(path))
    return mesh


def spawn_graybox(actor_class, location, rotation, scale, label, mesh_path=None, material=None):
    """Spawns a static mesh actor used as graybox blockout geometry."""
    try:
        actor = actor_subsystem().spawn_actor_from_class(unreal.StaticMeshActor, location, rotation)
    except Exception as exc:
        fail('spawn failed for {0}: {1}'.format(label, exc))
        return None
    if actor is None:
        fail('spawn returned None for ' + label)
        return None

    actor.set_actor_label(label)
    component = actor.get_editor_property('static_mesh_component')
    if mesh_path:
        mesh = load_mesh(mesh_path)
        if mesh:
            component.set_editor_property('static_mesh', mesh)
    if material:
        component.set_editor_property('override_materials', [material])
    actor.set_actor_scale3d(scale)
    report['spawned'].append('{0} at {1}'.format(label, location))
    return actor


def spawn_from_class(actor_class, location, rotation, label):
    """Spawns any actor class (lights, PlayerStart, gameplay objects)."""
    try:
        actor = actor_subsystem().spawn_actor_from_class(actor_class, location, rotation)
    except Exception as exc:
        fail('spawn failed for {0}: {1}'.format(label, exc))
        return None
    if actor is None:
        fail('spawn returned None for ' + label)
        return None
    actor.set_actor_label(label)
    report['spawned'].append(label)
    return actor


def set_world_game_mode(game_mode_class):
    """Sets the World Settings GameMode override (DefaultEngine.ini stays untouched)."""
    for actor in actor_subsystem().get_all_level_actors():
        if isinstance(actor, unreal.WorldSettings):
            try:
                actor.set_editor_property('default_game_mode', game_mode_class)
                log('world settings: default_game_mode -> BP_GameMode')
                return True
            except Exception as exc:
                warn('world settings game mode failed: {0}'.format(exc))
    warn('WorldSettings actor not found; the GameMode must be set manually')
    return False


def build_scene():
    """Graybox blockout: ground, forest, house, garage, car place, test object."""
    graybox = unreal.EditorAssetLibrary.load_asset('/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial')

    # ---- ground / semi-rural terrain --------------------------------------
    spawn_graybox(None, unreal.Vector(0, 0, -60), unreal.Rotator(0, 0, 0),
                  unreal.Vector(220, 220, 1.2), 'SM_Ground', CUBE, graybox)

    # ---- forest border (placeholder trees) --------------------------------
    tree_positions = [
        (-3800, -3600), (-3200, -4200), (-2400, -3800), (-1600, -4400),
        (2400, -4000), (3200, -3400), (4000, -4200), (-4200, 2200),
        (4200, 2600), (3600, 3600), (-3600, 3400), (-4400, 1200),
        (1200, -4800), (-800, 4200), (2800, 4200), (-2000, 4600),
    ]
    for index, (x, y) in enumerate(tree_positions):
        spawn_graybox(None, unreal.Vector(x, y, 260), unreal.Rotator(0, index * 23.0, 0),
                      unreal.Vector(0.9, 0.9, 5.2), 'SM_Tree_Trunk_{0}'.format(index), CYLINDER, graybox)
        spawn_graybox(None, unreal.Vector(x, y, 720), unreal.Rotator(0, index * 17.0, 0),
                      unreal.Vector(5.5, 5.5, 3.4), 'SM_Tree_Canopy_{0}'.format(index), SPHERE, graybox)

    # ---- small house ------------------------------------------------------
    spawn_graybox(None, unreal.Vector(1500, 900, 160), unreal.Rotator(0, 0, 0),
                  unreal.Vector(9.0, 7.0, 3.2), 'SM_House_Body', CUBE, graybox)
    spawn_graybox(None, unreal.Vector(1500, 900, 380), unreal.Rotator(0, 0, 0),
                  unreal.Vector(10.0, 8.0, 1.4), 'SM_House_Roof', CUBE, graybox)
    spawn_graybox(None, unreal.Vector(1500, 1350, 110), unreal.Rotator(0, 0, 0),
                  unreal.Vector(2.0, 0.3, 2.2), 'SM_House_Door', CUBE, graybox)

    # ---- garage -----------------------------------------------------------
    spawn_graybox(None, unreal.Vector(300, 1800, 150), unreal.Rotator(0, 0, 0),
                  unreal.Vector(6.5, 5.5, 3.0), 'SM_Garage_Body', CUBE, graybox)
    spawn_graybox(None, unreal.Vector(300, 1250, 130), unreal.Rotator(0, 0, 0),
                  unreal.Vector(5.0, 0.25, 2.6), 'SM_Garage_Door', CUBE, graybox)

    # ---- car parking area + placeholder vehicle (architecture placeholder) -
    spawn_graybox(None, unreal.Vector(300, 500, 5), unreal.Rotator(0, 0, 0),
                  unreal.Vector(8.0, 5.0, 0.15), 'SM_ParkingPad', CUBE, graybox)
    spawn_graybox(None, unreal.Vector(300, 500, 75), unreal.Rotator(0, 0, 0),
                  unreal.Vector(4.4, 1.9, 1.0), 'SM_CarPlaceholder_Body', CUBE, graybox)
    spawn_graybox(None, unreal.Vector(300, 500, 150), unreal.Rotator(0, 0, 0),
                  unreal.Vector(2.1, 1.7, 0.7), 'SM_CarPlaceholder_Cabin', CUBE, graybox)

    # ---- workbench next to the garage -------------------------------------
    spawn_graybox(None, unreal.Vector(-250, 1500, 55), unreal.Rotator(0, 0, 0),
                  unreal.Vector(2.6, 0.9, 1.1), 'SM_Workbench', CUBE, graybox)

    # ---- interaction test object, right in front of the spawn -------------
    test_class = unreal.load_class(None, TEST_OBJECT_PATH)
    if test_class:
        test_object = spawn_from_class(test_class, unreal.Vector(320, -260, 45), unreal.Rotator(0, 180, 0), 'BP_InteractionTestObject')
        if test_object:
            test_object.set_actor_scale3d(unreal.Vector(0.7, 0.7, 0.7))
    else:
        fail('test object class not found: ' + TEST_OBJECT_PATH)

    # ---- player spawn -----------------------------------------------------
    spawn_from_class(unreal.PlayerStart, unreal.Vector(0, 0, 120), unreal.Rotator(0, 0, 0), 'PlayerStart')

    # ---- lighting ---------------------------------------------------------
    spawn_from_class(unreal.DirectionalLight, unreal.Vector(0, 0, 1200), unreal.Rotator(-48, 35, 0), 'Light_Sun')
    spawn_from_class(unreal.SkyLight, unreal.Vector(0, 0, 600), unreal.Rotator(0, 0, 0), 'Light_Sky')
    spawn_from_class(unreal.ExponentialHeightFog, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0), 'Fog_Height')
    spawn_from_class(unreal.SkyAtmosphere, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0), 'SkyAtmosphere')


def write_report():
    rel = unreal.Paths.project_saved_dir() + 'Phase3A/'
    out_dir = unreal.Paths.convert_relative_path_to_full(rel)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    path = os.path.join(out_dir, 'phase3a_level_report.json')
    with open(path, 'w') as handle:
        json.dump(report, handle, indent=2)
    log('report -> ' + path)
    return path


def main():
    subsystem = level_subsystem()

    if unreal.EditorAssetLibrary.does_asset_exist(LEVEL_PATH):
        log('level already exists, left untouched: ' + LEVEL_PATH)
        report['notes'].append('level already exists')
        report['result'] = 'EXISTS'
        return write_report()

    try:
        subsystem.new_level(LEVEL_PATH)
    except Exception as exc:
        fail('new_level failed: {0}'.format(exc))
        return write_report()

    log('level created: ' + LEVEL_PATH)
    build_scene()

    game_mode_class = unreal.load_class(None, GAME_MODE_PATH)
    if game_mode_class:
        set_world_game_mode(game_mode_class)
    else:
        fail('game mode class not found: ' + GAME_MODE_PATH)

    try:
        subsystem.save_current_level()
        report['saved'] = True
        log('level saved')
    except Exception as exc:
        fail('save_current_level failed: {0}'.format(exc))

    report['result'] = 'OK' if not report['failed'] else 'FAILED'
    return write_report()


if __name__ == '__main__':
    report_path = main()
    print('PHASE3A_LEVEL_DONE ' + str(report_path))
    print('PHASE3A_LEVEL spawned={0} failed={1} result={2}'.format(
        len(report['spawned']), len(report['failed']), report['result']))
    for note in report['notes'][:15]:
        print('PHASE3A_LEVEL_NOTE: ' + note)
    for problem in report['failed'][:15]:
        print('PHASE3A_LEVEL_FAIL: ' + problem)
    print('PHASE3A_LEVEL_RESULT: ' + report['result'])
