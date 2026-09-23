# -*- coding: utf-8 -*-
"""Phase 3B - automated validation of the player <-> vehicle loop.

Editor world based (an -ExecutePythonScript script quits the editor when it
returns, so multi-tick PIE assertions cannot finish inside one launch; real
keyboard/mouse input is not exposed to Python at all - see the report).

It loads Lvl_GameplayPrototype, finds the placed BP_VehicleBase, spawns a player
character next to it and drives the REAL code paths:
  enter -> drive -> exit, plus Phase 3A regression checks.
Nothing is saved: spawned actors are destroyed again and the level is untouched.
"""

import json
import math
import os
from datetime import datetime

import unreal

LEVEL_PATH = '/Game/Game/Environment/Lvl_GameplayPrototype'
VEHICLE_BP_PATH = '/Game/Game/Vehicles/Base/BP_VehicleBase'
PLAYER_BP = '/Game/Game/Characters/Player/BP_PlayerCharacter.BP_PlayerCharacter_C'
TEST_OBJECT_BP = '/Game/Game/Interaction/BP_InteractionTestObject.BP_InteractionTestObject_C'

report = {'phase': 'Phase 3B - vehicle loop validation', 'timestamp': datetime.now().isoformat(timespec='seconds'),
          'tests': [], 'failed': [], 'notes': [], 'result': 'FAILED'}


def log(message):
    unreal.log('PHASE3B-VALIDATE: ' + str(message))


def test(test_id, name, passed, detail=''):
    entry = {'id': test_id, 'name': name, 'passed': bool(passed), 'detail': str(detail)}
    report['tests'].append(entry)
    if not passed:
        report['failed'].append('{0} {1}: {2}'.format(test_id, name, detail))
    unreal.log('PHASE3B_VALIDATE_TEST {0}: {1} {2} :: {3}'.format(
        test_id, 'PASS' if passed else 'FAIL', name, detail))
    return bool(passed)


def write_report():
    rel = unreal.Paths.project_saved_dir() + 'Phase3B/'
    out_dir = unreal.Paths.convert_relative_path_to_full(rel)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    report['result'] = 'OK' if not report['failed'] else 'FAILED'
    path = os.path.join(out_dir, 'phase3b_validation_report.json')
    with open(path, 'w') as handle:
        json.dump(report, handle, indent=2)
    return path


def vec(x, y, z):
    return unreal.Vector(x, y, z)


def distance(a, b):
    return (a - b).length()


def text_str(value):
    try:
        return str(value)
    except Exception as exc:
        return '<unprintable: {0}>'.format(exc)


def look_at_rotation(from_location, to_location):
    try:
        return unreal.MathLibrary.find_look_at_rotation(from_location, to_location)
    except Exception:
        pass
    try:
        return unreal.KismetMathLibrary.find_look_at_rotation(from_location, to_location)
    except Exception:
        pass
    delta = to_location - from_location
    xy = math.sqrt(delta.x * delta.x + delta.y * delta.y)
    yaw = math.degrees(math.atan2(delta.y, delta.x))
    pitch = math.degrees(math.atan2(delta.z, xy))
    return unreal.Rotator(pitch, yaw, 0.0)


def get_parent_class_name(asset_path):
    asset = unreal.EditorAssetLibrary.load_asset(asset_path)
    if not asset:
        return 'missing'
    try:
        parent = unreal.BlueprintEditorLibrary.get_blueprint_parent_class(asset)
        return parent.get_name() if parent else 'none'
    except Exception as exc:
        return '<error: {0}>'.format(exc)


def check_vehicle_anchors(vehicle):
    """B1: driver seat and exit point exist and sit in sensible places."""
    seat = vehicle.get_editor_property('driver_seat')
    exit_point = vehicle.get_editor_property('exit_point')
    if not seat or not exit_point:
        test('B1', 'vehicle has a driver seat and an exit point', False,
             'seat={0} exit={1}'.format(seat is not None, exit_point is not None))
        return None

    vehicle_location = vehicle.get_actor_location()
    seat_above = seat.get_world_location().z - vehicle_location.z
    exit_side = abs(exit_point.get_world_location().y - vehicle_location.y)
    test('B1', 'vehicle has a driver seat and an exit point',
         seat_above > 20.0 and exit_side > 120.0,
         'seat_z_offset={0:.0f}cm exit_side_offset={1:.0f}cm'.format(seat_above, exit_side))
    return seat


