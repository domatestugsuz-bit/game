# -*- coding: utf-8 -*-
"""Phase 3A - tick-driven PIE validation (no blocking sleeps).

Blocking the game thread with time.sleep() prevents the editor from processing the
Play-In-Editor request, so this version drives every step from a slate post-tick
callback: request PIE, wait for the world/pawn, then run each check across ticks.

Run (headless):
  UnrealEditor-Cmd.exe "<Project>.uproject" /Engine/Maps/Entry
                       -ExecutePythonScript="<this file>"
                       -unattended -nosplash -nullrhi -stdout -NoSourceControl
"""

import json
import os
import time
from datetime import datetime

import unreal

LEVEL_PATH = '/Game/Game/Environment/Lvl_GameplayPrototype'

report = {
    'phase': 'Phase 3A - PIE validation (tick driven)',
    'timestamp': datetime.now().isoformat(timespec='seconds'),
    'tests': [],
    'failed': [],
    'notes': [],
    'result': 'FAILED',
}

state = {
    'phase': 'request',
    'ticks': 0,
    'time': 0.0,
    'phase_time': 0.0,
    'handle': None,
    'world': None,
    'pawn': None,
    'component': None,
    'widget': None,
    'target': None,
    'les': None,
    'move_start': None,
    'yaw_before': 0.0,
    'count_before': 0,
    'count_after_first': 0,
    'focus_seen': False,
}


def log(message):
    unreal.log('PHASE3A-PIE: ' + str(message))


def warn(message):
    unreal.log_warning('PHASE3A-PIE: ' + str(message))
    report['notes'].append(str(message))


def fail(message):
    unreal.log_error('PHASE3A-PIE: ' + str(message))
    report['failed'].append(str(message))


def test(test_id, name, passed, detail=''):
    entry = {'id': test_id, 'name': name, 'passed': bool(passed), 'detail': str(detail)}
    report['tests'].append(entry)
    if not passed:
        report['failed'].append('{0} {1}: {2}'.format(test_id, name, detail))
    unreal.log('PHASE3A_PIE_TEST {0}: {1} {2} :: {3}'.format(test_id, 'PASS' if passed else 'FAIL', name, detail))
    return bool(passed)


def write_report():
    rel = unreal.Paths.project_saved_dir() + 'Phase3A/'
    out_dir = unreal.Paths.convert_relative_path_to_full(rel)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    path = os.path.join(out_dir, 'phase3a_pie_report.json')
    with open(path, 'w') as handle:
        json.dump(report, handle, indent=2)
    return path


def get_game_world():
    try:
        return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_game_world()
    except Exception:
        return None


def vec(x, y, z):
    return unreal.Vector(x, y, z)


def distance(a, b):
    return (a - b).length()


def find_test_object(world):
    for actor in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor):
        try:
            if 'InteractionTestObject' in actor.get_class().get_name():
                return actor
        except Exception:
            continue
    return None


def check_pawn_and_camera():
    """T1-T7: checks that need no waiting once the pawn exists."""
    les = state['les']
    pawn = state['pawn']

    test('T1', 'PIE session is running', les.is_in_play_in_editor(),
         'is_in_play={0}'.format(les.is_in_play_in_editor()))

    pawn_class = pawn.get_class().get_name()
    test('T2', 'pawn is BP_PlayerCharacter (first person character)',
         pawn_class == 'BP_PlayerCharacter_C', 'class=' + pawn_class)

    camera = pawn.get_editor_property('first_person_camera')
    if camera:
        pawn_location = pawn.get_actor_location()
        camera_location = camera.get_world_location()
        eye_delta = camera_location.z - pawn_location.z
        horizontal = distance(vec(camera_location.x, camera_location.y, 0.0),
                              vec(pawn_location.x, pawn_location.y, 0.0))
        test('T3', 'camera is at eye level on the pawn',
             abs(eye_delta - 64.0) <= 5.0 and horizontal <= 5.0,
             'eye_delta={0:.1f}cm horizontal={1:.2f}cm'.format(eye_delta, horizontal))
    else:
        test('T3', 'camera is at eye level on the pawn', False, 'no camera component')

    spring_arms = []
    for component in pawn.get_components_by_class(unreal.SceneComponent):
        if 'SpringArm' in component.get_class().get_name():
            spring_arms.append(component.get_class().get_name())
    test('T4', 'no third-person rig / spring arm on the pawn', len(spring_arms) == 0,
         'spring_arms={0}'.format(spring_arms))

    mesh = pawn.get_editor_property('mesh')
    if mesh:
        owner_no_see = bool(mesh.get_editor_property('owner_no_see'))
        hidden_shadow = bool(mesh.get_editor_property('cast_hidden_shadow'))
        cast_shadow = bool(mesh.get_editor_property('cast_shadow'))
        test('T5', 'body mesh is invisible to the player camera', owner_no_see,
             'owner_no_see={0}'.format(owner_no_see))
        test('T6', 'body still casts shadows (player presence)', cast_shadow and hidden_shadow,
             'cast_shadow={0} cast_hidden_shadow={1}'.format(cast_shadow, hidden_shadow))
    else:
        test('T5', 'body mesh is invisible to the player camera', False, 'no mesh component')
        test('T6', 'body still casts shadows (player presence)', False, 'no mesh component')

    component = pawn.get_editor_property('interaction_component')
    state['component'] = component
    test('T7', 'interaction component exists on the pawn', component is not None,
         component.get_class().get_name() if component else 'missing')
    return component is not None


