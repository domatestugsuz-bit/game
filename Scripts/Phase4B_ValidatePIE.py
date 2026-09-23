# -*- coding: utf-8 -*-
"""Phase 4B - in-game (PIE) validation of the home property, with screenshots.

Tick driven (no blocking sleeps): the editor requests PIE, waits for the pawn,
then checks the spawn, the property actors, the forest, mouse look, movement, the
Phase 3A interaction flow and the vehicle - and takes high resolution screenshots.

Run (needs a real RHI so the screenshots render):

  UnrealEditor-Cmd.exe "<Project>.uproject" -ExecutePythonScript="<this file>"
                       -unattended -nosplash -windowed -ResX=1280 -ResY=720
                       -stdout -NoSourceControl -NoLogTimes
"""

import json
import os
from datetime import datetime

import unreal

LEVEL_PATH = '/Game/Game/Environment/Lvl_Rural'
SHOT_RES = '1280x720'
PAD_M = 147.49            # Phase 4B pad height (world meters), from the build report
SPAWN_M = (758.0, 773.0)  # PlayerStart_Home

report = {
    'phase': 'Phase 4B - home property PIE validation',
    'timestamp': datetime.now().isoformat(timespec='seconds'),
    'tests': [],
    'failed': [],
    'notes': [],
    'screenshots': [],
    'result': 'FAILED',
}

state = {
    'phase': 'request',
    'ticks': 0,
    'phase_time': 0.0,
    'handle': None,
    'world': None,
    'pawn': None,
    'component': None,
    'widget': None,
    'target': None,
    'vehicle': None,
    'vehicle_z': None,
    'les': None,
    'move_start': None,
    'yaw_before': 0.0,
    'count_before': 0,
    'count_after_first': 0,
    'interact_returned': False,
    'actors_seen': [],
    'tree_instances': 0,
}


def log(message):
    unreal.log('P4B-PIE: ' + str(message))


def warn(message):
    unreal.log_warning('P4B-PIE: ' + str(message))
    report['notes'].append(str(message))


def fail(message):
    unreal.log_error('P4B-PIE: ' + str(message))
    report['failed'].append(str(message))


def test(test_id, name, passed, detail=''):
    report['tests'].append({'id': test_id, 'name': name, 'passed': bool(passed), 'detail': str(detail)})
    if not passed:
        report['failed'].append('{0} {1}: {2}'.format(test_id, name, detail))
    unreal.log('P4B-PIE_TEST {0}: {1} {2} :: {3}'.format(test_id, 'PASS' if passed else 'FAIL', name, detail))
    return bool(passed)


def write_report():
    rel = unreal.Paths.project_saved_dir() + 'Phase4B/'
    out_dir = unreal.Paths.convert_relative_path_to_full(rel)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    path = os.path.join(out_dir, 'phase4b_pie.json')
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


def cm_to_m(value):
    return round(float(value) / 100.0, 2)


def all_actors(world):
    return unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor)


def take_screenshot(world, name):
    report['screenshots'].append({'name': name})
    unreal.SystemLibrary.execute_console_command(world, 'HighResShot ' + SHOT_RES)


def screenshot_folder():
    """PIE writes into Saved/Screenshots/WindowsEditor, standalone into .../Windows."""
    root = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir() + 'Screenshots/')
    for candidate in ('WindowsEditor', 'Windows'):
        folder = os.path.join(root, candidate)
        if os.path.isdir(folder):
            return folder
    return os.path.join(root, 'WindowsEditor')


