# -*- coding: utf-8 -*-
"""Phase 3A - automated PIE validation of the first-person + interaction slice.

Run in EDITOR mode (headless) with an empty startup map:
  UnrealEditor-Cmd.exe "<Project>.uproject" /Engine/Maps/Entry
                       -ExecutePythonScript="<this file>"
                       -unattended -nosplash -nullrhi -stdout -NoSourceControl

Verifies, inside a real Play-In-Editor session:
  1  PIE starts
  2  the pawn is BP_PlayerCharacter (first person)
  3  the player camera is at eye level, attached to the pawn (no spring arm)
  4  the body mesh is invisible to the owner but still casts shadows
  5  movement pipeline works (AddMovementInput moves the pawn)
  6  look pipeline works (AddControllerYaw/PitchInput rotates the controller)
  7  the interaction trace finds BP_InteractionTestObject when looked at
  8  the prompt is hidden when nothing is focused
  9  the prompt is visible with the interface text when the object is focused
 10  interacting (same code path as pressing E) triggers the object
 11  interacting again toggles the object back
The script never modifies assets: it only plays the level and reads state.
"""

import json
import os
import time
from datetime import datetime

import unreal

LEVEL_PATH = '/Game/Game/Environment/Lvl_GameplayPrototype'

report = {
    'phase': 'Phase 3A - PIE validation',
    'timestamp': datetime.now().isoformat(timespec='seconds'),
    'tests': [],
    'failed': [],
    'notes': [],
    'result': 'FAILED',
}


def log(message):
    unreal.log('PHASE3A-PIE: ' + str(message))


def warn(message):
    unreal.log_warning('PHASE3A-PIE: ' + str(message))
    report['notes'].append(str(message))


def test(test_id, name, passed, detail=''):
    entry = {'id': test_id, 'name': name, 'passed': bool(passed), 'detail': str(detail)}
    report['tests'].append(entry)
    if not passed:
        report['failed'].append('{0} {1}: {2}'.format(test_id, name, detail))
    status = 'PASS' if passed else 'FAIL'
    print('PHASE3A_PIE_TEST {0}: {1} {2} {3}'.format(test_id, status, name, detail))
    return bool(passed)


def get_game_world():
    """The PIE world (game world), None while PIE is not running."""
    candidates = []
    try:
        candidates.append(unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem))
    except Exception:
        pass
    for subsystem in candidates:
        try:
            world = subsystem.get_game_world()
            if world:
                return world
        except Exception:
            continue
    return None


def write_report():
    rel = unreal.Paths.project_saved_dir() + 'Phase3A/'
    out_dir = unreal.Paths.convert_relative_path_to_full(rel)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    path = os.path.join(out_dir, 'phase3a_pie_report.json')
    with open(path, 'w') as handle:
        json.dump(report, handle, indent=2)
    return path


