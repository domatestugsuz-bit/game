# -*- coding: utf-8 -*-
"""Phase 5B - final input mapping pass.

Root cause (see Saved/Phase5B/phase5b_imc_detail.json):
  * BP_PlayerCharacter registers /Game/Game/Input/IMC_Game, which contained only
    "E -> IA_Interact" (twice).
  * The template contexts (IMC_Default / IMC_MouseLook) are registered by
    BP_FirstPersonPlayerController: they map WASD, arrows, Space and the gamepad, and the
    mouse is mapped to IA_MouseLook (which the character never binds).
  * Nothing therefore mapped "Mouse XY 2D-Axis" to IA_Look: walking worked, looking around
    was impossible - the reported touchpad symptom.

This script makes IMC_Game authoritative for looking and interaction, with no duplicate
mappings that could double the movement input:
  * keeps exactly one "IA_Interact <- E"
  * adds "IA_Look <- Mouse2D" with the template's Negate modifier (cloned from
    IMC_MouseLook, so the pitch direction matches the template exactly)
  * removes every other mapping in IMC_Game
Idempotent. Run in EDITOR mode (headless).
"""

import json
import os
from datetime import datetime

import unreal

IMC_PATH = '/Game/Game/Input/IMC_Game'
MOUSE_TEMPLATE_PATH = '/Game/Input/IMC_MouseLook'
IA_LOOK_PATH = '/Game/Input/Actions/IA_Look'
IA_INTERACT_PATH = '/Game/Game/Input/IA_Interact'
REPORT_REL = 'Phase5B/'
REPORT_NAME = 'phase5b_input_mappings.json'

report = {'phase': 'Phase 5B - input mapping cleanup', 'timestamp': datetime.now().isoformat(timespec='seconds'),
          'notes': []}


def log(message):
    print('PHASE5B-MAP: ' + str(message))


def entries_of(context):
    data = context.get_editor_property('default_key_mappings')
    return data, list(data.mappings)


def field(entry, name):
    try:
        return entry.get_editor_property(name)
    except Exception:
        return None


def action_name(entry):
    action = field(entry, 'action')
    if action is None:
        return None
    try:
        return action.get_name()
    except Exception:
        return str(action).rsplit('/', 1)[-1]


def key_name(entry):
    key = field(entry, 'key')
    if key is None:
        return None
    try:
        value = key.get_editor_property('key_name')
        if value:
            return str(value)
    except Exception:
        pass
    try:
        value = key.get_fname()
        if value:
            return str(value)
    except Exception:
        pass
    return str(key)


def describe(entries):
    return ['{0} <- {1}'.format(action_name(entry), key_name(entry)) for entry in entries]


def modifier_details(entry):
    rows = []
    for modifier in (field(entry, 'modifiers') or []):
        row = {'class': modifier.get_class().get_name()}
        for flag in ('b_x', 'b_y', 'b_z'):
            try:
                row[flag] = bool(modifier.get_editor_property(flag))
            except Exception:
                pass
        rows.append(row)
    return rows


def set_array(struct, field_name, values):
    """Writes a struct array back, whichever write path this build accepts."""
    try:
        struct.set_editor_property(field_name, values)
        return 'set_editor_property'
    except Exception as first:
        try:
            setattr(struct, field_name, values)
            return 'setattr'
        except Exception as second:
            try:
                current = getattr(struct, field_name)
                current.clear()
                for value in values:
                    current.append(value)
                return 'clear+append'
            except Exception as third:
                raise RuntimeError('array write failed: {0} / {1} / {2}'.format(first, second, third))


def main():
    out_dir = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir() + REPORT_REL)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    context = unreal.EditorAssetLibrary.load_asset(IMC_PATH)
    mouse_template = unreal.EditorAssetLibrary.load_asset(MOUSE_TEMPLATE_PATH)
    ia_look = unreal.EditorAssetLibrary.load_asset(IA_LOOK_PATH)
    if context is None or mouse_template is None or ia_look is None:
        report['result'] = 'FAILED'
        report['notes'].append('missing asset: context={0} template={1} look={2}'.format(
            context, mouse_template, ia_look))
    else:
        data, entries = entries_of(context)
        report['before'] = describe(entries)

        keep = []
        seen = set()
        for entry in entries:
            pair = (action_name(entry), key_name(entry))
            if pair == ('IA_Interact', 'E') and pair not in seen:
                keep.append(entry)
                seen.add(pair)

        if ('IA_Look', 'Mouse2D') not in seen:
            _, template_entries = entries_of(mouse_template)
            source = None
            for entry in template_entries:
                if key_name(entry) == 'Mouse2D':
                    source = entry
                    break
            if source is None:
                report['notes'].append('no Mouse2D mapping in {0}'.format(MOUSE_TEMPLATE_PATH))
            else:
                clone = source
                try:
                    clone.set_editor_property('action', ia_look)
                except Exception as exc:
                    report['notes'].append('could not retarget the cloned mapping: {0}'.format(exc))
                keep.append(clone)
                seen.add(('IA_Look', 'Mouse2D'))
                report['mouse_modifiers'] = modifier_details(clone)

        report['kept'] = describe(keep)
        log('IMC_Game before: {0}'.format(report['before']))
        log('keeping: {0}'.format(report['kept']))

        context.modify()
        try:
            mode = set_array(data, 'mappings', keep)
            report['write_path'] = mode
        except Exception as exc:
            report['notes'].append('could not rewrite the mapping array: {0}'.format(exc))
        try:
            context.set_editor_property('default_key_mappings', data)
        except Exception as exc:
            report['notes'].append('could not write default_key_mappings back: {0}'.format(exc))

        try:
            report['saved'] = bool(unreal.EditorAssetLibrary.save_loaded_asset(context, only_if_is_dirty=False))
        except Exception as exc:
            report['saved'] = False
            report['notes'].append('save failed: {0}'.format(exc))

        _, after = entries_of(context)
        report['after'] = describe(after)
        report['result'] = 'OK' if not report['notes'] else 'FAILED'
        log('IMC_Game after: {0}'.format(report['after']))

        look = [item for item in report['after'] if item.startswith('IA_Look <-')]
        report['look_keys'] = look
        if not look:
            report['notes'].append('IA_Look still has no mapping')
        if len(report['after']) != len(set(report['after'])):
            report['notes'].append('duplicate mappings remain: {0}'.format(report['after']))

    path = os.path.join(out_dir, REPORT_NAME)
    with open(path, 'w') as handle:
        json.dump(report, handle, indent=2)
    log('look keys: {0}'.format(report.get('look_keys')))
    log('mouse modifiers: {0}'.format(report.get('mouse_modifiers')))
    log('notes: {0}'.format(report['notes']))
    print('PHASE5B_MAP_DONE ' + path)


if __name__ == '__main__':
    main()