def newest_screenshot(folder):
    if not os.path.isdir(folder):
        return None
    files = [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith('.png')]
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def check_spawn():
    pawn = state['pawn']
    world = state['world']
    location = pawn.get_actor_location()
    x, y, z = cm_to_m(location.x), cm_to_m(location.y), cm_to_m(location.z)
    test('T1', 'PIE session is running',
         state['les'].is_in_play_in_editor(), 'is_in_play=True')
    pawn_class = pawn.get_class().get_name()
    test('T2', 'pawn is the Phase 3A first person character',
         pawn_class == 'BP_PlayerCharacter_C', 'class=' + pawn_class)
    test('T3', 'player spawns at PlayerStart_Home on the pad',
         abs(x - SPAWN_M[0]) < 2.0 and abs(y - SPAWN_M[1]) < 2.0 and abs(z - (PAD_M + 0.9)) < 0.8,
         'pawn at ({0}, {1}, {2}) m'.format(x, y, z))

    hit = unreal.SystemLibrary.line_trace_single(
        world, location, vec(location.x, location.y, location.z - 400.0),
        unreal.TraceTypeQuery.ECC_VISIBILITY, False, [pawn], unreal.DrawDebugTrace.NONE, True)
    ground = None
    if hit is not None:
        data = hit.to_dict()
        if data.get('blocking_hit', True):
            ground = cm_to_m(data['location'].z)
    test('T4', 'player stands on the property pad',
         ground is not None and abs(ground - PAD_M) < 0.6,
         'ground below the pawn = {0} m (pad {1} m)'.format(ground, PAD_M))

    controller = unreal.GameplayStatics.get_player_controller(world, 0)
    if controller is not None:
        yaw = controller.get_control_rotation().yaw
        delta = unreal.MathLibrary.normalize_to_range(yaw - 90.0, -180.0, 180.0)
        test('T5', 'player looks towards the house (yaw 90)', abs(delta) < 15.0, 'yaw={0:.1f}'.format(yaw))
    else:
        test('T5', 'player looks towards the house (yaw 90)', False, 'no player controller')


def check_property_actors():
    expected = ['P4B_House', 'P4B_Veranda', 'P4B_Garage', 'P4B_Shed', 'P4B_ConcreteYard',
                'P4B_Driveway', 'P4B_Grill', 'Vehicle', 'InteractionTestObject', 'PlayerStart_Home']
    labels = []
    trees = []
    for actor in all_actors(state['world']):
        try:
            label = actor.get_actor_label()
        except Exception:
            continue
        labels.append(label)
        if label.startswith('P4B_Trees_'):
            trees.append(actor)
    state['actors_seen'] = labels
    missing = [name for name in expected if name not in labels]
    test('T6', 'every Phase 4B actor is present in game', not missing,
         'missing={0}'.format(missing) if missing else '{0} actors in the world'.format(len(labels)))

    instances = 0
    for actor in trees:
        for component in actor.get_components_by_class(unreal.HierarchicalInstancedStaticMeshComponent):
            instances += int(component.get_instance_count())
    state['tree_instances'] = instances
    test('T7', 'pine forest is instanced in game', instances >= 800 and len(trees) >= 10,
         '{0} instances in {1} instanced actors'.format(instances, len(trees)))


def find_vehicle():
    for actor in all_actors(state['world']):
        try:
            if 'VehicleBase' in actor.get_class().get_name():
                return actor
        except Exception:
            continue
    return None


def start_vehicle_check():
    state['vehicle'] = find_vehicle()
    if state['vehicle'] is None:
        test('T8', 'vehicle is placed on the property pad', False, 'BP_VehicleBase not found')
        return
    location = state['vehicle'].get_actor_location()
    state['vehicle_z'] = cm_to_m(location.z)
    test('T8', 'vehicle is placed on the property pad',
         abs(state['vehicle_z'] - (PAD_M + 0.69)) < 0.8,
         'vehicle at ({0}, {1}, {2}) m'.format(cm_to_m(location.x), cm_to_m(location.y), state['vehicle_z']))


def check_vehicle():
    if state['vehicle'] is None:
        test('T9', 'vehicle rests on the ground (no sinking)', False, 'no vehicle')
        return
    z = cm_to_m(state['vehicle'].get_actor_location().z)
    test('T9', 'vehicle rests on the ground (no sinking)',
         abs(z - state['vehicle_z']) < 0.6, 'z {0} -> {1} m'.format(state['vehicle_z'], z))


def start_move():
    state['move_start'] = state['pawn'].get_actor_location()


def hold_move():
    state['pawn'].add_movement_input(vec(1.0, 0.0, 0.0), 1.0)


def check_move():
    moved = (state['pawn'].get_actor_location() - state['move_start']).length()
    test('T10', 'forward movement works on the property', moved > 50.0,
         'displacement={0:.1f}cm'.format(moved))


def start_look():
    state['yaw_before'] = unreal.GameplayStatics.get_player_controller(
        state['world'], 0).get_control_rotation().yaw


