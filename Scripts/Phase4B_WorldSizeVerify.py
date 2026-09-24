# -*- coding: utf-8 -*-
"""Independent check of the Phase 4B world size claim (read only).

The Phase 4B expansion report says the world is 4032 x 4032 m. Two of its own numbers do not fit
that claim: "0 components created" and a list of outer trace results that are all null. This script
measures the world from the level itself - streaming proxy bounds, component count and traces at
the inner reference points and at the outer ring - and states the verdict, so the size of the world
is never taken on faith again.
"""

import json
import os

import unreal

LEVEL = '/Game/Game/Environment/Lvl_Rural'
SAVED_DIR = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir()),
                         'Phase4B')
CM = 100.0
INNER_POINTS = [('home_pad', 750.0, 750.0), ('house', 760.0, 783.0), ('road_mid', 222.0, 215.0),
                ('world_centre', 0.0, 0.0), ('east_1000', 1000.0, 0.0), ('north_1000', 0.0, 1000.0)]
OUTER_POINTS = [('outer_west', -1900.0, 0.0), ('outer_east', 1900.0, 0.0),
                ('outer_south', 0.0, -1900.0), ('outer_north', 0.0, 1900.0),
                ('outer_south_west', -1900.0, -1900.0), ('outer_north_east', 1900.0, 1900.0),
                ('edge_west', -1200.0, 0.0), ('edge_east', 1200.0, 0.0)]

level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
level_subsystem.load_level(LEVEL)
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

report = {'result': 'FAILED'}


def trace(x_m, y_m):
    start = unreal.Vector(x_m * CM, y_m * CM, 400000.0)
    end = unreal.Vector(x_m * CM, y_m * CM, -60000.0)
    hit = unreal.SystemLibrary.line_trace_single(world, start, end, unreal.TraceTypeQuery.ECC_VISIBILITY,
                                                 False, [], unreal.DrawDebugTrace.NONE, True)
    if hit is None:
        return None
    data = hit.to_dict()
    if not data.get('blocking_hit', True):
        return None
    location = data.get('location')
    return round(float(location.z) / CM, 2) if location else None


min_x = min_y = 1e9
max_x = max_y = -1e9
proxies = 0
components = 0
for actor in actor_subsystem.get_all_level_actors():
    if actor.get_class().get_name() != 'LandscapeStreamingProxy':
        continue
    proxies += 1
    components += len(actor.get_components_by_class(unreal.LandscapeComponent))
    origin, extent = actor.get_actor_bounds(False)
    if not isinstance(origin, unreal.Vector):
        continue
    min_x = min(min_x, (float(origin.x) - float(extent.x)) / CM)
    max_x = max(max_x, (float(origin.x) + float(extent.x)) / CM)
    min_y = min(min_y, (float(origin.y) - float(extent.y)) / CM)
    max_y = max(max_y, (float(origin.y) + float(extent.y)) / CM)

report['landscape'] = {
    'streaming_proxies': proxies,
    'components': components,
    'world_min_m': [round(min_x, 1), round(min_y, 1)],
    'world_max_m': [round(max_x, 1), round(max_y, 1)],
    'world_size_m': [round(max_x - min_x, 1), round(max_y - min_y, 1)],
}
report['inner_traces'] = {name: trace(x, y) for name, x, y in INNER_POINTS}
report['outer_traces'] = {name: trace(x, y) for name, x, y in OUTER_POINTS}

inner_ok = all(value is not None for value in report['inner_traces'].values())
outer_present = [name for name, value in report['outer_traces'].items() if value is not None]
size = report['landscape']['world_size_m']

checks = {
    'landscape_measured': proxies > 0 and components > 0,
    'inner_world_reachable': inner_ok,
    'world_is_4032_m': abs(size[0] - 4032.0) < 8.0 and abs(size[1] - 4032.0) < 8.0,
    'outer_ring_has_terrain': len(outer_present) >= 6,
    'component_count_1024': components == 1024,
}
report['checks'] = checks
report['outer_traces_present'] = outer_present
report['ok'] = all(checks.values())
report['result'] = 'OK' if report['ok'] else 'CHECK'
report['verdict'] = ('world matches the 4032 m claim' if report['ok'] else
                     'world does NOT match the 4032 m claim: measured {0} x {1} m, '
                     '{2} components, outer terrain missing'.format(size[0], size[1], components))
unreal.log_warning('P4B-WORLDSIZE: ' + report['verdict'])

if not os.path.isdir(SAVED_DIR):
    os.makedirs(SAVED_DIR)
out_path = os.path.join(SAVED_DIR, 'phase4b_worldsize_verify.json')
with open(out_path, 'w') as handle:
    json.dump(report, handle, indent=2, default=str)
unreal.log_warning('P4B-WORLDSIZE: written ' + out_path)