def check_boarding(character, vehicle, component):
    """B2-B4: interaction prompt, boarding, first person preserved."""
    board_text = text_str(vehicle.get_editor_property('board_prompt_text'))
    vehicle_location = vehicle.get_actor_location()

    # stand next to the vehicle and let the interaction component do the trace
    character.set_actor_location(vec(vehicle_location.x, vehicle_location.y - 200.0, 92.0), False, True)
    camera = character.get_editor_property('first_person_camera')
    character.set_actor_rotation(look_at_rotation(camera.get_world_location(), vehicle_location), False)
    component.refresh_focus()

    focused = component.get_focused_interactable()
    prompt = text_str(component.get_focused_prompt_text())
    test('B2', 'looking at the vehicle shows the board prompt',
         focused is not None and focused.get_name() == vehicle.get_name() and prompt == board_text,
         'focused={0} prompt="{1}" expected="{2}"'.format(
             focused.get_name() if focused else 'None', prompt, board_text))

    boarded = bool(character.enter_vehicle(vehicle))
    control_mode = character.get_control_mode()
    driving = control_mode == unreal.PlayerControlMode.DRIVING
    attached = character.get_attach_parent_actor()
    test('B3', 'boarding attaches the player to the vehicle (driving mode)',
         boarded and driving and attached is not None and attached.get_name() == vehicle.get_name(),
         'boarded={0} mode={1} attached={2}'.format(boarded, control_mode, attached.get_name() if attached else 'None'))

    seat = vehicle.get_editor_property('driver_seat')
    camera_location = camera.get_world_location()
    seat_location = seat.get_world_location()
    test('B4', 'first person camera is preserved at the driver seat',
         abs(camera_location.z - seat_location.z) <= 3.0,
         'camera_z={0:.1f} seat_z={1:.1f}'.format(camera_location.z, seat_location.z))
    return seat


def check_driving(character, vehicle):
    """B5-B8: the vehicle moves, the player travels with it, steering works."""
    start_vehicle = vehicle.get_actor_location()
    start_character = character.get_actor_location()
    start_yaw = vehicle.get_actor_rotation().yaw

    vehicle.set_drive_input(1.0, 0.0)
    for _ in range(4):
        vehicle.apply_drive_step(0.25)
    travelled = distance(vehicle.get_actor_location(), start_vehicle)
    test('B5', 'vehicle moves forward with throttle input', travelled > 100.0,
         'travelled={0:.1f}cm speed={1:.0f}cm/s'.format(travelled, vehicle.get_current_speed()))

    player_travel = distance(character.get_actor_location(), start_character)
    test('B6', 'player travels with the vehicle (still attached)',
         player_travel > 100.0 and character.get_attach_parent_actor() is not None,
         'player_travelled={0:.1f}cm'.format(player_travel))

    vehicle.set_drive_input(1.0, 1.0)
    for _ in range(4):
        vehicle.apply_drive_step(0.25)
    yaw_delta = abs(vehicle.get_actor_rotation().yaw - start_yaw)
    test('B7', 'steering input turns the vehicle', yaw_delta > 5.0,
         'yaw_delta={0:.1f}deg'.format(yaw_delta))

    exit_text = text_str(vehicle.get_editor_property('exit_prompt_text'))
    prompt = text_str(character.get_editor_property('interaction_component').get_focused_prompt_text())
    test('B8', 'while driving the prompt switches to the exit text', prompt == exit_text,
         'prompt="{0}" expected="{1}"'.format(prompt, exit_text))


def check_exit(character, vehicle):
    """B9-B10: leaving restores on-foot state and never traps the player."""
    vehicle.set_drive_input(0.0, 0.0)
    vehicle.stop_vehicle()

    exited = bool(character.exit_vehicle())
    control_mode = character.get_control_mode()
    on_foot = control_mode == unreal.PlayerControlMode.ON_FOOT
    attached = character.get_attach_parent_actor()
    capsule = character.get_editor_property('capsule_component')
    collision_enabled = capsule.get_editor_property('body_instance').get_editor_property('collision_enabled') \
        if capsule else None
    movement_mode = character.get_editor_property('character_movement').get_editor_property('movement_mode')
    walking = movement_mode == unreal.MovementMode.MOVE_WALKING

    test('B9', 'leaving the vehicle restores on-foot control',
         exited and on_foot and attached is None
         and collision_enabled == unreal.CollisionEnabled.QUERY_AND_PHYSICS and walking,
         'exited={0} mode={1} attached={2} collision={3} movement={4}'.format(
             exited, control_mode, attached is not None, collision_enabled, movement_mode))

    exit_distance = distance(character.get_actor_location(), vehicle.get_actor_location())
    character_location = character.get_actor_location()
    test('B10', 'player is placed outside the vehicle (not stuck inside)',
         exit_distance > 150.0 and character_location.z > 0.0,
         'distance_to_vehicle={0:.1f}cm player_z={1:.1f}'.format(exit_distance, character_location.z))


