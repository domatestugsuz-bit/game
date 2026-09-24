# -*- coding: utf-8 -*-
"""Phase 5B step 3 - dump every mapping of the project input contexts, with keys,
triggers and modifiers, using the non-deprecated UE 5.8 property
(InputMappingContext.default_key_mappings.mappings).

Read-only. Writes Saved/Phase5B/phase5b_imc_detail.json.
"""

import json
import os

import unreal

CONTEXTS = ['/Game/Input/IMC_Default', '/Game/Input/IMC_MouseLook', '/Game/Game/Input/IMC_Game']

report = {'notes': []}


def log(message):
    print('PHASE5B-DETAIL: ' + str(message))


def field(entry, name):
    try:
        return entry.get_editor_property(name)
    except Exception as exc:
        return 'ERR: {0}'.format(exc)


def key_name(key):
    for accessor in ('get_editor_property', 'get_fname'):
        try:
            value = key.get_editor_property('key_name') if accessor == 'get_editor_property' else key.get_fname()
            if value:
                return str(value)
        except Exception:
            continue
    return str(key)


def object_names(items):
    result = []
    try:
        for item in items:
            try:
                result.append(item.get_class().get_name() + ':' + item.get_name())
            except Exception:
                result.append(str(item))
    except Exception as exc:
        result.append('ERR: {0}'.format(exc))
    return result


def dump(path):
    context = unreal.EditorAssetLibrary.load_asset(path)
    if context is None:
        return {'path': path, 'found': False}
    data = context.get_editor_property('default_key_mappings')
    rows = []
    for entry in list(data.mappings):
        rows.append({
            'action': str(field(entry, 'action')).rsplit('.', 1)[-1],
            'key': key_name(field(entry, 'key')),
            'triggers': object_names(field(entry, 'triggers')),
            'modifiers': object_names(field(entry, 'modifiers')),
        })
    return {'path': path, 'found': True, 'count': len(rows), 'mappings': rows}


def main():
    out_dir = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir() + 'Phase5B/')
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    report['contexts'] = [dump(path) for path in CONTEXTS]
    for context in report['contexts']:
        log('{0} ({1} mappings)'.format(context['path'], context.get('count', 'missing')))
        for row in context.get('mappings', []):
            log('    {0} <- {1} | triggers={2} | modifiers={3}'.format(
                row['action'], row['key'], row['triggers'], row['modifiers']))
    path = os.path.join(out_dir, 'phase5b_imc_detail.json')
    with open(path, 'w') as handle:
        json.dump(report, handle, indent=2)
    print('PHASE5B_DETAIL_DONE ' + path)


if __name__ == '__main__':
    main()
