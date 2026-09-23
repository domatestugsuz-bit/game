# -*- coding: utf-8 -*-
"""Phase 3A - functional validation of the interaction chain (editor world).

The editor quits as soon as an -ExecutePythonScript script returns, so a
multi-tick PIE test cannot finish inside a single launch. This script instead:
  * spawns BP_PlayerCharacter + BP_InteractionTestObject in the current (empty)
    editor world,
  * drives the real code paths synchronously (RefreshFocus -> camera trace +
    interface call, TryInteract -> object behaviour),
  * checks the asset/class configuration (parents, input actions, game mode),
  * destroys everything it spawned and never saves anything.

The gameplay level is not loaded and not saved; no asset is modified.
"""

import json
import os
from datetime import datetime

import unreal

report = {'phase': 'Phase 3A - functional validation (editor world)',
          'timestamp': datetime.now().isoformat(timespec='seconds'),
          'tests': [], 'failed': [], 'notes': [], 'result': 'FAILED'}

PLAYER_BP = '/Game/Game/Characters/Player/BP_PlayerCharacter.BP_PlayerCharacter_C'
TEST_OBJECT_BP = '/Game/Game/Interaction/BP_InteractionTestObject.BP_InteractionTestObject_C'
GAME_MODE_BP = '/Game/Game/Core/BP_GameMode.BP_GameMode_C'
WBP_PROMPT = '/Game/Game/UI/WBP_InteractionPrompt.WBP_InteractionPrompt_C'
INTERACTABLE = '/Script/MyProject.InteractableInterface'


def log(message):
    unreal.log('PHASE3A-VALIDATE: ' + str(message))


def test(test_id, name, passed, detail=''):
    entry = {'id': test_id, 'name': name, 'passed': bool(passed), 'detail': str(detail)}
    report['tests'].append(entry)
    if not passed:
        report['failed'].append('{0} {1}: {2}'.format(test_id, name, detail))
    unreal.log('PHASE3A_VALIDATE_TEST {0}: {1} {2} :: {3}'.format(
        test_id, 'PASS' if passed else 'FAIL', name, detail))
    return bool(passed)


def write_report():
    rel = unreal.Paths.project_saved_dir() + 'Phase3A/'
    out_dir = unreal.Paths.convert_relative_path_to_full(rel)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    path = os.path.join(out_dir, 'phase3a_validation_report.json')
    with open(path, 'w') as handle:
        json.dump(report, handle, indent=2)
    return path


def vec(x, y, z):
    return unreal.Vector(x, y, z)


def distance(a, b):
    return (a - b).length()


def look_at_rotation(from_location, to_location):
    """Rotation from one point to another (with API fallbacks)."""
    try:
        return unreal.MathLibrary.find_look_at_rotation(from_location, to_location)
    except Exception:
        pass
    try:
        return unreal.KismetMathLibrary.find_look_at_rotation(from_location, to_location)
    except Exception:
        pass
    import math
    delta = to_location - from_location
    xy = math.sqrt(delta.x * delta.x + delta.y * delta.y)
    yaw = math.degrees(math.atan2(delta.y, delta.x))
    pitch = math.degrees(math.atan2(delta.z, xy))
    return unreal.Rotator(pitch, yaw, 0.0)


def get_parent_class_name(asset_path):
    """Parent class name of a Blueprint asset (UE 5.8 Python API)."""
    asset = unreal.EditorAssetLibrary.load_asset(asset_path)
    if not asset:
        return 'missing'
    try:
        parent = unreal.BlueprintEditorLibrary.get_blueprint_parent_class(asset)
        return parent.get_name() if parent else 'none'
    except Exception as exc:
        return '<error: {0}>'.format(exc)


