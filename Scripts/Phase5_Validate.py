# -*- coding: utf-8 -*-
"""Phase 5 - validate the textured house in the editor and prove it in game (PIE screenshots).

Checks (before PIE):
  T1  master material M_House_PBR exists with the BaseColor/Normal/Roughness texture parameters
  T2  the imported texture sets are present (colour / normal / roughness per used pack)
  T3  every entry of the Phase 5 instance map is parented to the textured master and carries its
      base colour texture
  T4  the house meshes' slots that have a textured instance are actually assigned to it
  T5  no house mesh slot ended up empty

Then it starts PIE, drives the first person pawn to nine viewpoints (six exterior, three interior)
and captures a 1920x1080 screenshot at each, because material work has to be seen, not asserted.

Run (needs a real RHI so the screenshots render):
  Run-Phase4Script.ps1 -Script "...\\Scripts\\Phase5_Validate.py" -Log <log> -Windowed
"""

import json
import os
import time
from datetime import datetime

import unreal

LEVEL = '/Game/Game/Environment/Lvl_Rural'
ROOT = '/Game/Game/Environment/House'
MASTER_PATH = ROOT + '/Materials/M_House_PBR'
MAP_PATH = 'C:/Temp/blender_house/p5/p5_materials.json'
PLAN_PATH = 'C:/Temp/blender_house/export/export_plan.json'
OUT_DIR = 'C:/Users/azize/OneDrive/Belgeler/Unreal Projects/MyProject/Saved/Phase5'
OUT = OUT_DIR + '/phase5_validate.json'
TEXTURE_REPORT = OUT_DIR + '/phase5_house_texture.json'
SHOT_RES = '1920x1080'
HOUSE_X0_M, HOUSE_Y0_M, PAD_M = 760.0, 783.0, 147.492

report = {'phase': 'Phase 5 - textured house validation', 'checks': [], 'screenshots': [],
          'screenshot_files': [], 'errors': [], 'result': 'FAILED'}
state = {'phase': 'wait_editor', 'phase_time': 0.0, 'ticks': 0.0, 'handle': None, 'world': None,
         'pawn': None, 'views': [], 'index': 0, 'wait': 0.0, 'known': set(), 'tag': ''}


def log(message):
    print('P5VAL: ' + str(message))


def fail(message):
    report['errors'].append(str(message))
    log('ERROR ' + str(message))


def test(identifier, title, condition, detail=''):
    report['checks'].append({'id': identifier, 'title': title, 'passed': bool(condition),
                             'detail': str(detail)[:400]})
    log('{0} {1} | {2} | {3}'.format('PASS' if condition else 'FAIL', identifier, title, detail))


def b2u(bx, by, bz):
    """Blender house local metres -> Unreal world metres for the yaw 0 placement."""
    return (HOUSE_X0_M + bx, HOUSE_Y0_M - by, PAD_M + bz)


VIEWS = [
    ('house_front_yard', b2u(0.5, -21.0, 1.9), b2u(1.5, 0.0, 2.2)),
    ('house_front_close', b2u(1.0, -11.0, 1.8), b2u(1.0, 0.0, 1.6)),
    ('house_east_side', b2u(15.0, -3.0, 1.9), b2u(2.0, -2.0, 1.8)),
    ('house_west_shed', b2u(-15.0, -9.0, 1.9), b2u(0.0, -2.0, 1.8)),
    ('roof_from_yard', b2u(-7.0, -16.0, 1.8), b2u(0.0, -1.0, 6.5)),
    ('entrance_door', b2u(1.2, -5.6, 1.7), b2u(1.2, 0.0, 1.4)),
    ('interior_kitchen', b2u(4.05, -3.1, 1.55), b2u(1.0, -3.2, 1.4)),
    ('interior_living', b2u(2.3, 0.2, 1.55), b2u(-1.0, 0.2, 1.4)),
    ('interior_bedroom', b2u(-3.9, 0.4, 1.55), b2u(-4.0, 4.2, 1.4)),
]
report['views'] = [{'name': name, 'pawn_m': [round(value, 2) for value in pawn],
                    'target_m': [round(value, 2) for value in target]}
                   for name, pawn, target in VIEWS]

