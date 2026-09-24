# -*- coding: utf-8 -*-
"""Phase 5 - probe the Unreal side before the textured house pass.

Answers three questions with evidence instead of assumptions:
  1. which material editing / texture import API this build actually exposes,
  2. what parameters the existing house master material carries (does it already take textures?),
  3. which MI_H_* instances and house static meshes are present, so the new materials can be
     attached to exactly the same slots.

Run:
  Run-Phase4Script.ps1 -Script "...\\Scripts\\Phase5_MaterialProbe.py" -Log <log>
"""

import json
import os

import unreal

MASTER = '/Game/Game/Environment/Home/M_RuralSurface'
ROOT = '/Game/Game/Environment/House'
OUT = 'C:/Users/azize/OneDrive/Belgeler/Unreal Projects/MyProject/Saved/Phase5/phase5_probe.json'


def log(message):
    # print() reaches LogPython: Display in the runner log, unreal.log() does not in this build
    print('P5PROBE: ' + str(message))


def api_names():
    names = [name for name in dir(unreal.MaterialEditingLibrary)
             if 'param' in name.lower() or 'expression' in name.lower() or 'connect' in name.lower()]
    texture_names = [name for name in dir(unreal) if 'Texture' in name and 'Compression' in name]
    return {'material_editing': sorted(names), 'compression_enums': sorted(texture_names)}


def asset_presence():
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    found = {}
    for label, query in (('MI_H', 'MI_H_'), ('house_meshes', 'SM_House_')):
        assets = registry.get_assets_by_path(ROOT, recursive=True)
        names = sorted(str(asset.asset_name) for asset in assets if query in str(asset.asset_name))
        found[label] = names[:40]
        found[label + '_count'] = len(names)
    return found


def master_info():
    material = unreal.load_asset(MASTER)
    if material is None:
        return {'found': False}
    info = {'found': True, 'path': MASTER}
    for key in ('blend_mode', 'shading_model', 'two_sided'):
        try:
            info[key] = str(material.get_editor_property(key))
        except Exception as exc:  # noqa: BLE001
            info[key] = 'n/a: ' + str(exc)[:60]
    try:
        expressions = unreal.MaterialEditingLibrary.get_material_expressions(material)
        info['expressions'] = []
        for expression in expressions:
            info['expressions'].append({
                'class': str(expression.get_class().get_name()),
                'parameter_name': str(expression.get_editor_property('parameter_name'))
                if hasattr(expression, 'get_editor_property') else None})
    except Exception as exc:  # noqa: BLE001
        info['expressions'] = 'n/a: ' + str(exc)[:120]
    return info


def main():
    report = {'api': api_names(), 'master': master_info(), 'assets': asset_presence()}
    log('master found: {0}'.format(report['master'].get('found')))
    log('material editing api: {0}'.format(report['api']['material_editing']))
    log('compression enums: {0}'.format(report['api']['compression_enums']))
    log('MI_H assets: {0}'.format(report['assets'].get('MI_H_count')))
    log('house meshes: {0}'.format(report['assets'].get('house_meshes_count')))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w') as handle:
        json.dump(report, handle, indent=2)
    log('written: ' + OUT)


main()