def check_phase3a_regression(character, spawned):
    """B11: the Phase 3A interaction slice still works."""
    camera = character.get_editor_property('first_person_camera')
    mesh = character.get_editor_property('mesh')
    owner_no_see = bool(mesh.get_editor_property('owner_no_see')) if mesh else False
    hidden_shadow = bool(mesh.get_editor_property('cast_hidden_shadow')) if mesh else False

    test_object_class = unreal.load_class(None, TEST_OBJECT_BP)
    if not test_object_class:
        test('B11', 'Phase 3A interaction slice still works (regression)', False, 'test object class missing')
        return

    # Regression check in a known free area of the map (far from the house block, the
    # garage, the trees and the level's own Phase 3A test object), independent of
    # where the driving test left the vehicle.
    spot = vec(-600.0, -600.0, 45.0)
    target = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).spawn_actor_from_class(
        test_object_class, spot)
    if not target:
        test('B11', 'Phase 3A interaction slice still works (regression)', False, 'could not spawn test object')
        return

    spawned.append(target)
    character.set_actor_location(vec(spot.x - 140.0, spot.y, spot.z + 75.0), False, True)
    camera_location = camera.get_world_location()
    character.set_actor_rotation(look_at_rotation(camera_location, spot), False)
    component = character.get_editor_property('interaction_component')
    component.set_forced_interactable(None)
    component.refresh_focus()
    focused = component.get_focused_interactable()
    focused_ok = focused is not None and focused.get_name() == target.get_name()
    returned = bool(component.try_interact())

    test('B11', 'Phase 3A interaction slice still works (regression)',
         owner_no_see and hidden_shadow and focused_ok and returned and target.is_activated(),
         'owner_no_see={0} hidden_shadow={1} focused={2} returned={3} activated={4} cam={5} target={6} dist={7:.0f}'.format(
             owner_no_see, hidden_shadow, focused_ok, returned, target.is_activated(),
             camera_location, spot, distance(camera_location, spot)))


def check_assets():
    """A1-A3: the vehicle asset exists, derives from C++ and is placed in the level."""
    test('A1', 'BP_VehicleBase exists and derives from the C++ VehicleBase',
         get_parent_class_name(VEHICLE_BP_PATH) == 'VehicleBase',
         'parent={0}'.format(get_parent_class_name(VEHICLE_BP_PATH)))

    test('A2', 'C++ AVehicleBase class is available',
         unreal.load_class(None, '/Script/MyProject.VehicleBase') is not None,
         'script class lookup')

    vehicle = None
    try:
        level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        level_subsystem.load_level(LEVEL_PATH)
        for actor in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
            if 'BP_VehicleBase' in actor.get_class().get_name():
                vehicle = actor
                break
    except Exception as exc:
        report['notes'].append('level load failed: {0}'.format(exc))

    test('A3', 'the level contains a BP_VehicleBase actor (placeholder car connected)',
         vehicle is not None,
         'actor={0}'.format(vehicle.get_name() if vehicle else 'not found'))
    return vehicle


def main():
    spawned = []
    vehicle = None
    vehicle_start_transform = None
    try:
        vehicle = check_assets()
        if not vehicle:
            return spawned

        # Remember the placed transform: the driving test moves the car, and the
        # level must stay exactly as it was (nothing is saved by this script).
        vehicle_start_transform = vehicle.get_actor_transform()

        check_vehicle_anchors(vehicle)

        player_class = unreal.load_class(None, PLAYER_BP)
        if not player_class:
            test('B0', 'BP_PlayerCharacter is available', False, 'class missing')
            return spawned

        character = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).spawn_actor_from_class(
            player_class, vec(0.0, 0.0, 120.0))
        if not character:
            test('B0', 'player character can be spawned', False, 'spawn failed')
            return spawned
        spawned.append(character)

        component = character.get_editor_property('interaction_component')
        test('B0', 'player character has the interaction component', component is not None,
             component.get_class().get_name() if component else 'missing')
        if not component:
            return spawned

        check_boarding(character, vehicle, component)
        check_driving(character, vehicle)
        check_exit(character, vehicle)
        check_phase3a_regression(character, spawned)
    except Exception as exc:
        report['notes'].append('exception: {0}'.format(exc))
        unreal.log_error('PHASE3B-VALIDATE: exception {0}'.format(exc))
    finally:
        # Restore the vehicle to where the level placed it, then remove the actors
        # this script spawned. The level is never saved by this script.
        if vehicle and vehicle_start_transform:
            try:
                vehicle.set_actor_transform(vehicle_start_transform, False, True)
                vehicle.stop_vehicle()
                vehicle.set_occupant(None)
            except Exception as exc:
                report['notes'].append('vehicle restore failed: {0}'.format(exc))

        for actor in spawned:
            try:
                unreal.get_editor_subsystem(unreal.EditorActorSubsystem).destroy_actor(actor)
            except Exception as exc:
                report['notes'].append('cleanup failed: {0}'.format(exc))
        report['cleaned_up'] = len(spawned)

        report['result'] = 'OK' if not report['failed'] else 'FAILED'
        path = write_report()
        passed = len([entry for entry in report['tests'] if entry['passed']])
        print('PHASE3B_VALIDATE_DONE ' + path)
        print('PHASE3B_VALIDATE_RESULT: {0} passed={1}/{2}'.format(
            report['result'], passed, len(report['tests'])))
        for problem in report['failed']:
            print('PHASE3B_VALIDATE_FAIL: ' + problem)


if __name__ == '__main__':
    main()