editor_assets = unreal.EditorAssetLibrary
material_library = unreal.MaterialEditingLibrary
SUBFOLDER = {
    'House_Architecture': 'Architecture', 'House_Roof': 'Architecture',
    'House_Windows': 'Architecture', 'House_Interior': 'Interior',
    'House_Lighting': 'Interior', 'House_Kitchen': 'Kitchen', 'House_Bathroom': 'Bathroom',
    'House_Bedrooms': 'Bedroom', 'House_LivingRoom': 'Furniture', 'House_Props': 'Props',
    'House_Veranda': 'Exterior', 'House_Garden': 'Exterior', 'House_Yard': 'Exterior',
    'House_Shed': 'Exterior', 'House_Interactables': 'Interactables',
}


def load_json(path):
    with open(path) as handle:
        return json.load(handle)


def asset_path_of(asset):
    if asset is None:
        return None
    return str(asset.get_path_name()).split('.')[0]


def validate_assets():
    master = editor_assets.load_asset(MASTER_PATH)
    parameters = {}
    if master is not None:
        for getter, key in ((material_library.get_texture_parameter_names, 'textures'),
                            (material_library.get_scalar_parameter_names, 'scalars'),
                            (material_library.get_vector_parameter_names, 'vectors')):
            try:
                parameters[key] = sorted(str(name) for name in getter(master))
            except Exception as exc:  # noqa: BLE001
                parameters[key] = ['n/a: ' + str(exc)[:60]]
    report['master_parameters'] = parameters
    wanted = ['BaseColorTexture', 'NormalTexture', 'RoughnessTexture']
    test('T1', 'master material M_House_PBR with texture parameters',
         master is not None and all(name in parameters.get('textures', []) for name in wanted),
         json.dumps(parameters))

    material_map = load_json(MAP_PATH)
    entries = material_map.get('materials', [])
    # The texture pass records the asset each Blender material ended up with (a case-insensitive
    # name clash on Windows forces a _V2 suffix), so that map is the expectation here.
    try:
        instance_map = load_json(TEXTURE_REPORT).get('instance_map', {})
    except Exception as exc:  # noqa: BLE001
        instance_map = {}
        report['instance_map_error'] = str(exc)[:200]
    report['instance_map_entries'] = len(instance_map)
    packs = sorted({entry['pack'] for entry in entries})
    missing_textures = []
    for pack in packs:
        for kind in ('COLOR', 'NORMAL', 'ROUGHNESS'):
            path = '{0}/Textures/{1}/T_H_{1}_{2}'.format(ROOT, pack, kind)
            if editor_assets.load_asset(path) is None:
                missing_textures.append(path)
    test('T2', 'texture sets present for {0} packs'.format(len(packs)), not missing_textures,
         '{0} missing: {1}'.format(len(missing_textures), missing_textures[:4]))

    bad_instances = []
    for entry in entries:
        name = entry['material']
        path = instance_map.get(name) or ROOT + '/Materials/MI_H_' + name
        instance = editor_assets.load_asset(path)
        if instance is None:
            bad_instances.append(path + ' missing')
            continue
        parent = asset_path_of(instance.get_editor_property('parent'))
        if parent != MASTER_PATH:
            bad_instances.append('{0} parent={1}'.format(path, parent))
            continue
        texture = material_library.get_material_instance_texture_parameter_value(
            instance, 'BaseColorTexture')
        if texture is None:
            bad_instances.append(path + ' has no base colour texture')
    test('T3', 'material instances parented to the textured master ({0})'.format(len(entries)),
         not bad_instances, '{0} bad: {1}'.format(len(bad_instances), bad_instances[:4]))

    plan = load_json(PLAN_PATH)
    textured_names = {entry['material'] for entry in entries}
    counts_total = {'textured': 0, 'flat_authored': 0, 'empty': 0}
    wrong_assignment = []
    wrong_parent = []
    unresolved = []
    foreign_parents = []
    per_batch = {}
    # Blender's slot order does not survive the FBX/Interchange import, so the slot NAME stored in the
    # mesh - not the slot index from the export plan - is what decides the expected material.
    for folder in sorted(set(SUBFOLDER.values())):
        for asset_path in sorted(editor_assets.list_assets(ROOT + '/' + folder, recursive=False,
                                                          include_folder=False)):
            mesh = editor_assets.load_asset(str(asset_path))
            if mesh is None:
                continue
            counts = {'textured': 0, 'flat_authored': 0, 'empty': 0}
            for index, slot in enumerate(mesh.get_editor_property('static_materials') or []):
                try:
                    slot_name = str(slot.get_editor_property('material_slot_name'))
                except Exception:  # noqa: BLE001
                    slot_name = ''
                material = mesh.get_material(index)
                label = '{0}[{1}] {2}'.format(mesh.get_name(), index, slot_name)
                if material is None:
                    counts['empty'] += 1
                    if len(unresolved) < 12:
                        unresolved.append(label)
                    continue
                if slot_name not in textured_names:
                    counts['flat_authored'] += 1
                    continue
                counts['textured'] += 1
                expected = instance_map.get(slot_name) or ROOT + '/Materials/MI_H_' + slot_name
                if asset_path_of(material) != expected and len(wrong_assignment) < 6:
                    wrong_assignment.append('{0} -> {1} (expected {2})'.format(
                        label, asset_path_of(material), expected))
                parent = asset_path_of(material.get_editor_property('parent'))
                if parent != MASTER_PATH:
                    if len(wrong_parent) < 6:
                        wrong_parent.append('{0} parent={1}'.format(label, parent))
                    if parent and not parent.startswith(ROOT) and len(foreign_parents) < 6:
                        foreign_parents.append('{0} -> {1}'.format(label, parent))
            for key in counts_total:
                counts_total[key] += counts[key]
            per_batch[mesh.get_name()] = counts
    report['slots'] = dict(counts_total)
    report['slots_per_batch'] = per_batch
    report['unresolved_slots'] = unresolved
    report['foreign_parents'] = foreign_parents
    test('T4', 'textured slots use their own textured instance', not wrong_assignment,
         '{0} textured slots, wrong={1} {2}'.format(counts_total['textured'],
                                                   len(wrong_assignment), wrong_assignment))
    test('T5', 'every textured slot is parented to M_House_PBR', not wrong_parent,
         'wrong parents={0}'.format(wrong_parent))
    test('T6', 'no house slot lost its material', counts_total['empty'] == 0,
         'empty={0}, flat authored={1}'.format(counts_total['empty'],
                                               counts_total['flat_authored']))