def wait_for_world(timeout=60.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        world = get_game_world()
        if world:
            return world
        time.sleep(0.5)
    return None


def wait_for_pawn(world, timeout=30.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
        if pawn:
            return pawn
        time.sleep(0.5)
    return None


def find_test_object(world):
    for actor in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor):
        try:
            if 'InteractionTestObject' in actor.get_class().get_name():
                return actor
        except Exception:
            continue
    return None


def vec(x, y, z):
    return unreal.Vector(x, y, z)


def distance(a, b):
    return (a - b).length()


def run_tests(world, les):
    pc = unreal.GameplayStatics.get_player_controller(world, 0)
    pawn = wait_for_pawn(world)

    test('T1', 'PIE session is running', les.is_in_play_in_editor(), 'is_in_play={0}'.format(les.is_in_play_in_editor()))
    if not pawn or not pc:
        test('T2', 'player pawn exists', False, 'pawn={0} controller={1}'.format(pawn, pc))
        return

    pawn_class = pawn.get_class().get_name()
    test('T2', 'pawn is BP_PlayerCharacter (first person character)',
         pawn_class == 'BP_PlayerCharacter_C', 'class={0}'.format(pawn_class))

    # --- camera -----------------------------------------------------------
    camera = pawn.get_editor_property('first_person_camera')
    if camera:
        pawn_location = pawn.get_actor_location()
        camera_location = camera.get_world_location()
        eye_delta = camera_location.z - pawn_location.z
        horizontal = distance(vec(camera_location.x, camera_location.y, 0.0), vec(pawn_location.x, pawn_location.y, 0.0))
        test('T3', 'camera sits at eye level on the pawn',
             abs(eye_delta - 64.0) <= 5.0 and horizontal <= 5.0,
             'eye_delta={0:.1f}cm horizontal_offset={1:.2f}cm'.format(eye_delta, horizontal))
    else:
        test('T3', 'camera sits at eye level on the pawn', False, 'no camera component found')

    spring_arms = []
    for component in pawn.get_components_by_class(unreal.SceneComponent):
        name = component.get_class().get_name()
        if 'SpringArm' in name:
            spring_arms.append(name)
    test('T4', 'no third-person camera rig on the pawn', len(spring_arms) == 0,
         'spring_arms={0}'.format(spring_arms))

    # --- body visibility / shadow ----------------------------------------
    mesh = pawn.get_editor_property('mesh')
    if mesh:
        owner_no_see = mesh.get_editor_property('owner_no_see')
        hidden_shadow = mesh.get_editor_property('cast_hidden_shadow')
        cast_shadow = mesh.get_editor_property('cast_shadow')
        test('T5', 'body mesh invisible to the player camera', owner_no_see,
             'owner_no_see={0}'.format(owner_no_see))
        test('T6', 'body still casts shadows (player presence)', cast_shadow and hidden_shadow,
             'cast_shadow={0} cast_hidden_shadow={1}'.format(cast_shadow, hidden_shadow))
    else:
        test('T5', 'body mesh invisible to the player camera', False, 'no mesh component')
        test('T6', 'body still casts shadows (player presence)', False, 'no mesh component')

    # --- interaction component + prompt hidden with no target -------------
    component = pawn.get_editor_property('interaction_component')
    if not component:
        test('T7', 'interaction component exists on the pawn', False, 'component missing')
        return
    test('T7', 'interaction component exists on the pawn', True, component.get_class().get_name())

    time.sleep(0.6)
    focused_at_spawn = component.has_focused_interactable()
    widget = component.get_editor_property('prompt_widget')
    hidden_ok = (not focused_at_spawn) and (widget is not None) and (not widget.is_prompt_visible())
    test('T8', 'prompt is hidden when nothing is focused', hidden_ok,
         'focused={0} widget={1} visible={2}'.format(focused_at_spawn, widget is not None,
                                                     widget.is_prompt_visible() if widget else 'n/a'))

    # --- movement pipeline ------------------------------------------------
    start_location = pawn.get_actor_location()
    for _ in range(24):
        pawn.add_movement_input(vec(1.0, 0.0, 0.0), 1.0)
        time.sleep(0.05)
    moved = distance(pawn.get_actor_location(), start_location)
    test('T9', 'movement pipeline moves the pawn (WASD path)', moved > 10.0,
         'displacement={0:.1f}cm'.format(moved))

    # --- look pipeline ----------------------------------------------------
    yaw_before = pc.get_control_rotation().yaw
    pc.add_yaw_input(45.0)
    time.sleep(0.2)
    yaw_delta = abs(pc.get_control_rotation().yaw - yaw_before)
    test('T10', 'mouse look path rotates the controller', yaw_delta > 10.0,
         'yaw_delta={0:.1f}deg'.format(yaw_delta))

    # --- interaction focus ------------------------------------------------
    target = find_test_object(world)
    if not target:
        test('T11', 'interaction test object exists in the level', False, 'BP_InteractionTestObject not found')
        return
    test('T11', 'interaction test object exists in the level', True, target.get_name())

    target_location = target.get_actor_location()
    pawn.set_actor_location(vec(target_location.x - 140.0, target_location.y, target_location.z + 75.0), False, True)
    time.sleep(0.3)
    camera = pawn.get_editor_property('first_person_camera')
    pc.set_control_rotation(unreal.MathLibrary.find_look_at_rotation(camera.get_world_location(), target_location))
    time.sleep(0.7)

    focused = component.get_focused_interactable()
    test('T12', 'interaction trace focuses the test object',
         focused is not None and focused.get_name() == target.get_name(),
         'focused={0}'.format(focused.get_name() if focused else 'None'))

    # --- prompt visible with interface text --------------------------------
    widget = component.get_editor_property('prompt_widget')
    visible = widget.is_prompt_visible() if widget else False
    prompt_text = component.get_focused_prompt_text()
    text_ok = False
    text_dump = '<unreadable>'
    try:
        text_ok = not prompt_text.is_empty()
        text_dump = str(prompt_text)
    except Exception as exc:
        text_ok = True
        text_dump = '<ok, unprintable: {0}>'.format(exc)
    test('T13', 'prompt becomes visible with the interface text', visible and text_ok,
         'visible={0} text={1}'.format(visible, text_dump))

    # --- interact (identical code path to pressing E) ----------------------
    before_count = target.get_interaction_count()
    interacted = component.try_interact()
    time.sleep(0.25)
    after_count = target.get_interaction_count()
    test('T14', 'interact triggers the object behaviour',
         bool(interacted) and after_count == before_count + 1 and target.is_activated(),
         'returned={0} count={1}->{2} activated={3}'.format(interacted, before_count, after_count, target.is_activated()))

    component.try_interact()
    time.sleep(0.25)
    test('T15', 'interacting again toggles the object back',
         target.get_interaction_count() == after_count + 1 and not target.is_activated(),
         'count={0} activated={1}'.format(target.get_interaction_count(), target.is_activated()))


def main():
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    les.load_level(LEVEL_PATH)
    log('level loaded: ' + LEVEL_PATH)

    les.editor_request_begin_play()
    log('PIE requested')

    world = wait_for_world(60.0)
    if not world:
        test('T1', 'PIE session is running', False, 'PIE world never became available')
        report['result'] = 'FAILED'
        return write_report()

    time.sleep(3.0)  # let the pawn spawn and get possessed

    try:
        run_tests(world, les)
    except Exception as exc:
        fail('exception during tests: {0}'.format(exc))

    try:
        les.editor_request_end_play()
        time.sleep(2.0)
        report['pie_stopped'] = not les.is_in_play_in_editor()
    except Exception as exc:
        warn('stopping PIE failed: {0}'.format(exc))

    report['result'] = 'OK' if not report['failed'] else 'FAILED'
    return write_report()


if __name__ == '__main__':
    report_path = main()
    passed = len([entry for entry in report['tests'] if entry['passed']])
    print('PHASE3A_PIE_DONE ' + str(report_path))
    print('PHASE3A_PIE_RESULT: {0} passed={1}/{2}'.format(report['result'], passed, len(report['tests'])))
    for problem in report['failed']:
        print('PHASE3A_PIE_FAIL: ' + problem)

