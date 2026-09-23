# -*- coding: utf-8 -*-
"""Phase 3A - capability discovery for the Unreal Python/Editor automation API.

Read-only: this script only INTROSPECTS the exposed Python API and writes a JSON
report into <Project>/Saved/Phase3A/. It never creates, modifies or deletes assets.

Purpose: determine exactly which parts of the Phase 3A vertical slice can be
automated (asset creation, component addition, input mapping, PIE control) and
which parts require interactive editor work (Blueprint graph authoring).
"""

import json
import os
from datetime import datetime

import unreal


def names(obj):
    try:
        return sorted([n for n in dir(obj) if not n.startswith('_')])
    except Exception as exc:
        return ['<error: {0}>'.format(exc)]


def has_attr(obj, attr):
    return hasattr(obj, attr)


def collect():
    data = {}
    data['engine_version'] = str(unreal.SystemLibrary.get_engine_version())
    data['timestamp'] = datetime.now().isoformat(timespec='seconds')

    # --- asset factories ---------------------------------------------------
    data['factories_all'] = sorted([n for n in dir(unreal) if n.endswith('Factory')])
    for factory in ('BlueprintFactory', 'BlueprintInterfaceFactory', 'WidgetBlueprintFactory',
                    'InputActionFactory', 'InputMappingContextFactory', 'DataAssetFactory',
                    'DataTableFactory', 'ActorFactory', 'WorldFactory', 'LevelFactory',
                    'MaterialFactoryNew', 'StaticMeshFactory'):
        data['factory_' + factory] = names(getattr(unreal, factory)) if hasattr(unreal, factory) else None

    # --- input / enhanced input -------------------------------------------
    for cls in ('InputAction', 'InputMappingContext', 'EnhancedActionKeyMapping', 'InputActionValue'):
        data['class_' + cls] = names(getattr(unreal, cls)) if hasattr(unreal, cls) else None
    data['input_action_value_type'] = names(unreal.InputActionValueType) if hasattr(unreal, 'InputActionValueType') else None
    data['input_action_trigger_classes'] = sorted([n for n in dir(unreal) if 'Trigger' in n])[:40]
    data['key_struct'] = names(unreal.Key) if hasattr(unreal, 'Key') else None

    # --- blueprint authoring surface --------------------------------------
    for cls in ('BlueprintEditorLibrary', 'SubobjectDataSubsystem', 'AddNewSubobjectParams',
                'SubobjectDataHandle', 'EditorAssetLibrary', 'EditorAssetSubsystem',
                'AssetToolsHelpers', 'AssetTools'):
        data['lib_' + cls] = names(getattr(unreal, cls)) if hasattr(unreal, cls) else None

    # --- graph authoring (the critical question) --------------------------
    data['has_EdGraph'] = has_attr(unreal, 'EdGraph')
    data['EdGraph_members'] = names(unreal.EdGraph) if has_attr(unreal, 'EdGraph') else None
    data['has_EdGraphNode'] = has_attr(unreal, 'EdGraphNode')
    data['k2node_classes'] = sorted([n for n in dir(unreal) if n.startswith('K2Node')])[:40]
    data['blueprint_graph_classes'] = sorted([n for n in dir(unreal)
                                              if n in ('EdGraphPinType', 'Blueprint', 'FunctionGraph', 'EdGraphPin')])

    return data


def write_report(data):
    rel = unreal.Paths.project_saved_dir() + 'Phase3A/'
    out_dir = unreal.Paths.convert_relative_path_to_full(rel)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    path = os.path.join(out_dir, 'phase3a_discovery.json')
    with open(path, 'w') as handle:
        json.dump(data, handle, indent=2)
    unreal.log('PHASE3A: discovery report -> {0}'.format(path))
    return path


def main():
    data = collect()
    path = write_report(data)
    print('PHASE3A_DISCOVERY_DONE ' + path)
    print('factories: {0}'.format(len(data['factories_all'])))
    print('K2Node classes exposed: {0}'.format(len(data['k2node_classes'])))
    print('EdGraph exposed: {0}'.format(data['has_EdGraph']))


if __name__ == '__main__':
    main()
