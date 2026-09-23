# -*- coding: utf-8 -*-
"""Read-only exposure investigation, part 2: blueprint / camera manager surfaces.

Checks every place a project could hide an exposure value that is NOT in an .ini:
  * the template camera manager blueprint (may drive camera post process)
  * the template first person character (components + post process overrides)
  * our own gameplay blueprints (any exposed 'exposure' property)
STRICTLY READ ONLY - the JSON report goes to %TEMP%, nothing is saved.
"""

import json
import os

import unreal

BLUEPRINTS = {
    'BP_FirstPersonCameraManager (template)': '/Game/FirstPerson/Blueprints/BP_FirstPersonCameraManager.BP_FirstPersonCameraManager_C',
    'BP_FirstPersonCharacter (template)': '/Game/FirstPerson/Blueprints/BP_FirstPersonCharacter.BP_FirstPersonCharacter_C',
    'BP_FirstPersonGameMode (template)': '/Game/FirstPerson/Blueprints/BP_FirstPersonGameMode.BP_FirstPersonGameMode_C',
    'BP_FirstPersonPlayerController (template)': '/Game/FirstPerson/Blueprints/BP_FirstPersonPlayerController.BP_FirstPersonPlayerController_C',
    'BP_PlayerCharacter (ours)': '/Game/Game/Characters/Player/BP_PlayerCharacter.BP_PlayerCharacter_C',
    'BP_GameMode (ours)': '/Game/Game/Core/BP_GameMode.BP_GameMode_C',
    'BP_InteractionTestObject (ours)': '/Game/Game/Interaction/BP_InteractionTestObject.BP_InteractionTestObject_C',
    'BP_VehicleBase (ours)': '/Game/Game/Vehicles/Base/BP_VehicleBase.BP_VehicleBase_C',
}

report = {'phase': 'exposure investigation part 2 (read only)', 'blueprints': {}, 'notes': []}


def text(value):
    try:
        return str(value)
    except Exception as exc:
        return '<unprintable: {0}>'.format(exc)


def scan_object(obj, label, out):
    """Any exposed property whose name mentions exposure, plus component cameras."""
    try:
        for name in sorted([n for n in dir(obj) if 'exposure' in n.lower() or 'ev100' in n.lower()]):
            try:
                out['{0}:{1}'.format(label, name)] = text(obj.get_editor_property(name))
            except Exception as exc:
                out['{0}:{1}'.format(label, name)] = '<error: {0}>'.format(exc)
    except Exception as exc:
        out['{0}:<dir failed>'.format(label)] = text(exc)


def scan_components(cdo, label, out):
    try:
        for component in cdo.get_components_by_class(unreal.ActorComponent):
            class_name = component.get_class().get_name()
            if 'Camera' in class_name:
                settings = component.get_editor_property('post_process_settings')
                for name in sorted([n for n in dir(settings) if 'exposure' in n.lower()]):
                    try:
                        value = text(settings.get_editor_property(name))
                    except Exception as exc:
                        value = '<error: {0}>'.format(exc)
                    out['{0}/{1}:{2}'.format(label, component.get_name(), name)] = value
            out['{0}/components'.format(label)] = out.get('{0}/components'.format(label), '') + class_name + ','
    except Exception as exc:
        out['{0}:<components failed>'.format(label)] = text(exc)


def main():
    data = {}
    for label, class_path in BLUEPRINTS.items():
        owner_class = unreal.load_class(None, class_path)
        if owner_class is None:
            report['notes'].append('{0}: not found ({1})'.format(label, class_path))
            continue
        cdo = unreal.get_default_object(owner_class)
        scan_object(cdo, label, data)
        scan_components(cdo, label, data)
    report['blueprints'] = data

    out_dir = os.path.join(os.environ.get('TEMP', '.'), 'MyProject_Phase2')
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    path = os.path.join(out_dir, 'exposure_dump2.json')
    with open(path, 'w') as handle:
        json.dump(report, handle, indent=2)
    print('EXPOSURE_DUMP2_DONE ' + path)
    for note in report['notes']:
        print('EXPOSURE_DUMP2_NOTE: ' + note)


if __name__ == '__main__':
    main()
