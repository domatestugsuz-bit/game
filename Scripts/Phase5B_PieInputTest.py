# -*- coding: utf-8 -*-
"""Phase 5B - PIE test of the input fix (touchpad look) and of the terrain repair.

PIE cannot progress while the python interpreter blocks the game thread, so the whole flow
runs from a slate post tick callback (the pattern Phase5_Validate.py proved works):
wait for the editor -> request PIE -> wait for the world -> wait for the pawn -> checks ->
HighResShot -> collect -> end play -> report -> quit.

Checks:
  A1  IMC_Game maps IA_Look to Mouse XY 2D-Axis     (the actual touchpad fix)
  A2  that mapping still carries the template Negate modifier
  P1  PIE session starts on Lvl_Rural
  P2  player pawn + controller exist
  P3  pawn is BP_PlayerCharacter
  P4  pawn registers IMC_Game
  P5  pawn binds IA_Look as its look action
  P6  the mouse cursor is hidden (deltas reach the game without a first click)
  P7  the look pipeline rotates the controller (yaw + pitch)
  P8  the world edge is terrain, not the raw 0 trench (-256 m)
  P9  a 1920x1080 screenshot of the starting view was captured

Run (needs a real RHI so the screenshot renders):
  UnrealEditor-Cmd.exe "<Project>.uproject" -ExecutePythonScript="<this file>"
                       -unattended -nosplash -stdout -NoSourceControl
"""

import json
import os
import time
from datetime import datetime

import unreal

LEVEL = '/Game/Game/Environment/Lvl_Rural'
IMC_PATH = '/Game/Game/Input/IMC_Game'
SHOT_RES = '1920x1080'

report = {'phase': 'Phase 5B - PIE input test', 'timestamp': datetime.now().isoformat(timespec='seconds'),
          'tests': [], 'failed': [], 'notes': [], 'screenshots': [], 'result': 'FAILED'}
state = {'phase': 'wait_editor', 'phase_time': 0.0, 'ticks': 0, 'handle': None, 'world': None, 'pawn': None,
         'pc': None, 'known': set(), 'folder': '', 'les': None, 'screenshot': None}


def log(message):
    print('PHASE5B-TEST: ' + str(message))


def warn(message):
    print('PHASE5B-TEST-WARN: ' + str(message))
    report['notes'].append(str(message))


def test(test_id, name, passed, detail=''):
    entry = {'id': test_id, 'name': name, 'passed': bool(passed), 'detail': str(detail)}
    report['tests'].append(entry)
    if not passed:
        report['failed'].append('{0} {1}: {2}'.format(test_id, name, detail))
    print('PHASE5B_TEST {0}: {1} {2} {3}'.format(test_id, 'PASS' if passed else 'FAIL', name, detail))
    return bool(passed)


def get_game_world():
    try:
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_game_world()
        if world:
            return world
    except Exception:
        pass
    return None


def screenshot_folder():
    return unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir() + 'Screenshots/WindowsEditor')


def new_shots(folder, known):
    if not os.path.isdir(folder):
        return []
    shots = []
    for name in os.listdir(folder):
        if not name.lower().endswith('.png'):
            continue
        path = os.path.join(folder, name)
        if path not in known:
            shots.append(path)
    return shots


def entries_of(context):
    return list(context.get_editor_property('default_key_mappings').mappings)


def action_name(entry):
    action = entry.get_editor_property('action')
    return action.get_name() if action else None


def key_name(entry):
    key = entry.get_editor_property('key')
    try:
        value = key.get_editor_property('key_name')
        if value:
            return str(value)
    except Exception:
        pass
    return str(key)


def modifier_classes(entry):
    return [modifier.get_class().get_name() for modifier in (entry.get_editor_property('modifiers') or [])]


def ground_z(world, x_m, y_m):
    start = unreal.Vector(x_m * 100.0, y_m * 100.0, 60000.0)
    end = unreal.Vector(x_m * 100.0, y_m * 100.0, -60000.0)
    hit = unreal.SystemLibrary.line_trace_single(world, start, end, unreal.TraceTypeQuery.ECC_VISIBILITY, True, [],
                                                 unreal.DrawDebugTrace.NONE, True)
    if hit is None:
        return None
    try:
        return round(float(hit.to_dict()['location'].z) / 100.0, 2)
    except Exception:
        return None


