# -*- coding: utf-8 -*-
"""Phase 5B - make the player input complete (look + move + jump + interact).

Diagnosis (Saved/Phase5B/phase5b_input_probe.json): BP_PlayerCharacter registers
/Game/Game/Input/IMC_Game, but that context was created with a single mapping
(E -> IA_Interact). Walking worked through the engine's fallback, looking around never
did, which is exactly the reported "can walk, cannot look with the touchpad" symptom.

This script copies the template's own mappings for IA_Move / IA_Look / IA_Jump into
IMC_Game (same keys, same modifiers - no hand-built modifiers) and leaves the existing
IA_Interact mapping in place. Idempotent: a mapping is only added when the context does
not already have that action+key pair.

Run in EDITOR mode (headless):
  UnrealEditor-Cmd.exe "<Project>.uproject" -ExecutePythonScript="<this file>"
                       -unattended -nosplash -nullrhi -stdout -NoSourceControl
"""

import json
import os
from datetime import datetime

import unreal

IMC_PATH = '/Game/Game/Input/IMC_Game'
TEMPLATE_PATH = '/Game/Input/IMC_Default'
COPY_ACTIONS = ('IA_Move', 'IA_Look', 'IA_Jump')
REPORT_REL = 'Phase5B/'
REPORT_NAME = 'phase5b_input_fix.json'

report = {
    'phase': 'Phase 5B - input mapping fix',
    'timestamp': datetime.now().isoformat(timespec='seconds'),
    'notes': [],
    'added': [],
    'skipped': [],
}


def log(message):
    print('PHASE5B-FIX: ' + str(message))


def entries_of(context):
    """Returns (struct, list of mapping entries) using the UE 5.8 property."""
    data = context.get_editor_property('default_key_mappings')
    return data, list(data.mappings)


def entry_action_name(entry):
    try:
        action = entry.get_editor_property('action')
    except Exception:
        return None
    if action is None:
        return None
    try:
        return action.get_name()
    except Exception:
        return str(action).rsplit('/', 1)[-1]


def entry_key_name(entry):
    try:
        key = entry.get_editor_property('key')
    except Exception:
        return '?'
    try:
        name = key.get_editor_property('key_name')
        if name:
            return str(name)
    except Exception:
        pass
    try:
        name = key.get_fname()
        if name:
            return str(name)
    except Exception:
        pass
    return str(key)


def describe(entries):
    return ['{0} <- {1}'.format(entry_action_name(entry), entry_key_name(entry)) for entry in entries]


def main():
    out_dir = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir() + REPORT_REL)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    context = unreal.EditorAssetLibrary.load_asset(IMC_PATH)
    template = unreal.EditorAssetLibrary.load_asset(TEMPLATE_PATH)
    if context is None or template is None:
        report['result'] = 'FAILED'
        report['notes'].append('missing asset: context={0} template={1}'.format(context, template))
    else:
        data, existing = entries_of(context)
        report['before'] = describe(existing)
        _, template_entries = entries_of(template)
        report['template'] = describe(template_entries)
        log('IMC_Game before: {0}'.format(report['before']))
        log('IMC_Default: {0}'.format(report['template']))

        have = set()
        for entry in existing:
            have.add((entry_action_name(entry), entry_key_name(entry)))

        context.modify()
        added = 0
        for entry in template_entries:
            action_name = entry_action_name(entry)
            key_name = entry_key_name(entry)
            if action_name not in COPY_ACTIONS:
                report['skipped'].append('{0} <- {1} (not in scope)'.format(action_name, key_name))
                continue
            if (action_name, key_name) in have:
                report['skipped'].append('{0} <- {1} (already mapped)'.format(action_name, key_name))
                continue
            try:
                data.mappings.append(entry)
                have.add((action_name, key_name))
                report['added'].append('{0} <- {1}'.format(action_name, key_name))
                added += 1
            except Exception as exc:
                report['notes'].append('append failed for {0} <- {1}: {2}'.format(action_name, key_name, exc))

        if added:
            try:
                context.set_editor_property('default_key_mappings', data)
            except Exception as exc:
                report['notes'].append('set default_key_mappings failed: {0}'.format(exc))
            saved = False
            try:
                saved = unreal.EditorAssetLibrary.save_loaded_asset(context, only_if_is_dirty=False)
            except Exception as exc:
                report['notes'].append('save failed: {0}'.format(exc))
            report['saved'] = bool(saved)
            log('added {0} mappings, saved={1}'.format(added, saved))
        else:
            report['saved'] = False
            log('nothing to add')

        # read back to prove the data is in the asset
        _, after = entries_of(context)
        report['after'] = describe(after)
        log('IMC_Game after: {0}'.format(report['after']))

        missing = [name for name in ('IA_Move', 'IA_Look', 'IA_Jump', 'IA_Interact')
                   if not any(item.startswith(name + ' <-') for item in report['after'])]
        report['missing_actions'] = missing
        report['look_keys'] = [item for item in report['after'] if item.startswith('IA_Look <-')]
        report['move_keys'] = [item for item in report['after'] if item.startswith('IA_Move <-')]
        if missing:
            report['notes'].append('still missing actions: {0}'.format(missing))
        if not report['look_keys']:
            report['notes'].append('IA_Look has no mapping: looking around cannot work')

    report['result'] = 'FAILED' if report['notes'] else 'OK'
    path = os.path.join(out_dir, REPORT_NAME)
    with open(path, 'w') as handle:
        json.dump(report, handle, indent=2)
    log('missing actions: {0}'.format(report.get('missing_actions')))
    log('look keys: {0}'.format(report.get('look_keys')))
    log('move keys: {0}'.format(report.get('move_keys')))
    print('PHASE5B_FIX_DONE ' + path)


if __name__ == '__main__':
    main()
