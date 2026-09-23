# -*- coding: utf-8 -*-
"""Phase 3B - create BP_VehicleBase and connect the placeholder car to it.

Run in EDITOR mode (headless):
  UnrealEditor-Cmd.exe "<Project>.uproject" /Engine/Maps/Entry
                       -ExecutePythonScript="<this file>"
                       -unattended -nosplash -nullrhi -stdout -NoSourceControl

  1. creates /Game/Game/Vehicles/Base/BP_VehicleBase (child of AVehicleBase) and
     tunes its prototype defaults
  2. replaces the two graybox placeholder car actors in Lvl_GameplayPrototype with
     one BP_VehicleBase instance at the same spot (parking pad, PlayerStart, house,
     garage, trees and the interaction test object stay untouched)
  3. saves the level
Idempotent: an existing BP_VehicleBase is reused, an existing vehicle actor in the
level means the replacement step is skipped.
"""

import json
import os
from datetime import datetime

import unreal

LEVEL_PATH = '/Game/Game/Environment/Lvl_GameplayPrototype'
VEHICLE_FOLDER = '/Game/Game/Vehicles/Base'
VEHICLE_BP_PATH = VEHICLE_FOLDER + '/BP_VehicleBase'
NATIVE_VEHICLE = '/Script/MyProject.VehicleBase'
PLACEHOLDER_LABEL_HINT = 'CarPlaceholder'

report = {'phase': 'Phase 3B - vehicle setup', 'timestamp': datetime.now().isoformat(timespec='seconds'),
          'created': [], 'existing': [], 'failed': [], 'notes': [], 'configured': [], 'result': 'FAILED'}


def log(message):
    unreal.log('PHASE3B: ' + str(message))


def warn(message):
    unreal.log_warning('PHASE3B: ' + str(message))
    report['notes'].append(str(message))


def fail(message):
    unreal.log_error('PHASE3B: ' + str(message))
    report['failed'].append(str(message))


def write_report():
    rel = unreal.Paths.project_saved_dir() + 'Phase3B/'
    out_dir = unreal.Paths.convert_relative_path_to_full(rel)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    report['result'] = 'OK' if not report['failed'] else 'FAILED'
    path = os.path.join(out_dir, 'phase3b_vehicle_setup_report.json')
    with open(path, 'w') as handle:
        json.dump(report, handle, indent=2)
    return path


def create_vehicle_blueprint():
    """Creates BP_VehicleBase (child of the C++ AVehicleBase) - idempotent."""
    if unreal.EditorAssetLibrary.does_asset_exist(VEHICLE_BP_PATH):
        report['existing'].append(VEHICLE_BP_PATH)
        log('already exists: ' + VEHICLE_BP_PATH)
        return unreal.EditorAssetLibrary.load_asset(VEHICLE_BP_PATH)

    native_class = unreal.load_class(None, NATIVE_VEHICLE)
    if native_class is None:
        fail('native class not found (was the C++ module compiled?): ' + NATIVE_VEHICLE)
        return None

    if not unreal.EditorAssetLibrary.does_directory_exist(VEHICLE_FOLDER):
        unreal.EditorAssetLibrary.make_directory(VEHICLE_FOLDER)

    factory = unreal.BlueprintFactory()
    factory.set_editor_property('parent_class', native_class)
    blueprint = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        'BP_VehicleBase', VEHICLE_FOLDER, unreal.Blueprint, factory)
    if blueprint is None:
        fail('could not create ' + VEHICLE_BP_PATH)
        return None

    report['created'].append(VEHICLE_BP_PATH)
    log('created: ' + VEHICLE_BP_PATH)

    try:
        unreal.BlueprintEditorLibrary.compile_blueprint(blueprint)
    except Exception as exc:
        warn('compile_blueprint failed: {0}'.format(exc))

    cdo = unreal.get_default_object(blueprint.generated_class())
    defaults = {
        'max_speed': 600.0,
        'reverse_speed_factor': 0.45,
        'speed_interp_speed': 1.6,
        'coast_interp_speed': 1.2,
        'steer_interp_speed': 6.0,
        'max_yaw_rate': 75.0,
        'handbrake_factor': 6.0,
        'b_sweep_movement': True,
        'board_prompt_text': unreal.Text('Araca bin'),
        'exit_prompt_text': unreal.Text('Ara\u00e7tan in'),
    }
    for prop, value in defaults.items():
        try:
            cdo.set_editor_property(prop, value)
            report['configured'].append(prop)
        except Exception as exc:
            warn('{0} failed: {1}'.format(prop, exc))
    return blueprint