# ---------------------------------------------------------------- PIE screenshots
def get_game_world():
    try:
        return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_game_world()
    except Exception:  # noqa: BLE001
        return None


def screenshot_folder():
    root = unreal.Paths.convert_relative_path_to_full(
        unreal.Paths.project_saved_dir() + 'Screenshots/')
    for candidate in ('WindowsEditor', 'Windows'):
        folder = os.path.join(root, candidate)
        if os.path.isdir(folder):
            return folder
    return os.path.join(root, 'WindowsEditor')


def new_shots(folder, known):
    if not os.path.isdir(folder):
        return []
    files = [os.path.join(folder, name) for name in os.listdir(folder)
             if name.lower().endswith('.png')]
    return sorted((path for path in files if path not in known), key=os.path.getmtime)


def next_phase(name):
    state['phase'] = name
    state['phase_time'] = 0.0
    log('phase -> {0}'.format(name))


def place_pawn(view):
    pawn = state['pawn']
    if pawn is None:
        return
    location = view[1]
    pawn.set_actor_location(unreal.Vector(location[0] * 100.0, location[1] * 100.0,
                                          location[2] * 100.0), False, True)
    controller = unreal.GameplayStatics.get_player_controller(state['world'], 0)
    camera = pawn.get_editor_property('first_person_camera')
    if controller is None or camera is None:
        return
    target = unreal.Vector(view[2][0] * 100.0, view[2][1] * 100.0, view[2][2] * 100.0)
    controller.set_control_rotation(
        unreal.MathLibrary.find_look_at_rotation(camera.get_world_location(), target))