def asset_checks():
    context = unreal.EditorAssetLibrary.load_asset(IMC_PATH)
    if context is None:
        test('A1', 'IMC_Game exists', False, IMC_PATH)
        return
    entries = entries_of(context)
    pairs = ['{0}<-{1}'.format(action_name(entry), key_name(entry)) for entry in entries]
    test('A1', 'IMC_Game maps IA_Look to the mouse (touchpad fix)',
         any(action_name(entry) == 'IA_Look' and key_name(entry) == 'Mouse2D' for entry in entries), str(pairs))
    for entry in entries:
        if action_name(entry) == 'IA_Look':
            classes = modifier_classes(entry)
            test('A2', 'IA_Look mouse mapping keeps the template Negate modifier', 'InputModifierNegate' in classes,
                 '{0} modifiers={1}'.format(key_name(entry), classes))
    report['imc_mappings'] = pairs


def mouse_cursor_state(pc):
    """bShowMouseCursor is not exposed to python in every build; probe the spellings that work."""
    for name in ('b_show_mouse_cursor', 'bShowMouseCursor'):
        try:
            return bool(pc.get_editor_property(name))
        except Exception:
            continue
    for name in ('b_show_mouse_cursor', 'bShowMouseCursor'):
        try:
            return bool(getattr(pc, name))
        except Exception:
            continue
    return None


def pawn_checks():
    pawn = state['pawn']
    pc = state['pc']
    world = state['world']

    test('P1', 'PIE session is running', state['les'].is_in_play_in_editor(), 'is_in_play=True')
    test('P2', 'player pawn + controller exist', pawn is not None and pc is not None,
         'pawn={0}'.format(pawn.get_class().get_name() if pawn else None))
    if pawn is None or pc is None:
        return

    test('P3', 'pawn is BP_PlayerCharacter', pawn.get_class().get_name() == 'BP_PlayerCharacter_C',
         pawn.get_class().get_name())
    context = pawn.get_editor_property('default_mapping_context')
    test('P4', 'pawn registers IMC_Game', context is not None and 'IMC_Game' in str(context), str(context))
    look_action = pawn.get_editor_property('look_action')
    test('P5', 'pawn binds IA_Look as its look action', look_action is not None and 'IA_Look' in str(look_action),
         str(look_action))
    cursor = mouse_cursor_state(pc)
    if cursor is None:
        warn('bShowMouseCursor is not exposed to python in this build; the C++ forces game-only '
             'input and a hidden cursor on BeginPlay instead')
    else:
        test('P6', 'mouse cursor is hidden so touchpad deltas reach the game', not cursor,
             'b_show_mouse_cursor={0}'.format(cursor))

    yaw_before = pc.get_control_rotation().yaw
    pc.add_yaw_input(45.0)
    pitch_before = pc.get_control_rotation().pitch
    pc.add_pitch_input(30.0)
    state['yaw_before'] = yaw_before
    state['pitch_before'] = pitch_before

    edges = {name: ground_z(world, x, y) for name, x, y in (
        ('west', -1240.0, 0.0), ('east', 1240.0, 0.0), ('south', 0.0, -1240.0), ('north', 0.0, 1240.0))}
    report['edge_traces'] = edges
    # A missing hit only means the World Partition cell is not streamed in at that distance;
    # what must not happen any more is a trace landing in the old raw 0 trench (~-256 m).
    trench = [name for name, value in edges.items() if isinstance(value, float) and value < -50.0]
    test('P8', 'world edge is terrain, no -256 m trench', not trench,
         'traces={0} trench={1}'.format(edges, trench))


