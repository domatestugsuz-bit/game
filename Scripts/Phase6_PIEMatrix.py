# -*- coding: utf-8 -*-
"""Phase 6 - PIE performance matrix A-G.

PIE cannot progress while python blocks the game thread, so the whole run is a slate post tick
state machine (the pattern Phase5_Validate.py proved works, launched with -ExecCmds).

Seven configurations, all measured from the same camera position (forest edge of the home
property, which is the heaviest view: forest + house + landscape material in frame):

    A  LOW            sg.QualityLevel 0
    B  MEDIUM         sg.QualityLevel 1
    C  HIGH           sg.QualityLevel 2
    D  ULTRA          sg.QualityLevel 3
    E  ULTRA, Nanite off             (r.Nanite 0)
    F  ULTRA, virtual shadow maps off (r.Shadow.Virtual.Enable 0)
    G  ULTRA, Lumen off               (r.Lumen.DiffuseIndirect.Allow 0)

NOTE: the project has no written A-G definition, so the mapping above is this pass's own
choice: A-D are the four quality profiles of Config/DefaultScalability.ini and E-G switch off
one expensive feature each so its cost can be read off the table.
"""

import json
import os
from datetime import datetime

import unreal

LEVEL = '/Game/Game/Environment/Lvl_Rural'
OUT_DIR = 'C:/Users/azize/OneDrive/Belgeler/Unreal Projects/MyProject/Saved/Phase6'
SHOT_RES = '1920x1080'
SETTLE_FRAMES = 90
MEASURE_FRAMES = 120
VIEW_LOCATION_M = (690.0, 640.0)
VIEW_YAW = 305.0

MATRIX = [
    ('A', 'LOW', ['sg.QualityLevel 0']),
    ('B', 'MEDIUM', ['sg.QualityLevel 1']),
    ('C', 'HIGH', ['sg.QualityLevel 2']),
    ('D', 'ULTRA', ['sg.QualityLevel 3']),
    ('E', 'ULTRA + Nanite off', ['sg.QualityLevel 3', 'r.Nanite 0']),
    ('F', 'ULTRA + VSM off', ['sg.QualityLevel 3', 'r.Shadow.Virtual.Enable 0']),
    ('G', 'ULTRA + Lumen off', ['sg.QualityLevel 3', 'r.Lumen.DiffuseIndirect.Allow 0']),
]

# Without these the project VSyncs at 60 fps and every row reads 16.8 ms, which hides the
# real cost of each configuration.
PRELUDE = ['r.VSync 0', 't.MaxFPS 0', 'r.FinishCurrentFrame 0']

report = {'phase': 'Phase 6 - PIE performance matrix A-G', 'timestamp': datetime.now().isoformat(timespec='seconds'),
          'definition_note': 'A-D = the LOW/MEDIUM/HIGH/ULTRA profiles, E-G = ULTRA with one feature off',
          'view': {'location_m': list(VIEW_LOCATION_M), 'yaw': VIEW_YAW},
          'rows': [], 'screenshots': [], 'notes': [], 'result': 'FAILED'}

state = {'phase': 'wait_editor', 'phase_time': 0.0, 'index': 0, 'frames': 0, 'phase_frame': 0, 't0': None,
         'les': None, 'world': None, 'pawn': None, 'pc': None, 'handle': None, 'shot_sent': False,
         'folder': ''}


def log(message):
    print('PHASE6-MATRIX: ' + str(message))


def get_game_world():
    try:
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_game_world()
        if world:
            return world
    except Exception:
        pass
    return None


def next_phase(name):
    state['phase'] = name
    state['phase_time'] = 0.0
    state['phase_frame'] = 0
    log('phase -> {0}'.format(name))


def place_view():
    pawn = state['pawn']
    pc = state['pc']
    x, y = VIEW_LOCATION_M
    loc = unreal.Vector(x * 100.0, y * 100.0, pawn.get_actor_location().z)
    try:
        pawn.set_actor_location(loc, False, False)
    except Exception:
        try:
            pawn.set_actor_location(loc, False, True)
        except Exception as exc:
            report['notes'].append('teleport failed: {0}'.format(exc))
    pc.set_control_rotation(unreal.Rotator(0.0, VIEW_YAW, 0.0))


def apply_config(entry):
    for command in PRELUDE + list(entry[2]):
        unreal.SystemLibrary.execute_console_command(state['world'], command)
    log('{0} ({1}): {2}'.format(entry[0], entry[1], '; '.join(entry[2])))


def measure_start():
    try:
        state['t0'] = unreal.GameplayStatics.get_time_seconds(state['world'])
    except Exception:
        state['t0'] = None