def connect_placeholder_vehicle(vehicle_blueprint):
    """Replaces the graybox placeholder car with one BP_VehicleBase instance."""
    if vehicle_blueprint is None:
        return False

    vehicle_class = unreal.BlueprintEditorLibrary.generated_class(vehicle_blueprint)
    if vehicle_class is None:
        fail('BP_VehicleBase has no generated class')
        return False

    level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    level_subsystem.load_level(LEVEL_PATH)
    log('level loaded: ' + LEVEL_PATH)

    placeholders = []
    existing_vehicle = None
    for actor in actor_subsystem.get_all_level_actors():
        if 'BP_VehicleBase' in actor.get_class().get_name():
            existing_vehicle = actor
        try:
            label = actor.get_actor_label()
        except Exception:
            label = ''
        if PLACEHOLDER_LABEL_HINT in label:
            placeholders.append(actor)

    if existing_vehicle is not None:
        report['notes'].append('level already contains a BP_VehicleBase actor')
        log('level already has a vehicle actor: ' + existing_vehicle.get_name())
        return True

    if not placeholders:
        fail('no placeholder car actors found (labels containing "{0}")'.format(PLACEHOLDER_LABEL_HINT))
        return False

    body_actor = None
    for actor in placeholders:
        if 'Body' in actor.get_actor_label():
            body_actor = actor
            break
    if body_actor is None:
        body_actor = placeholders[0]

    spawn_location = body_actor.get_actor_location()
    spawn_rotation = body_actor.get_actor_rotation()
    # Sit on the parking pad (its top surface is roughly 13 cm above the ground).
    spawn_location.z = 63.0

    for actor in placeholders:
        try:
            label = actor.get_actor_label()
            actor_subsystem.destroy_actor(actor)
            report['notes'].append('removed placeholder: ' + label)
        except Exception as exc:
            warn('could not remove placeholder {0}: {1}'.format(actor, exc))

    vehicle = actor_subsystem.spawn_actor_from_class(vehicle_class, spawn_location, spawn_rotation)
    if vehicle is None:
        fail('could not spawn BP_VehicleBase')
        return False

    vehicle.set_actor_label('BP_VehicleBase')
    report['created'].append('level actor BP_VehicleBase at {0}'.format(spawn_location))
    log('vehicle placed at {0}'.format(spawn_location))

    try:
        level_subsystem.save_current_level()
        report['level_saved'] = True
        log('level saved')
    except Exception as exc:
        fail('save_current_level failed: {0}'.format(exc))
        return False
    return True


def main():
    blueprint = create_vehicle_blueprint()
    if blueprint is not None:
        try:
            unreal.EditorAssetLibrary.save_asset(VEHICLE_BP_PATH, only_if_is_dirty=False)
        except Exception as exc:
            warn('save_asset failed: {0}'.format(exc))
    connect_placeholder_vehicle(blueprint)
    return write_report()


if __name__ == '__main__':
    report_path = main()
    print('PHASE3B_SETUP_DONE ' + str(report_path))
    print('PHASE3B_SETUP created={0} existing={1} failed={2}'.format(
        len(report['created']), len(report['existing']), len(report['failed'])))
    for note in report['notes']:
        print('PHASE3B_NOTE: ' + note)
    for problem in report['failed']:
        print('PHASE3B_FAIL: ' + problem)
    print('PHASE3B_RESULT: ' + report['result'])
