# -*- coding: utf-8 -*-
"""Phase 3A - discovery #2: node authoring + level/PIE automation surface.

Read-only introspection; writes a JSON report into <Project>/Saved/Phase3A/.
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


KEYWORDS = ('Graph', 'Node', 'Pin', 'Widget', 'Level', 'Blueprint', 'Automation',
            'Test', 'Interface', 'Input', 'Asset', 'Subobject', 'Actor')

CLASSES = ('LevelEditorSubsystem', 'EditorLevelLibrary', 'AutomationLibrary',
           'EditorUtilitySubsystem', 'EditorActorSubsystem', 'EditorAssetSubsystem',
           'AssetTools', 'WidgetBlueprint', 'WidgetTree', 'PanelWidget', 'TextBlock',
           'CanvasPanel', 'StaticMeshActor', 'DirectionalLight', 'SkyLight',
           'ExponentialHeightFog', 'PlayerStart', 'StaticMeshComponent',
           'K2Node_CallFunction', 'K2Node_Event', 'K2Node_VariableGet',
           'K2Node_VariableSet', 'K2Node_ConstructObjectFromClass', 'EdGraphNode',
           'EdGraphPinType', 'Blueprint', 'FunctionGraph', 'DataAsset',
           'PrimaryDataAsset', 'ActorComponent', 'SceneComponent', 'BoxComponent',
           'LevelSequence', 'EditorUtilityWidget', 'EditorFilterLibrary')


def collect():
    data = {'timestamp': datetime.now().isoformat(timespec='seconds')}
    by_keyword = {}
    for keyword in KEYWORDS:
        matches = sorted([n for n in dir(unreal) if keyword.lower() in n.lower()])
        by_keyword[keyword] = matches[:120]
    data['classes_by_keyword'] = by_keyword

    for cls in CLASSES:
        data['members_' + cls] = names(getattr(unreal, cls)) if hasattr(unreal, cls) else None
    return data


def main():
    data = collect()
    rel = unreal.Paths.project_saved_dir() + 'Phase3A/'
    out_dir = unreal.Paths.convert_relative_path_to_full(rel)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    path = os.path.join(out_dir, 'phase3a_discovery2.json')
    with open(path, 'w') as handle:
        json.dump(data, handle, indent=2)
    print('PHASE3A_DISCOVERY2_DONE ' + path)
    print('node-ish classes: {0}'.format(len(data['classes_by_keyword'].get('Node', []))))
    print('level editor subsystem present: {0}'.format(data['members_LevelEditorSubsystem'] is not None))


if __name__ == '__main__':
    main()
