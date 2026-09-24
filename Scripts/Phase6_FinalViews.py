# -*- coding: utf-8 -*-
"""Phase 6 - final evidence screenshots from four fixed viewpoints.

Runs PIE (tick driven, launched with -ExecCmds) and captures one 1920x1080 screenshot per
view so the whole pass can be judged by eye:

    house_from_yard   the textured house seen from its own yard
    forest_edge       the new pine forest with the ten layer landscape material
    world_edge_west   the world edge that used to be the raw 0 trench (-256 m)
    overview          aerial view of the property, forest belt and mountains

Writes Saved/Phase6/phase6_final_views.json.
"""

import json
import os
from datetime import datetime

import unreal

LEVEL = '/Game/Game/Environment/Lvl_Rural'
OUT_DIR = 'C:/Users/azize/OneDrive/Belgeler/Unreal Projects/MyProject/Saved/Phase6'
SHOT_RES = '1920x1080'
SETTLE_FRAMES = 25
COLLECT_FRAMES = 35

VIEWS = [
    ('house_from_yard', (742.0, 760.0), 2.0, (760.0, 783.0), False),
    ('forest_edge', (690.0, 640.0), 2.0, None, False),
    ('world_edge_west', (-1150.0, 0.0), 2.5, None, False),
    ('overview', (760.0, 783.0), 420.0, (520.0, 520.0), True),
]

report = {'phase': 'Phase 6 - final views', 'timestamp': datetime.now().isoformat(timespec='seconds'),
          'views': [], 'screenshots': [], 'notes': [], 'result': 'FAILED'}
state = {'phase': 'wait_editor', 'phase_time': 0.0, 'phase_frame': 0, 'index': 0, 'les': None, 'world': None,
         'pawn': None, 'pc': None, 'handle': None, 'folder': '', 'known': set()}


def log(message):
    print('PHASE6-VIEW: ' + str(message))


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


def ground_z(world, x_m, y_m):
    start = unreal.Vector(x_m * 100.0, y_m * 100.0, 60000.0)
    end = unreal.Vector(x_m * 100.0, y_m * 100.0, -60000.0)
    hit = unreal.SystemLibrary.line_trace_single(world, start, end, unreal.TraceTypeQuery.ECC_VISIBILITY, True, [],
                                                 unreal.DrawDebugTrace.NONE, True)
    if hit is None:
        return None
    try:
        return float(hit.to_dict()['location'].z) / 100.0
    except Exception:
        return None


def place_view(entry):
    name, (x_m, y_m), height_m, target, aerial = entry
    pawn = state['pawn']
    pc = state['pc']
    ground = ground_z(state['world'], x_m, y_m)
    base = ground if ground is not None else 0.0
    z_cm = (base + height_m) * 100.0
    location = unreal.Vector(x_m * 100.0, y_m * 100.0, z_cm)
    try:
        pawn.set_actor_location(location, False, False)
    except Exception:
        try:
            pawn.set_actor_location(location, False, True)
        except Exception as exc:
            report['notes'].append('teleport failed for {0}: {1}'.format(name, exc))
    if target is not None:
        aim = unreal.Vector(target[0] * 100.0, target[1] * 100.0, base * 100.0 + 400.0)
        pc.set_control_rotation(unreal.MathLibrary.find_look_at_rotation(location, aim))
    elif aerial:
        pc.set_control_rotation(unreal.Rotator(-52.0, 225.0, 0.0))
    else:
        pc.set_control_rotation(unreal.Rotator(0.0, 305.0, 0.0))


def screenshot_folder():
    return unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir() + 'Screenshots/WindowsEditor')


def new_shots(folder, known):
    shots = []
    if os.path.isdir(folder):
        for name in sorted(os.listdir(folder)):
            if name.lower().endswith('.png'):
                path = os.path.join(folder, name)
                if path not in known:
                    shots.append(path)
    return shots


def write_report():
    if not os.path.isdir(OUT_DIR):
        os.makedirs(OUT_DIR)
    report['result'] = 'OK' if len(report['screenshots']) >= 3 else 'FAILED'
    path = os.path.join(OUT_DIR, 'phase6_final_views.json')
    with open(path, 'w') as handle:
        json.dump(report, handle, indent=2)
    log('report written: {0}'.format(path))
    print('PHASE6_VIEWS_RESULT: {0}'.format(report['result']))
    for shot in report['screenshots']:
        print('PHASE6_VIEW_SHOT ' + shot)


def tick_body(delta_seconds):
    state['phase_time'] += delta_seconds
    state['phase_frame'] += 1
    phase = state['phase']

    if phase == 'wait_editor':
        if state['phase_time'] > 4.0:
            state['folder'] = screenshot_folder()
            state['known'] = set(new_shots(state['folder'], set()))
            state['les'].editor_request_begin_play()
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
            next_phase('settle')
        elif state['phase_time'] > 120.0:
            report['notes'].append('no pawn in PIE')
            next_phase('stop')

    elif phase == 'settle':
        entry = VIEWS[state['index']]
        place_view(entry)
        if state['phase_frame'] > SETTLE_FRAMES:
            unreal.SystemLibrary.execute_console_command(state['world'], 'HighResShot ' + SHOT_RES)
            log('screenshot requested: {0}'.format(entry[0]))
            next_phase('collect')

    elif phase == 'collect':
        shots = new_shots(state['folder'], state['known'])
        if shots or state['phase_frame'] > COLLECT_FRAMES:
            for shot in shots:
                state['known'].add(shot)
                report['screenshots'].append(shot)
            report['views'].append({'name': VIEWS[state['index']][0], 'files': shots})
            state['index'] += 1
            if state['index'] >= len(VIEWS):
                next_phase('stop')
            else:
                next_phase('settle')

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
    log('tick callback registered')


main()
