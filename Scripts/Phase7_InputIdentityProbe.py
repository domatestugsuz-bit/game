# -*- coding: utf-8 -*-
"""Phase 7 - resolve the identity of the input actions.

The mouse mapping fires nothing even though IMC_Game maps Mouse2D to IA_Look and the pawn
binds IA_Look. Two assets with the same short name in different folders are different objects,
so the mapping would fire and the pawn would never hear about it. This probe prints the FULL
paths of every candidate action and of the actions the blueprint/IMC actually point at.
"""

import json
import os

import unreal

LINES = []


def log(message):
    LINES.append(str(message))
    print('P9PROBE: ' + str(message))


def all_assets():
    found = []
    for folder in ('/Game',):
        try:
            found.extend(unreal.EditorAssetLibrary.list_assets(folder, True, False))
        except Exception as exc:
            log('list_assets failed: {0}'.format(exc))
    return found


def report_candidates():
    names = ('IA_Look', 'IA_Move', 'IA_Jump', 'IA_Interact', 'IA_MouseLook', 'IMC_Game', 'IMC_Default')
    for asset in all_assets():
        short = asset.split('.')[-1]
        if short in names or 'IA_Look' in short:
            log('asset {0}'.format(asset))


def report_blueprint():
    path = '/Game/Game/Characters/Player/BP_PlayerCharacter.BP_PlayerCharacter'
    blueprint = unreal.EditorAssetLibrary.load_asset(path)
    if blueprint is None:
        log('blueprint missing ' + path)
        return
    generated = blueprint.generated_class()
    default = unreal.get_default_object(generated)
    facts = {}
    for prop in ('move_action', 'look_action', 'jump_action', 'interact_action', 'default_mapping_context'):
        try:
            value = default.get_editor_property(prop)
            facts[prop] = value.get_path_name() if value else None
        except Exception as exc:
            facts[prop] = 'err:' + str(exc)
    log('CDO ' + json.dumps(facts))


def report_context(path):
    context = unreal.EditorAssetLibrary.load_asset(path)
    if context is None:
        return
    try:
        mappings = context.get_editor_property('default_key_mappings').mappings
    except Exception as exc:
        log('{0}: mapping read failed: {1}'.format(path, exc))
        return
    rows = []
    for mapping in mappings:
        action = mapping.get_editor_property('action')
        key = mapping.get_editor_property('key')
        rows.append({'action': action.get_path_name() if action else None,
                     'key': str(key.get_editor_property('key_name')) if key else None})
    log('IMC {0} {1}'.format(context.get_path_name(), json.dumps(rows)))


report_candidates()
report_blueprint()
for candidate in ('/Game/Game/Input/IMC_Game', '/Game/Input/IMC_Default', '/Game/Input/IMC_MouseLook'):
    report_context(candidate)

# the actions the pawn actually uses (the earlier probe looked in the wrong folder and printed
# nothing for them, which hid the one fact that matters: the value type the C++ guard checks)
for path in ('/Game/Input/Actions/IA_Look', '/Game/Input/Actions/IA_Move', '/Game/Input/Actions/IA_Jump',
             '/Game/Input/Actions/IA_MouseLook', '/Game/Game/Input/IA_Interact'):
    action = unreal.EditorAssetLibrary.load_asset(path)
    if action is None:
        log('ACTION {0}: missing'.format(path))
        continue
    facts = {'path': path}
    for prop in ('value_type', 'b_consume_input', 'trigger_when_paused', 'b_trigger_when_paused'):
        try:
            value = action.get_editor_property(prop)
            facts[prop] = str(value).split('.')[-1] if prop == 'value_type' else value
        except Exception:
            continue
    for prop in ('triggers', 'modifiers'):
        try:
            entries = action.get_editor_property(prop)
            facts[prop] = [str(entry.get_class().get_name()) for entry in entries]
        except Exception:
            continue
    log('ACTION ' + json.dumps(facts, default=str))

try:
    out_dir = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir() + 'Phase7/')
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    with open(os.path.join(out_dir, 'phase7_input_identity.json'), 'w') as handle:
        json.dump({'lines': LINES}, handle, indent=2)
    print('P9PROBE_REPORT written')
except Exception as exc:  # noqa: BLE001
    print('P9PROBE_REPORT_FAILED ' + str(exc))
