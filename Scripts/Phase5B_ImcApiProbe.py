# -*- coding: utf-8 -*-
"""Phase 5B step 2 - find where UE 5.8 stores the key mappings of a mapping context.

The deprecated 'mappings' array now returns empty; this probe lists the object's
python-visible properties and tries the documented replacement (default key mappings).
Read-only. Prints the findings and writes Saved/Phase5B/phase5b_imc_api.json.
"""

import json
import os

import unreal

report = {'notes': []}


def log(message):
    print('PHASE5B-API: ' + str(message))


def names_of(obj):
    try:
        return sorted(item for item in dir(obj) if not item.startswith('_'))
    except Exception as exc:
        return ['ERR: {0}'.format(exc)]


def try_read(obj, key):
    try:
        return obj.get_editor_property(key)
    except Exception as exc:
        return 'ERR: {0}'.format(exc)


def describe(value, depth=0):
    if depth > 2:
        return str(value)[:200]
    if isinstance(value, (int, float, bool, str)) or value is None:
        return value
    text = str(value)
    if 'ERR:' in text:
        return text
    return {'type': type(value).__name__, 'str': text[:160], 'attrs': names_of(value)[:60]}


def main():
    out_dir = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir() + 'Phase5B/')
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    imc = unreal.EditorAssetLibrary.load_asset('/Game/Game/Input/IMC_Game')
    report['imc_object_attrs'] = names_of(imc)
    report['class_attrs'] = names_of(unreal.InputMappingContext)
    for key in ('mappings', 'default_key_mappings', 'key_mappings', 'player_mappable_key_settings'):
        value = try_read(imc, key)
        report['read_' + key] = describe(value)
        log('{0} -> {1}'.format(key, str(report['read_' + key])[:300]))

    # the mapping struct itself, when one can be reached
    struct = try_read(imc, 'default_key_mappings')
    if not isinstance(struct, str):
        for key in ('mappings', 'key_mappings', 'default_key_mappings'):
            value = try_read(struct, key)
            report['struct_' + key] = describe(value)
            log('default_key_mappings.{0} -> {1}'.format(key, str(report['struct_' + key])[:300]))

    # template context for comparison
    template = unreal.EditorAssetLibrary.load_asset('/Game/Input/IMC_Default')
    report['template_default_key_mappings'] = describe(try_read(template, 'default_key_mappings'))

    path = os.path.join(out_dir, 'phase5b_imc_api.json')
    with open(path, 'w') as handle:
        json.dump(report, handle, indent=2)
    print('PHASE5B_API_DONE ' + path)


if __name__ == '__main__':
    main()