def check_prompt_hidden():
    """T8: nothing in range -> the widget exists but stays hidden."""
    component = state['component']
    widget = component.get_editor_property('prompt_widget')
    state['widget'] = widget
    focused = component.has_focused_interactable()
    visible = widget.is_prompt_visible() if widget else False
    test('T8', 'prompt is hidden while nothing is focused',
         (not focused) and (widget is not None) and (not visible),
         'focused={0} widget_created={1} visible={2}'.format(focused, widget is not None, visible))


def start_move():
    state['move_start'] = state['pawn'].get_actor_location()


def hold_move():
    state['pawn'].add_movement_input(vec(1.0, 0.0, 0.0), 1.0)


def check_move():
    moved = distance(state['pawn'].get_actor_location(), state['move_start'])
    test('T9', 'movement pipeline moves the pawn (WASD path)', moved > 10.0,
         'displacement={0:.1f}cm'.format(moved))


def start_look():
    controller = unreal.GameplayStatics.get_player_controller(state['world'], 0)
    state['yaw_before'] = controller.get_control_rotation().yaw


def do_look():
    unreal.GameplayStatics.get_player_controller(state['world'], 0).add_yaw_input(45.0)


def check_look():
    controller = unreal.GameplayStatics.get_player_controller(state['world'], 0)
    delta = abs(controller.get_control_rotation().yaw - state['yaw_before'])
    test('T10', 'mouse look path rotates the controller', delta > 10.0,
         'yaw_delta={0:.1f}deg'.format(delta))


def aim_at_target():
    pawn = state['pawn']
    target_location = state['target'].get_actor_location()
    pawn.set_actor_location(vec(target_location.x - 140.0, target_location.y, target_location.z + 75.0), False, True)
    camera = pawn.get_editor_property('first_person_camera')
    controller = unreal.GameplayStatics.get_player_controller(state['world'], 0)
    controller.set_control_rotation(
        unreal.MathLibrary.find_look_at_rotation(camera.get_world_location(), target_location))


def check_focus():
    component = state['component']
    target = state['target']
    focused = component.get_focused_interactable()
    ok = focused is not None and focused.get_name() == target.get_name()
    test('T11', 'interaction trace focuses the test object', ok,
         'focused={0}'.format(focused.get_name() if focused else 'None'))


def check_prompt_visible():
    component = state['component']
    widget = state['widget']
    visible = widget.is_prompt_visible() if widget else False
    text = component.get_focused_prompt_text()
    text_ok = False
    dump = '<n/a>'
    try:
        text_ok = not text.is_empty()
        dump = str(text)
    except Exception as exc:
        text_ok = True
        dump = '<unprintable: {0}>'.format(exc)
    test('T12', 'prompt becomes visible with the interface text', visible and text_ok,
         'visible={0} text={1}'.format(visible, dump))


def interact_first():
    state['count_before'] = state['target'].get_interaction_count()
    state['interact_returned'] = bool(state['component'].try_interact())


