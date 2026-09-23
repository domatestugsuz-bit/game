# -*- coding: utf-8 -*-
"""Phase 4A verify: fresh editor session - load the level and read the real terrain
heights (collision generated at load time) plus actor/WP state. Read only."""

import json
import os

import unreal

LEVEL = '/Game/Game/Environment/Lvl_Rural'
report = {'result': 'FAILED'}

level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
editor_subsystem = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)


def log(message):
    unreal.log('P4A-V: ' + str(message))


level_subsystem.load_level(LEVEL)
world = editor_subsystem.get_editor_world()
report['world'] = world.get_path_name()
report['world_partition_is_none'] = (
    world.get_world_settings().get_editor_property('world_partition') is None)
report['actors'] = ['{0} [{1}]'.format(a.get_actor_label(), a.get_class().get_name())
                    for a in actor_subsystem.get_all_level_actors()]
report['actor_count'] = len(report['actors'])


def trace(x_m, y_m):
    start = unreal.Vector(x_m * 100.0, y_m * 100.0, 300000.0)
    end = unreal.Vector(x_m * 100.0, y_m * 100.0, -60000.0)
    hit = unreal.SystemLibrary.line_trace_single(
        world, start, end, unreal.TraceTypeQuery.ECC_VISIBILITY, True, [],
        unreal.DrawDebugTrace.NONE, True)
    if hit is None:
        return None
    data = hit.to_dict()
    if not isinstance(data, dict) or not data.get('blocking_hit', True):
        return None
    location = data.get('location')
    try:
        return round(float(location.z) / 100.0, 2)
    except Exception:
        return None


probes = {
    'home_clearing (750,750)': (750.0, 750.0),
    'hill_summit (890,895)': (890.0, 895.0),
    'forest_belt (450,450)': (450.0, 450.0),
    'mid_road (-265,-500)': (-265.0, -500.0),
    'lowland_south_west (-708,-708)': (-708.0, -708.0),
    'lowland_south (0,-848)': (0.0, -848.0),
    'lowland_west (-808,0)': (-808.0, 0.0),
    'north_west_region (-808,608)': (-808.0, 608.0),
    'world_edge_north_east (978,978)': (978.0, 978.0),
    'town_reserved (-250,-825)': (-250.0, -825.0),
    'mechanic_reserved (200,-625)': (200.0, -625.0),
    'market_reserved (500,-615)': (500.0, -615.0),
    'home_road_start (750,665)': (750.0, 665.0),
    'home_road_end (893,-975)': (893.0, -975.0),
    'main_road_west (-600,-580)': (-600.0, -580.0),
    'main_road_junction (828,-570)': (828.0, -570.0),
    'outside_world_east (1400,0)': (1400.0, 0.0),
    'outside_world_south (0,-1400)': (0.0, -1400.0),
}
report['traces'] = {}
for name, (x, y) in probes.items():
    report['traces'][name] = trace(x, y)
    log('trace {0} = {1}'.format(name, report['traces'][name]))

report['landscape_actors'] = [x for x in report['actors'] if 'Landscape' in x]

spawn_info = {}
for actor in actor_subsystem.get_all_level_actors():
    if actor.get_actor_label().startswith('PlayerStart'):
        entry = {'class': actor.get_class().get_name(), 'location': str(actor.get_actor_location())}
        for prop in ('is_spatially_loaded', 'b_is_spatially_loaded'):
            try:
                entry[prop] = str(actor.get_editor_property(prop))
            except Exception:  # noqa: BLE001
                entry[prop] = 'n/a'
        spawn_info[actor.get_actor_label()] = entry
report['player_starts'] = spawn_info
log('player starts: ' + json.dumps(spawn_info))
report['result'] = 'OK'
out_dir = os.path.join(os.environ.get('TEMP', '.'), 'MyProject_Phase4A')
with open(os.path.join(out_dir, 'phase4a_verify.json'), 'w') as handle:
    json.dump(report, handle, indent=2, default=str)
log('verify written, actors={0}'.format(report['actor_count']))