def write_report(reason):
    report['end_reason'] = reason
    test('T7', 'in-game screenshots captured', len(report['screenshot_files']) >= 8,
         '{0} files, last: {1}'.format(len(report['screenshot_files']),
                                       report['screenshot_files'][-2:]))
    failed = [check['id'] for check in report['checks'] if not check['passed']]
    report['result'] = 'PASSED' if not report['errors'] and not failed else 'FAILED'
    report['failed_checks'] = failed
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT, 'w') as handle:
        json.dump(report, handle, indent=2)
    log('result {0} ({1}), evidence written'.format(report['result'], reason))


def tick_body(delta_seconds):
    state['phase_time'] += delta_seconds
    phase = state['phase']
    if phase == 'wait_editor':
        if state['phase_time'] > 4.0:
            state['les'].editor_request_begin_play()
            log('PIE requested')
            next_phase('wait_world')
    elif phase == 'wait_world':
        world = get_game_world()
        if world is not None:
            state['world'] = world
            state['folder'] = screenshot_folder()
            state['known'] = set(new_shots(state['folder'], set()))
            log('PIE world ready after {0:.1f}s'.format(state['phase_time']))
            next_phase('wait_pawn')
        elif state['phase_time'] > 150.0:
            fail('PIE world did not start')
            next_phase('stop')
    elif phase == 'wait_pawn':
        pawn = unreal.GameplayStatics.get_player_pawn(state['world'], 0)
        if pawn is not None:
            state['pawn'] = pawn
            state['index'] = 0
            log('pawn ready: ' + pawn.get_name())
            next_phase('settle')
        elif state['phase_time'] > 90.0:
            fail('no player pawn in PIE')
            next_phase('stop')
    elif phase == 'settle':
        place_pawn(VIEWS[state['index']])
        if state['phase_time'] > 1.6:
            next_phase('shoot')
    elif phase == 'shoot':
        place_pawn(VIEWS[state['index']])
        if state['phase_time'] > 0.25:
            name = VIEWS[state['index']][0]
            unreal.SystemLibrary.execute_console_command(state['world'], 'HighResShot ' + SHOT_RES)
            report['screenshots'].append({'name': name, 'tick': state['ticks']})
            log('screenshot requested: ' + name)
            next_phase('collect')
    elif phase == 'collect':
        shots = new_shots(state['folder'], state['known'])
        if shots or state['phase_time'] > 25.0:
            for shot in shots:
                state['known'].add(shot)
            report['screenshot_files'].extend(shots)
            log('captured {0} file(s) for {1}'.format(len(shots), VIEWS[state['index']][0]))
            state['index'] += 1
            if state['index'] >= len(VIEWS):
                next_phase('stop')
            else:
                next_phase('settle')
    elif phase == 'stop':
        try:
            state['les'].editor_request_end_play()
        except Exception:  # noqa: BLE001
            pass
        if state['phase_time'] > 6.0:
            write_report('completed')
            try:
                unreal.unregister_slate_post_tick_callback(state['handle'])
            except Exception:  # noqa: BLE001
                pass
            unreal.SystemLibrary.quit_editor()


def tick_body_guarded(delta_seconds):
    state['ticks'] += 1
    try:
        tick_body(delta_seconds)
    except Exception:  # noqa: BLE001
        import traceback
        fail('tick exception: ' + traceback.format_exc())
        try:
            state['les'].editor_request_end_play()
        except Exception:  # noqa: BLE001
            pass


def main():
    state['les'] = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    unreal.EditorLoadingAndSavingUtils.load_map(LEVEL)
    validate_assets()
    report['level_loaded'] = True
    state['handle'] = unreal.register_slate_post_tick_callback(
        lambda delta: tick_body_guarded(delta))
    log('asset validation done, PIE screenshots follow on the next ticks')


main()




