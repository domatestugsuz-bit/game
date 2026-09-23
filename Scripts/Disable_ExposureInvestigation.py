# -*- coding: utf-8 -*-
"""Read-only exposure investigation for the MyProject Unreal project.

Dumps every exposure / eye-adaptation related value that actually exists in the
project (levels, cameras, post process volumes) plus the engine defaults, so the
values can be classified as "engine default" vs "set in this project".

STRICTLY READ ONLY: nothing is created, modified or saved inside the project; the
JSON report is written to %TEMP% outside the project folder.
"""

import json
import os

import unreal

LEVELS = ['/Game/Game/Environment/Lvl_GameplayPrototype',
          '/Game/FirstPerson/Lvl_FirstPerson']

CAMERA_BLUEPRINTS = {
    'BP_PlayerCharacter (ours)': '/Game/Game/Characters/Player/BP_PlayerCharacter.BP_PlayerCharacter_C',
    'BP_FirstPersonCharacter (template)': '/Game/FirstPerson/Blueprints/BP_FirstPersonCharacter.BP_FirstPersonCharacter_C',
}

report = {'phase': 'exposure investigation (read only)',
          'engine_default': {},
          'cameras': {},
          'levels': {},
          'notes': []}


def text(value):
    try:
        return str(value)
    except Exception as exc:
        return '<unprintable: {0}>'.format(exc)


def dump_post_process(settings):
    """Every exposed exposure / histogram / local exposure property with its value."""
    data = {}
    try:
        names = [n for n in dir(settings)
                 if any(key in n.lower() for key in ('exposure', 'ev100', 'histogram', 'eyadapt'))]
    except Exception as exc:
        return {'<dir failed>': text(exc)}
    for name in sorted(names):
        try:
            data[name] = text(settings.get_editor_property(name))
        except Exception as exc:
            data[name] = '<error: {0}>'.format(exc)
    return data


def dump_engine_defaults():
    try:
        camera_cdo = unreal.get_default_object(unreal.CameraComponent)
        report['engine_default']['CameraComponent.PostProcessSettings'] = dump_post_process(
            camera_cdo.get_editor_property('post_process_settings'))
    except Exception as exc:
        report['notes'].append('engine default camera dump failed: {0}'.format(exc))

    try:
        volume_cdo = unreal.get_default_object(unreal.PostProcessVolume)
        report['engine_default']['PostProcessVolume.settings'] = dump_post_process(
            volume_cdo.get_editor_property('settings'))
    except Exception as exc:
        report['notes'].append('engine default post process volume dump failed: {0}'.format(exc))


def dump_cameras():
    for label, class_path in CAMERA_BLUEPRINTS.items():
        camera_data = {}
        try:
            owner_class = unreal.load_class(None, class_path)
            if owner_class is None:
                report['notes'].append('{0}: class not found ({1})'.format(label, class_path))
                continue
            cdo = unreal.get_default_object(owner_class)
            for component in cdo.get_components_by_class(unreal.CameraComponent):
                camera_data[component.get_name()] = dump_post_process(
                    component.get_editor_property('post_process_settings'))
        except Exception as exc:
            camera_data['<error>'] = text(exc)
        report['cameras'][label] = camera_data


def dump_levels():
    level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    for level_path in LEVELS:
        level_data = {'volumes': [], 'cameras': []}
        try:
            level_subsystem.load_level(level_path)
            actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
            for actor in actors:
                if isinstance(actor, unreal.PostProcessVolume):
                    entry = {
                        'actor': actor.get_name(),
                        'label': actor.get_actor_label(),
                        'enabled': text(actor.get_editor_property('enabled')),
                        'unbound': text(actor.get_editor_property('unbound')),
                        'priority': text(actor.get_editor_property('priority')),
                        'blend_radius': text(actor.get_editor_property('blend_radius')),
                        'blend_weight': text(actor.get_editor_property('blend_weight')),
                        'settings': dump_post_process(actor.get_editor_property('settings')),
                    }
                    level_data['volumes'].append(entry)
                for component in actor.get_components_by_class(unreal.CameraComponent):
                    level_data['cameras'].append({
                        'owner': actor.get_name(),
                        'component': component.get_name(),
                        'settings': dump_post_process(component.get_editor_property('post_process_settings')),
                    })
        except Exception as exc:
            level_data['error'] = text(exc)
        report['levels'][level_path] = level_data


def main():
    dump_engine_defaults()
    dump_cameras()
    dump_levels()

    out_dir = os.path.join(os.environ.get('TEMP', '.'), 'MyProject_Phase2')
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    path = os.path.join(out_dir, 'exposure_dump.json')
    with open(path, 'w') as handle:
        json.dump(report, handle, indent=2)
    print('EXPOSURE_DUMP_DONE ' + path)
    print('EXPOSURE_DUMP levels={0} cameras={1}'.format(len(report['levels']), len(report['cameras'])))
    for note in report['notes']:
        print('EXPOSURE_DUMP_NOTE: ' + note)
    # also print the key engine defaults and any level volume values directly
    for key, values in report['engine_default'].items():
        interesting = {k: v for k, v in values.items() if 'min_bright' in k or 'max_bright' in k or 'bias' in k}
        print('EXPOSURE_ENGINE {0}: {1}'.format(key, interesting))


if __name__ == '__main__':
    main()