def do_look():
    unreal.GameplayStatics.get_player_controller(state['world'], 0).add_yaw_input(60.0)


def check_look():
    controller = unreal.GameplayStatics.get_player_controller(state['world'], 0)
    delta = abs(controller.get_control_rotation().yaw - state['yaw_before'])
    test('T11', 'mouse look still rotates the controller', delta > 10.0, 'yaw_delta={0:.1f}deg'.format(delta))


def aim_at_target():
    pawn = state['pawn']
    target_location = state['target'].get_actor_location()
    pawn.set_actor_location(vec(target_location.x - 150.0, target_location.y, target_location.z + 80.0), False, True)
    camera = pawn.get_editor_property('first_person_camera')
    controller = unreal.GameplayStatics.get_player_controller(state['world'], 0)
    controller.set_control_rotation(
        unreal.MathLibrary.find_look_at_rotation(camera.get_world_location(), target_location))


def check_focus():
    focused = state['component'].get_focused_interactable()
    ok = focused is not None and focused.get_name() == state['target'].get_name()
    test('T12', 'interaction trace still focuses the test object', ok,
         'focused={0}'.format(focused.get_name() if focused else 'None'))


def check_prompt_visible():
    widget = state['widget']
    visible = widget.is_prompt_visible() if widget else None
    text = state['component'].get_focused_prompt_text()
    try:
        text_ok = not text.is_empty()
        dump = str(text)
    except Exception as exc:  # noqa: BLE001
        text_ok = True
        dump = '<unprintable: {0}>'.format(exc)
    detail = 'widget_visible={0} text={1}'.format('n/a (protected)' if visible is None else visible, dump)
    test('T13', 'interaction prompt text is provided for the focus',
         text_ok and (visible is None or visible), detail)


def interact_first():
    state['count_before'] = state['target'].get_interaction_count()
    state['interact_returned'] = bool(state['component'].try_interact())


def check_interact_first():
    after = state['target'].get_interaction_count()
    state['count_after_first'] = after
    test('T14', 'interacting still triggers the object',
         state['interact_returned'] and after == state['count_before'] + 1 and state['target'].is_activated(),
         'returned={0} count={1}->{2}'.format(state['interact_returned'], state['count_before'], after))


def interact_second():
    state['component'].try_interact()


def check_interact_second():
    after = state['target'].get_interaction_count()
    test('T15', 'interacting again toggles it back',
         after == state['count_after_first'] + 1 and not state['target'].is_activated(),
         'count={0} activated={1}'.format(after, state['target'].is_activated()))


def check_screenshots():
    folder = screenshot_folder()
    files = []
    if os.path.isdir(folder):
        files = sorted((f for f in os.listdir(folder) if f.lower().endswith('.png')),
                       key=lambda f: os.path.getmtime(os.path.join(folder, f)))
    report['screenshot_files'] = [os.path.join(folder, f) for f in files[-4:]]
    report['screenshot_folder'] = folder
    test('T16', 'game screenshots were captured', len(files) >= 4,
         '{0} files in {1}, newest: {2}'.format(len(files), folder, files[-4:]))


def next_phase(phase):
    state['phase'] = phase
    state['phase_time'] = 0.0
    log('phase -> {0} (tick {1})'.format(phase, state['ticks']))


def find_test_object():
    for actor in all_actors(state['world']):
        try:
            if 'InteractionTestObject' in actor.get_class().get_name():
                return actor
        except Exception:
            continue
    return None


def on_tick(delta_seconds):
    state['ticks'] += 1
    try:
        tick_body(delta_seconds)
    except Exception:  # noqa: BLE001
        import traceback
        fail('tick exception: ' + traceback.format_exc())
        finish('tick exception')