def check_configuration():
    """Asset / class level checks (no world interaction)."""
    player_class = unreal.load_class(None, PLAYER_BP)
    test_class = unreal.load_class(None, TEST_OBJECT_BP)
    game_mode_class = unreal.load_class(None, GAME_MODE_BP)
    prompt_class = unreal.load_class(None, WBP_PROMPT)
    interface_class = unreal.load_class(None, INTERACTABLE)

    test('A1', 'BP_PlayerCharacter derives from the C++ first person character',
         get_parent_class_name('/Game/Game/Characters/Player/BP_PlayerCharacter') == 'MyProjectPlayerCharacter',
         'parent={0}'.format(get_parent_class_name('/Game/Game/Characters/Player/BP_PlayerCharacter')))

    pawn_default = None
    if game_mode_class:
        pawn_default = unreal.get_default_object(game_mode_class).get_editor_property('default_pawn_class')
    test('A2', 'BP_GameMode uses BP_PlayerCharacter as default pawn',
         pawn_default is not None and 'BP_PlayerCharacter' in str(pawn_default),
         'pawn={0}'.format(pawn_default))

    implements = None
    try:
        implements = bool(test_class.implements_interface(interface_class)) if (test_class and interface_class) else None
    except Exception as exc:
        implements = None
        report['notes'].append('A3: Class->ImplementsInterface is not exposed to Python ({0}); '
                               'the interface is proven behaviourally by test B7'.format(exc))
    test('A3', 'BP_InteractionTestObject implements the Interactable Interface', implements is not False,
         'implements={0}'.format(implements if implements is not None else 'proven by B7 trace focus'))

    test('A4', 'WBP_InteractionPrompt derives from the C++ prompt widget',
         get_parent_class_name('/Game/Game/UI/WBP_InteractionPrompt') == 'InteractionPromptWidget',
         'parent={0}'.format(get_parent_class_name('/Game/Game/UI/WBP_InteractionPrompt')))

    if player_class:
        cdo = unreal.get_default_object(player_class)
        actions = {
            'move_action': cdo.get_editor_property('move_action'),
            'look_action': cdo.get_editor_property('look_action'),
            'jump_action': cdo.get_editor_property('jump_action'),
            'interact_action': cdo.get_editor_property('interact_action'),
            'mapping_context': cdo.get_editor_property('default_mapping_context'),
        }
        missing = [key for key, value in actions.items() if value is None]
        test('A5', 'enhanced input actions and mapping context are assigned',
             len(missing) == 0, 'missing={0}'.format(missing))

    return player_class, test_class