def measure_end():
    try:
        t1 = unreal.GameplayStatics.get_time_seconds(state['world'])
    except Exception:
        t1 = None
    if state['t0'] is None or t1 is None or t1 <= state['t0']:
        return None
    return round((t1 - state['t0']) * 1000.0 / MEASURE_FRAMES, 2)


def screenshot_folder():
    return unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir() + 'Screenshots/WindowsEditor')


def tick_body(delta_seconds):
    state['phase_time'] += delta_seconds
    state['frames'] += 1
    state['phase_frame'] += 1
    phase = state['phase']

    if phase == 'wait_editor':
        if state['phase_time'] > 4.0:
            state['folder'] = screenshot_folder()
            state['les'].editor_request_begin_play()
            log('PIE requested')
            next_phase('wait_world')

    elif phase == 'wait_world':
        world = get_game_world()
        if world is not None:
            state['world'] = world
            next_phase('wait_pawn')
        elif state['phase_time'] > 180.0:
            report['notes'].append('PIE world never started')
            next_phase('stop')

    elif phase == 'wait_pawn':
        pawn = unreal.GameplayStatics.get_player_pawn(state['world'], 0)
        if pawn is not None:
            state['pawn'] = pawn
            state['pc'] = unreal.GameplayStatics.get_player_controller(state['world'], 0)
            next_phase('config')
        elif state['phase_time'] > 120.0:
            report['notes'].append('no pawn in PIE')
            next_phase('stop')

    elif phase == 'config':
        if state['index'] >= len(MATRIX):
            next_phase('stop')
            return
        apply_config(MATRIX[state['index']])
        place_view()
        next_phase('settle')

    elif phase == 'settle':
        place_view()
        if state['phase_frame'] > SETTLE_FRAMES:
            measure_start()
            next_phase('measure')

    elif phase == 'measure':
        if state['phase_frame'] > MEASURE_FRAMES:
            elapsed = measure_end()
            entry = MATRIX[state['index']]
            report['rows'].append({'id': entry[0], 'name': entry[1], 'commands': entry[2],
                                   'avg_frame_ms': elapsed,
                                   'fps': round(1000.0 / elapsed, 1) if elapsed else None})
            log('{0} ({1}): {2} ms'.format(entry[0], entry[1], elapsed))
            state['shot_sent'] = False
            next_phase('shot')

    elif phase == 'shot':
        # one screenshot for LOW and one for ULTRA so the landscape material can be judged by
        # eye as well as by number
        wanted = MATRIX[state['index']][0] in ('A', 'D')
        if wanted and not state['shot_sent']:
            place_view()
            unreal.SystemLibrary.execute_console_command(state['world'], 'HighResShot ' + SHOT_RES)
            state['shot_sent'] = True
        if state['phase_frame'] > (40 if wanted else 1):
            state['index'] += 1
            next_phase('config')

    elif phase == 'stop':
        if state['phase_frame'] == 1:
            try:
                state['les'].editor_request_end_play()
            except Exception:
                pass
        if state['phase_time'] > 6.0:
            write_report()
            try:
                unreal.unregister_slate_post_tick_callback(state['handle'])
            except Exception:
                pass
            unreal.SystemLibrary.quit_editor()


def write_report():
    if not os.path.isdir(OUT_DIR):
        os.makedirs(OUT_DIR)
    shots = []
    if state['folder'] and os.path.isdir(state['folder']):
        for name in sorted(os.listdir(state['folder'])):
            if name.lower().endswith('.png'):
                shots.append(os.path.join(state['folder'], name))
    report['screenshots'] = shots[-2:]
    report['result'] = 'OK' if len([row for row in report['rows'] if row['avg_frame_ms']]) >= 5 else 'FAILED'
    path = os.path.join(OUT_DIR, 'phase6_pie_matrix.json')
    with open(path, 'w') as handle:
        json.dump(report, handle, indent=2)
    log('report written: {0}'.format(path))
    print('PHASE6_MATRIX_RESULT: {0}'.format(report['result']))
    for row in report['rows']:
        print('PHASE6_MATRIX_ROW {0} {1}: {2} ms ({3} fps)'.format(row['id'], row['name'], row['avg_frame_ms'],
                                                                 row['fps']))


def tick_body_guarded(delta_seconds):
    try:
        tick_body(delta_seconds)
    except Exception:
        import traceback
        report['notes'].append('tick exception: ' + traceback.format_exc())
        next_phase('stop')


def main():
    state['les'] = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    unreal.EditorLoadingAndSavingUtils.load_map(LEVEL)
    log('level loaded: ' + LEVEL)
    state['handle'] = unreal.register_slate_post_tick_callback(lambda delta: tick_body_guarded(delta))
    log('tick callback registered; the matrix follows')


main()