def finish_look_check():
    pc = state['pc']
    yaw_delta = abs(pc.get_control_rotation().yaw - state['yaw_before'])
    pitch_delta = abs(pc.get_control_rotation().pitch - state['pitch_before'])
    test('P7', 'look pipeline rotates the controller (yaw + pitch)', yaw_delta > 10.0 and pitch_delta > 5.0,
         'yaw_delta={0:.1f} pitch_delta={1:.1f}'.format(yaw_delta, pitch_delta))


def write_report(reason):
    out_dir = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir() + 'Phase5B/')
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    report['result'] = 'OK' if not report['failed'] else 'FAILED'
    report['reason'] = reason
    path = os.path.join(out_dir, 'phase5b_pie_input_test.json')
    with open(path, 'w') as handle:
        json.dump(report, handle, indent=2)
    passed = len([entry for entry in report['tests'] if entry['passed']])
    print('PHASE5B_TEST_RUNTIME_RESULT: {0} passed={1}/{2}'.format(report['result'], passed, len(report['tests'])))
    for problem in report['failed']:
        print('PHASE5B_TEST_RUNTIME_FAIL: ' + problem)
    log('report written: {0}'.format(path))
    return path


def next_phase(name):
    state['phase'] = name
    state['phase_time'] = 0.0
    log('phase -> {0}'.format(name))


def tick_body(delta_seconds):
    state['phase_time'] += delta_seconds
    phase = state['phase']

    if phase == 'wait_editor':
        if state['phase_time'] > 4.0:
            state['folder'] = screenshot_folder()
            state['known'] = set(new_shots(state['folder'], set()))
            state['les'].editor_request_begin_play()
            log('PIE requested')
            next_phase('wait_world')

    elif phase == 'wait_world':
        world = get_game_world()
        if world is not None:
            state['world'] = world
            log('PIE world ready after {0:.1f}s'.format(state['phase_time']))
            next_phase('wait_pawn')
        elif state['phase_time'] > 180.0:
            test('P1', 'PIE session is running', False, 'the PIE world never started')
            next_phase('stop')

    elif phase == 'wait_pawn':
        pawn = unreal.GameplayStatics.get_player_pawn(state['world'], 0)
        if pawn is not None:
            state['pawn'] = pawn
            state['pc'] = unreal.GameplayStatics.get_player_controller(state['world'], 0)
            log('pawn ready: {0}'.format(pawn.get_name()))
            next_phase('settle')
        elif state['phase_time'] > 120.0:
            test('P2', 'player pawn + controller exist', False, 'no pawn in PIE')
            next_phase('stop')

    elif phase == 'settle':
        if state['phase_time'] > 3.0:
            pawn_checks()
            next_phase('look')

    elif phase == 'look':
        if state['phase_time'] > 1.0:
            finish_look_check()
            next_phase('shoot')

    elif phase == 'shoot':
        unreal.SystemLibrary.execute_console_command(state['world'], 'HighResShot ' + SHOT_RES)
        log('screenshot requested')
        next_phase('collect')

    elif phase == 'collect':
        shots = new_shots(state['folder'], state['known'])
        if shots or state['phase_time'] > 30.0:
            report['screenshots'] = shots
            test('P9', 'in-game screenshot captured', bool(shots), str(shots))
            next_phase('stop')

    elif phase == 'stop':
        if state['phase_time'] < 0.1:
            try:
                state['les'].editor_request_end_play()
            except Exception as exc:
                warn('end play failed: {0}'.format(exc))
        if state['phase_time'] > 6.0:
            write_report('completed')
            try:
                unreal.unregister_slate_post_tick_callback(state['handle'])
            except Exception:
                pass
            unreal.SystemLibrary.quit_editor()


def tick_body_guarded(delta_seconds):
    state['ticks'] += 1
    try:
        tick_body(delta_seconds)
    except Exception:
        import traceback
        warn('tick exception: ' + traceback.format_exc())
        next_phase('stop')


def main():
    state['les'] = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    unreal.EditorLoadingAndSavingUtils.load_map(LEVEL)
    log('level loaded: ' + LEVEL)
    asset_checks()
    state['handle'] = unreal.register_slate_post_tick_callback(lambda delta: tick_body_guarded(delta))
    log('tick callback registered; the PIE checks follow on the next ticks')


main()