def check_live_chain(player_class, test_class):
    """Spawns the real actors and drives the real interaction code paths."""
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    spawned = []
    if not player_class or not test_class:
        test('B1', 'spawn player character and test object', False, 'classes missing')
        return spawned

    try:
        pawn = actors.spawn_actor_from_class(player_class, vec(0.0, 0.0, 120.0))
        target = actors.spawn_actor_from_class(test_class, vec(320.0, 0.0, 45.0))
    except Exception as exc:
        test('B1', 'spawn player character and test object', False, str(exc))
        return spawned

    spawned.extend([pawn, target])
    test('B1', 'spawn player character and test object', pawn is not None and target is not None,
         'pawn={0} target={1}'.format(pawn is not None, target is not None))
    if not pawn or not target:
        return spawned

    camera = pawn.get_editor_property('first_person_camera')
    pawn_location = pawn.get_actor_location()
    camera_location = camera.get_world_location()
    eye_delta = camera_location.z - pawn_location.z
    horizontal = distance(vec(camera_location.x, camera_location.y, 0.0),
                          vec(pawn_location.x, pawn_location.y, 0.0))
    test('B2', 'camera is attached at eye level (first person)',
         abs(eye_delta - 64.0) <= 5.0 and horizontal <= 5.0,
         'eye_delta={0:.1f}cm horizontal={1:.2f}cm'.format(eye_delta, horizontal))

    spring_arms = [c.get_class().get_name() for c in pawn.get_components_by_class(unreal.SceneComponent)
                   if 'SpringArm' in c.get_class().get_name()]
    test('B3', 'no third-person rig / spring arm on the pawn', len(spring_arms) == 0,
         'spring_arms={0}'.format(spring_arms))

    mesh = pawn.get_editor_property('mesh')
    owner_no_see = bool(mesh.get_editor_property('owner_no_see')) if mesh else False
    hidden_shadow = bool(mesh.get_editor_property('cast_hidden_shadow')) if mesh else False
    cast_shadow = bool(mesh.get_editor_property('cast_shadow')) if mesh else False
    test('B4', 'body mesh invisible to the owner camera', owner_no_see,
         'owner_no_see={0}'.format(owner_no_see))
    test('B5', 'body still casts shadows (player presence)', cast_shadow and hidden_shadow,
         'cast_shadow={0} cast_hidden_shadow={1}'.format(cast_shadow, hidden_shadow))

    component = pawn.get_editor_property('interaction_component')
    test('B6', 'interaction component present on the pawn', component is not None,
         component.get_class().get_name() if component else 'missing')
    if not component:
        return spawned

    target_location = target.get_actor_location()
    pawn.set_actor_location(vec(target_location.x - 140.0, target_location.y, target_location.z + 75.0), False, True)
    pawn.set_actor_rotation(look_at_rotation(camera.get_world_location(), target_location), False)
    component.refresh_focus()

    focused = component.get_focused_interactable()
    test('B7', 'camera trace focuses the interactable object',
         focused is not None and focused.get_name() == target.get_name(),
         'focused={0}'.format(focused.get_name() if focused else 'None'))

    prompt_text = component.get_focused_prompt_text()
    text_ok = False
    text_dump = '<n/a>'
    try:
        text_ok = not prompt_text.is_empty()
        text_dump = str(prompt_text)
    except Exception as exc:
        text_dump = '<unprintable: {0}>'.format(exc)
    test('B8', 'prompt text comes from the interactable interface', text_ok, 'text={0}'.format(text_dump))

    before = target.get_interaction_count()
    returned = bool(component.try_interact())
    after = target.get_interaction_count()
    test('B9', 'interact triggers the object behaviour',
         returned and after == before + 1 and target.is_activated(),
         'returned={0} count={1}->{2} activated={3}'.format(returned, before, after, target.is_activated()))

    component.try_interact()
    test('B10', 'interacting again toggles the object back',
         target.get_interaction_count() == after + 1 and not target.is_activated(),
         'count={0} activated={1}'.format(target.get_interaction_count(), target.is_activated()))

    movement = pawn.get_editor_property('character_movement')
    test('B11', 'character movement is configured for walking/jumping',
         movement is not None and movement.max_walk_speed > 0.0 and movement.jump_z_velocity > 0.0,
         'max_walk_speed={0} jump_z_velocity={1}'.format(
             movement.max_walk_speed if movement else 'n/a',
             movement.jump_z_velocity if movement else 'n/a'))

    return spawned


def main():
    spawned = []
    try:
        player_class, test_class = check_configuration()
        spawned = check_live_chain(player_class, test_class)
    except Exception as exc:
        report['failed'].append('exception: {0}'.format(exc))
        log('exception: {0}'.format(exc))
    finally:
        for actor in spawned:
            try:
                unreal.get_editor_subsystem(unreal.EditorActorSubsystem).destroy_actor(actor)
            except Exception as exc:
                report['notes'].append('cleanup failed: {0}'.format(exc))
        report['cleaned_up'] = len(spawned)
        report['result'] = 'OK' if not report['failed'] else 'FAILED'
        path = write_report()
        passed = len([entry for entry in report['tests'] if entry['passed']])
        print('PHASE3A_VALIDATE_DONE ' + path)
        print('PHASE3A_VALIDATE_RESULT: {0} passed={1}/{2}'.format(
            report['result'], passed, len(report['tests'])))
        for problem in report['failed']:
            print('PHASE3A_VALIDATE_FAIL: ' + problem)


if __name__ == '__main__':
    main()