def check_interact_first():
    target = state['target']
    after = target.get_interaction_count()
    state['count_after_first'] = after
    test('T13', 'interact triggers the object behaviour',
         state['interact_returned'] and after == state['count_before'] + 1 and target.is_activated(),
         'returned={0} count={1}->{2} activated={3}'.format(
             state['interact_returned'], state['count_before'], after, target.is_activated()))


def interact_second():
    state['component'].try_interact()


def check_interact_second():
    target = state['target']
    after = target.get_interaction_count()
    test('T14', 'interacting again toggles the object back',
         after == state['count_after_first'] + 1 and not target.is_activated(),
         'count={0} activated={1}'.format(after, target.is_activated()))


def next_phase(phase):
    state['phase'] = phase
    state['phase_time'] = 0.0


def on_tick(delta_seconds):
    state['ticks'] += 1
    state['time'] += delta_seconds
    state['phase_time'] += delta_seconds
    phase = state['phase']

    if phase == 'request':
        state['les'].editor_request_begin_play()
        log('PIE requested at tick {0}'.format(state['ticks']))
        next_phase('wait_world')

    elif phase == 'wait_world':
        world = get_game_world()
        if world:
            state['world'] = world
            log('PIE world ready after {0:.1f}s'.format(state['phase_time']))
            next_phase('wait_pawn')
        elif state['phase_time'] > 90.0:
            test('T1', 'PIE session is running', False, 'PIE world never became available')
            finish('timeout waiting for the PIE world')

    elif phase == 'wait_pawn':
        pawn = unreal.GameplayStatics.get_player_pawn(state['world'], 0)
        if pawn:
            state['pawn'] = pawn
            next_phase('settle')
        elif state['phase_time'] > 10.0:
            fail('player pawn never spawned')
            finish('timeout waiting for the pawn')

    elif phase == 'settle':
        if state['phase_time'] >= 1.0:
            if check_pawn_and_camera():
                next_phase('prompt_hidden')
            else:
                finish('no interaction component on the pawn')

    elif phase == 'prompt_hidden':
        if state['phase_time'] >= 0.6:
            check_prompt_hidden()
            next_phase('move_start')

    elif phase == 'move_start':
        start_move()
        next_phase('move_hold')

    elif phase == 'move_hold':
        hold_move()
        if state['phase_time'] >= 1.2:
            next_phase('move_check')

    elif phase == 'move_check':
        check_move()
        start_look()
        next_phase('look_do')

    elif phase == 'look_do':
        do_look()
        next_phase('look_check')

    elif phase == 'look_check':
        if state['phase_time'] >= 0.3:
            check_look()
            state['target'] = find_test_object(state['world'])
            if state['target'] is None:
                test('T11', 'interaction test object exists in the level', False, 'not found in the PIE world')
                finish('no test object in the level')
            else:
                aim_at_target()
                next_phase('focus_wait')

    elif phase == 'focus_wait':
        if state['phase_time'] >= 0.8:
            check_focus()
            check_prompt_visible()
            next_phase('interact_first')

    elif phase == 'interact_first':
        interact_first()
        next_phase('interact_first_wait')

    elif phase == 'interact_first_wait':
        if state['phase_time'] >= 0.4:
            check_interact_first()
            next_phase('interact_second')

    elif phase == 'interact_second':
        interact_second()
        next_phase('interact_second_wait')

    elif phase == 'interact_second_wait':
        if state['phase_time'] >= 0.4:
            check_interact_second()
            finish('all checks completed')


def main():
    state['les'] = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    state['les'].load_level(LEVEL_PATH)
    log('level loaded: ' + LEVEL_PATH)
    state['handle'] = unreal.register_slate_post_tick_callback(on_tick)
    log('tick callback registered - PIE is requested on the first tick')


def finish(reason=''):
    """Stops PIE, writes the report and ends the editor session."""
    les = state['les']
    try:
        if les and les.is_in_play_in_editor():
            les.editor_request_end_play()
    except Exception as exc:
        warn('end play failed: {0}'.format(exc))

    report['result'] = 'OK' if not report['failed'] else 'FAILED'
    report['ticks'] = state['ticks']
    path = write_report()
    log('report -> {0} ({1})'.format(path, reason))
    try:
        if state['handle'] is not None:
            unreal.unregister_slate_post_tick_callback(state['handle'])
    except Exception:
        pass
    unreal.SystemLibrary.quit_editor()


if __name__ == '__main__':
    main()
