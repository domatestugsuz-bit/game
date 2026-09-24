# -*- coding: utf-8 -*-
"""Phase 7 - deep input probe: why does the mouse turn nothing in game?

Read only. Prints, for every relevant InputAction, its value type and triggers (the C++
OnLook() bails out unless the action's value type is Axis2D), and for every mapping in
IMC_Game / IMC_Default / IMC_MouseLook the key, the target action, the triggers and the
modifiers (with the Negate axes). Also prints which InputActions the BP_PlayerCharacter CDO
actually assigned, because SetupPlayerInputComponent only binds non null actions.
"""

import json
import os

import unreal

LINES = []
ACTION_PATHS = [
    '/Game/Game/Input/IA_Look',
    '/Game/Game/Input/IA_Move',
    '/Game/Game/Input/IA_Jump',
    '/Game/Game/Input/IA_Interact',
    '/Game/Game/Input/IA_MouseLook',
    '/Game/Input/IA_Look',
    '/Game/Input/IA_Move',
    '/Game/Input/IA_MouseLook',
    '/Game/Input/IMC_Default',
    '/Game/Input/IMC_MouseLook',
]
CONTEXT_PATHS = ['/Game/Game/Input/IMC_Game', '/Game/Game/Input/IMC_Default', '/Game/Game/Input/IMC_MouseLook',
                 '/Game/Input/IMC_Default', '/Game/Input/IMC_MouseLook']


def log(message):
    LINES.append(str(message))
    print('P8PROBE: ' + str(message))


def enum_text(value):
    text = str(value)
    return text.split('::')[-1].split('.')[-1]


def describe_action(path):
    action = unreal.EditorAssetLibrary.load_asset(path)
    if action is None:
        return
    facts = {'path': path}
    for prop in ('value_type', 'b_consume_input', 'trigger_when_paused', 'b_trigger_when_paused'):
        try:
            value = action.get_editor_property(prop)
            facts[prop] = enum_text(value) if prop == 'value_type' else value
        except Exception:
            continue
    try:
        triggers = action.get_editor_property('triggers')
        facts['triggers'] = [enum_text(trigger.get_class().get_name()) for trigger in triggers]
    except Exception:
        pass
    log('action ' + json.dumps(facts, default=str))


def describe_context(path):
    context = unreal.EditorAssetLibrary.load_asset(path)
    if context is None:
        log('context missing ' + path)
        return
    mappings = []
    for prop in ('default_key_mappings', 'mappings'):
        try:
            value = context.get_editor_property(prop)
        except Exception:
            continue
        inner = getattr(value, 'mappings', None)
        if inner is None:
            continue
        if len(inner) == 0:
            continue
        for mapping in inner:
            entry = {}
            try:
                action = mapping.get_editor_property('action')
                entry['action'] = action.get_name() if action else None
            except Exception as exc:
                entry['action'] = 'err:' + str(exc)
            try:
                key = mapping.get_editor_property('key')
                entry['key'] = enum_text(key.get_editor_property('key_name')) if key else None
            except Exception as exc:
                entry['key'] = 'err:' + str(exc)
            try:
                triggers = mapping.get_editor_property('triggers')
                entry['triggers'] = [enum_text(trigger.get_class().get_name()) for trigger in triggers]
            except Exception:
                entry['triggers'] = []
            try:
                modifiers = mapping.get_editor_property('modifiers')
                described = []
                for modifier in modifiers:
                    name = enum_text(modifier.get_class().get_name())
                    axes = {}
                    for axis in ('x', 'y', 'z'):
                        try:
                            axes[axis] = modifier.get_editor_property(axis)
                        except Exception:
                            pass
                    described.append({'name': name, 'axes': axes})
                entry['modifiers'] = described
            except Exception:
                entry['modifiers'] = []
            mappings.append(entry)
        log('context {0} (via {1}): {2}'.format(path, prop, json.dumps(mappings, default=str)))
        return
    log('context {0}: no readable mappings'.format(path))


def describe_blueprint_actions():
    names = [name for name in unreal.EditorAssetLibrary.list_assets('/Game/Game', True, False)
             if 'PlayerCharacter' in name and name.endswith('.BP_PlayerCharacter')]
    if not names:
        names = [name for name in unreal.EditorAssetLibrary.list_assets('/Game/Game', True, False)
                 if 'PlayerCharacter' in name]
    log('candidate blueprints: {0}'.format(names[:5]))
    for name in names[:3]:
        blueprint = unreal.EditorAssetLibrary.load_asset(name)
        if blueprint is None:
            continue
        try:
            generated = blueprint.generated_class()
        except Exception as exc:
            log('{0}: generated_class failed: {1}'.format(name, exc))
            continue
        default = unreal.get_default_object(generated)
        if default is None:
            continue
        assigned = {}
        for prop in ('move_action', 'look_action', 'jump_action', 'interact_action',
                     'default_mapping_context'):
            try:
                value = default.get_editor_property(prop)
                assigned[prop] = value.get_name() if value else None
            except Exception as exc:
                assigned[prop] = 'err:' + str(exc)
        log('{0} CDO: {1}'.format(name, json.dumps(assigned, default=str)))


for path in ACTION_PATHS:
    describe_action(path)
for path in CONTEXT_PATHS:
    describe_context(path)
describe_blueprint_actions()
log('DONE')

try:
    out_dir = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir() + 'Phase7/')
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    with open(os.path.join(out_dir, 'phase7_input_deep_probe.json'), 'w') as handle:
        json.dump({'lines': LINES}, handle, indent=2)
    print('P8PROBE_REPORT ' + os.path.join(out_dir, 'phase7_input_deep_probe.json'))
except Exception as exc:  # noqa: BLE001
    print('P8PROBE_REPORT_FAILED ' + str(exc))