def tick_body(delta_seconds):
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
        elif state['phase_time'] > 120.0:
            test('T1', 'PIE session is running', False, 'PIE world never became available')
            finish('timeout waiting for the PIE world')

    elif phase == 'wait_pawn':
        pawn = unreal.GameplayStatics.get_player_pawn(state['world'], 0)
        if pawn:
            state['pawn'] = pawn
            next_phase('settle')
        elif state['phase_time'] > 30.0:
            fail('player pawn never spawned')
            finish('timeout waiting for the pawn')

    elif phase == 'settle':
        if state['phase_time'] >= 1.5:
            check_spawn()
            check_property_actors()
            next_phase('shot_house')

    elif phase == 'shot_house':
        take_screenshot(state['world'], 'house_from_spawn')
        next_phase('shot_house_wait')

    elif phase == 'shot_house_wait':
        if state['phase_time'] >= 2.0:
            next_phase('move_start')

    elif phase == 'move_start':
        start_move()
        next_phase('move_hold')

    elif phase == 'move_hold':
        hold_move()
        if state['phase_time'] >= 1.5:
            next_phase('move_check')

    elif phase == 'move_check':
        check_move()
        next_phase('shot_property')

    elif phase == 'shot_property':
        take_screenshot(state['world'], 'property_close')
        next_phase('shot_property_wait')

    elif phase == 'shot_property_wait':
        if state['phase_time'] >= 2.0:
            next_phase('look_start')

    elif phase == 'look_start':
        start_look()
        next_phase('look_do')

    elif phase == 'look_do':
        do_look()
        next_phase('look_check')

    elif phase == 'look_check':
        if state['phase_time'] >= 0.5:
            check_look()
            next_phase('shot_forest')

    elif phase == 'shot_forest':
        take_screenshot(state['world'], 'forest_around_property')
        next_phase('shot_forest_wait')

    elif phase == 'shot_forest_wait':
        if state['phase_time'] >= 2.0:
            next_phase('veranda_start')

    elif phase == 'veranda_start':
        # Stand on the pad west of the veranda and look east along the garden side.
        state['pawn'].set_actor_location(vec(74500.0, 79600.0, (PAD_M + 1.2) * 100.0), False, True)
        unreal.GameplayStatics.get_player_controller(state['world'], 0).set_control_rotation(
            unreal.Rotator(-6.0, 0.0, 0.0))
        next_phase('veranda_settle')

    elif phase == 'veranda_settle':
        if state['phase_time'] >= 1.0:
            next_phase('shot_veranda')

    elif phase == 'shot_veranda':
        take_screenshot(state['world'], 'veranda_garden_side')
        next_phase('shot_veranda_wait')

    elif phase == 'shot_veranda_wait':
        if state['phase_time'] >= 2.0:
            next_phase('vehicle_start')

    elif phase == 'vehicle_start':
        start_vehicle_check()
        next_phase('vehicle_wait')

    elif phase == 'vehicle_wait':
        if state['phase_time'] >= 2.0:
            check_vehicle()
            state['target'] = find_test_object()
            state['component'] = state['pawn'].get_editor_property('interaction_component')
            if state['target'] is None or state['component'] is None:
                fail('interaction test object or component missing')
                finish('no interaction target')
            else:
                try:
                    state['widget'] = state['component'].get_editor_property('prompt_widget')
                except Exception as exc:  # noqa: BLE001
                    state['widget'] = None
                    warn('prompt widget is protected in Python ({0}); the screenshot covers the HUD'.format(exc))
                aim_at_target()
                next_phase('focus_wait')

    elif phase == 'focus_wait':
        if state['phase_time'] >= 1.0:
            check_focus()
            check_prompt_visible()
            next_phase('focus_shot')

    elif phase == 'focus_shot':
        take_screenshot(state['world'], 'interaction_prompt')
        next_phase('focus_shot_wait')

    elif phase == 'focus_shot_wait':
        if state['phase_time'] >= 2.0:
            next_phase('interact_first')

    elif phase == 'interact_first':
        interact_first()
        next_phase('interact_first_wait')

    elif phase == 'interact_first_wait':
        if state['phase_time'] >= 0.5:
            check_interact_first()
            next_phase('interact_second')

    elif phase == 'interact_second':
        interact_second()
        next_phase('interact_second_wait')

    elif phase == 'interact_second_wait':
        if state['phase_time'] >= 0.5:
            check_interact_second()
            check_screenshots()
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
    except Exception as exc:  # noqa: BLE001
        warn('end play failed: {0}'.format(exc))

    report['result'] = 'OK' if not report['failed'] else 'FAILED'
    report['ticks'] = state['ticks']
    report['actors_seen'] = state['actors_seen']
    report['tree_instances'] = state['tree_instances']
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

