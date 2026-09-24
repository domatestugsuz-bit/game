# -*- coding: utf-8 -*-
"""Phase 5B - read-only diagnosis of the project input setup.

Answers one question: which keys/axes are actually mapped to IA_Move / IA_Look in the
mapping context that BP_PlayerCharacter registers? Walking works in PIE but looking
around does not, so the mapping (or the mouse capture) must be incomplete.

Run in EDITOR mode (headless):
  UnrealEditor-Cmd.exe "<Project>.uproject" -ExecutePythonScript="<this file>"
                       -unattended -nosplash -nullrhi -stdout -NoSourceControl
"""

import json
import os
from datetime import datetime

import unreal

REPORT_REL = 'Phase5B/'
REPORT_NAME = 'phase5b_input_probe.json'

report = {
    'phase': 'Phase 5B - input diagnosis',
    'timestamp': datetime.now().isoformat(timespec='seconds'),
    'notes': [],
}


def log(message):
    print('PHASE5B-IN: ' + str(message))


def prop(obj, name):
    """Reads a property that may only exist in one of the two Python naming styles."""
    try:
        return obj.get_editor_property(name)
    except Exception:
        pass
    try:
        return getattr(obj, name)
    except Exception:
        return None


def name_of(value):
    if value is None:
        return None
    for accessor in ('get_path_name', 'get_name'):
        try:
            return str(getattr(value, accessor)())
        except Exception:
            continue
    try:
        return str(value)
    except Exception:
        return '<unprintable>'


def key_of(value):
    if value is None:
        return None
    key_name = prop(value, 'key_name')
    return str(key_name) if key_name else name_of(value)


def dump_mapping(mapping):
    return {
        'action': name_of(prop(mapping, 'action')),
        'key': key_of(prop(mapping, 'key')),
        'triggers': [name_of(item) for item in (prop(mapping, 'triggers') or [])],
        'modifiers': [name_of(item) for item in (prop(mapping, 'modifiers') or [])],
    }


def dump_context(path):
    context = unreal.EditorAssetLibrary.load_asset(path)
    if context is None:
        return {'path': path, 'found': False}
    mappings = prop(context, 'mappings')
    rows = []
    try:
        iterator = list(mappings)
    except Exception as exc:
        iterator = []
        report['notes'].append('{0}: mappings not iterable ({1})'.format(path, exc))
    for mapping in iterator:
        try:
            rows.append(dump_mapping(mapping))
        except Exception as exc:
            report['notes'].append('{0}: mapping dump failed ({1})'.format(path, exc))
    return {'path': path, 'found': True, 'count': len(rows), 'mappings': rows}


def dump_action(path):
    action = unreal.EditorAssetLibrary.load_asset(path)
    if action is None:
        return {'path': path, 'found': False}
    return {'path': path, 'found': True, 'value_type': name_of(prop(action, 'value_type'))}


def dump_settings():
    result = {}
    try:
        settings = unreal.InputSettings.get_input_settings()
    except Exception as exc:
        return {'error': str(exc)}
    for key in ('b_capture_mouse_on_launch', 'default_viewport_mouse_capture_mode',
                'default_viewport_mouse_lock_mode', 'b_enable_mouse_smoothing',
                'mouse_smoothing', 'b_use_mouse_for_touch', 'b_enable_legacy_input_scales',
                'default_player_input_class', 'default_input_component_class',
                'b_always_show_touch_interface', 'b_enable_fov_scaling', 'fov_scale'):
        result[key] = name_of(prop(settings, key))
    return result


def main():
    out_dir = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir() + REPORT_REL)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    # ---- the pawn blueprint and what it registers --------------------------------
    bp = unreal.EditorAssetLibrary.load_asset('/Game/Game/Characters/Player/BP_PlayerCharacter')
    cdo = None
    if bp is not None:
        try:
            cdo = unreal.get_default_object(bp.generated_class())
        except Exception as exc:
            report['notes'].append('CDO lookup failed: {0}'.format(exc))
    if cdo is not None:
        report['player_cdo'] = {
            'default_mapping_context': name_of(prop(cdo, 'default_mapping_context')),
            'move_action': name_of(prop(cdo, 'move_action')),
            'look_action': name_of(prop(cdo, 'look_action')),
            'jump_action': name_of(prop(cdo, 'jump_action')),
            'interact_action': name_of(prop(cdo, 'interact_action')),
        }
    else:
        report['player_cdo'] = {'error': 'BP_PlayerCharacter CDO not found'}

    # ---- mapping contexts --------------------------------------------------------
    report['contexts'] = [
        dump_context('/Game/Game/Input/IMC_Game'),
        dump_context('/Game/Input/IMC_Default'),
        dump_context('/Game/Input/IMC_MouseLook'),
    ]

    # ---- actions -----------------------------------------------------------------
    report['actions'] = [
        dump_action('/Game/Input/Actions/IA_Move'),
        dump_action('/Game/Input/Actions/IA_Look'),
        dump_action('/Game/Input/Actions/IA_MouseLook'),
        dump_action('/Game/Input/Actions/IA_Jump'),
        dump_action('/Game/Game/Input/IA_Interact'),
    ]

    # ---- project input settings ---------------------------------------------------
    report['settings'] = dump_settings()

    # ---- the game mode the level runs --------------------------------------------
    gm_bp = unreal.EditorAssetLibrary.load_asset('/Game/Game/Core/BP_GameMode')
    if gm_bp is not None:
        try:
            gm_cdo = unreal.get_default_object(gm_bp.generated_class())
            report['game_mode'] = {
                'default_pawn_class': name_of(prop(gm_cdo, 'default_pawn_class')),
                'player_controller_class': name_of(prop(gm_cdo, 'player_controller_class')),
            }
        except Exception as exc:
            report['game_mode'] = {'error': str(exc)}

    report['result'] = 'OK' if not report['notes'] else 'OK_WITH_NOTES'
    path = os.path.join(out_dir, REPORT_NAME)
    with open(path, 'w') as handle:
        json.dump(report, handle, indent=2)

    for context in report['contexts']:
        log('{0}: {1} mappings'.format(context['path'], context.get('count', 'missing')))
        for mapping in context.get('mappings', []):
            log('    {0} <- {1} | mods={2} | triggers={3}'.format(
                mapping['action'], mapping['key'], mapping['modifiers'], mapping['triggers']))
    log('player cdo: {0}'.format(report['player_cdo']))
    for action in report['actions']:
        log('action {0}: {1}'.format(action['path'], action.get('value_type', 'missing')))
    log('settings: {0}'.format(report['settings']))
    log('game mode: {0}'.format(report.get('game_mode', 'n/a')))
    print('PHASE5B_PROBE_DONE ' + path)


if __name__ == '__main__':
    main()
