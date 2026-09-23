# -*- coding: utf-8 -*-
"""Phase 3A - set the GameMode override on the prototype level's World Settings.

Python cannot reach AWorldSettings through EditorActorSubsystem.get_all_level_actors(),
so this helper tries several supported access paths and reports which one worked.
Only the level's World Settings are touched; nothing else in the level changes.
"""

import json
import os
from datetime import datetime

import unreal

LEVEL_PATH = '/Game/Game/Environment/Lvl_GameplayPrototype'
GAME_MODE_PATH = '/Game/Game/Core/BP_GameMode.BP_GameMode_C'

report = {'phase': 'Phase 3A - level game mode fix', 'timestamp': datetime.now().isoformat(timespec='seconds'),
          'attempts': [], 'result': 'FAILED'}


def write_report():
    rel = unreal.Paths.project_saved_dir() + 'Phase3A/'
    out_dir = unreal.Paths.convert_relative_path_to_full(rel)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    path = os.path.join(out_dir, 'phase3a_level_gamemode_report.json')
    with open(path, 'w') as handle:
        json.dump(report, handle, indent=2)
    return path


def try_path(label, getter, game_mode_class):
    try:
        settings = getter()
    except Exception as exc:
        report['attempts'].append('{0}: raised {1}'.format(label, exc))
        return None
    if settings is None:
        report['attempts'].append('{0}: not available'.format(label))
        return None
    try:
        settings.set_editor_property('default_game_mode', game_mode_class)
        value = settings.get_editor_property('default_game_mode')
        report['attempts'].append('{0}: OK -> {1}'.format(label, value))
        unreal.log('PHASE3A-GAMEMODE: set via {0} -> {1}'.format(label, value))
        return settings
    except Exception as exc:
        report['attempts'].append('{0}: set failed {1}'.format(label, exc))
        return None


def main():
    subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    game_mode_class = unreal.load_class(None, GAME_MODE_PATH)
    if game_mode_class is None:
        unreal.log_error('PHASE3A-GAMEMODE: game mode class not found: ' + GAME_MODE_PATH)
        return write_report()

    subsystem.load_level(LEVEL_PATH)
    unreal.log('PHASE3A-GAMEMODE: level loaded: ' + LEVEL_PATH)

    level = subsystem.get_current_level()
    world = level.get_outer() if level else None

    found = None
    if world:
        found = try_path('world.world_settings',
                         lambda: world.get_editor_property('world_settings'), game_mode_class)
    if not found and world:
        def via_gameplay_statics():
            actors = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.WorldSettings)
            return actors[0] if actors else None
        found = try_path('GameplayStatics.get_all_actors_of_class(WorldSettings)', via_gameplay_statics, game_mode_class)
    if not found:
        found = try_path('EditorLevelLibrary.get_editor_world().world_settings',
                         lambda: unreal.EditorLevelLibrary.get_editor_world().get_editor_property('world_settings'),
                         game_mode_class)

    if found:
        try:
            subsystem.save_current_level()
            report['saved'] = True
        except Exception as exc:
            report['attempts'].append('save failed: {0}'.format(exc))
        report['result'] = 'OK'
    return write_report()


if __name__ == '__main__':
    path = main()
    print('PHASE3A_GAMEMODE_DONE ' + str(path))
    for attempt in report['attempts']:
        print('PHASE3A_GAMEMODE_ATTEMPT: ' + attempt)
    print('PHASE3A_GAMEMODE_RESULT: ' + report['result'])
