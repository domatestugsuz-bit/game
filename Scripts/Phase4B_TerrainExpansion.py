# -*- coding: utf-8 -*-
"""Phase 4B - expand the World Partition landscape of Lvl_Rural to a ~4032 m world.

Non destructive by design: components are only ADDED around the existing ones through the
same route the editor's "Add New Landscape Component" tool uses (the helper lives in
Source/MyProject/World/Phase4BTerrainExpander.cpp). The original 2016 m block keeps its
heightmap, so the home property, the road and the garage keep their exact heights, and a
raw heightmap backup is written before anything is modified.
"""

import json
import os

import unreal

LEVEL = '/Game/Game/Environment/Lvl_Rural'
SAVED_DIR = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir()), 'Phase4B')
BACKUP = os.path.join(SAVED_DIR, 'heightmap_backup_pre_expansion.bin')

report = {'steps': [], 'result': 'FAILED', 'failed': []}

FIELDS = ['bSuccess', 'message', 'steps', 'oldVertexMin', 'oldVertexMax', 'oldWorldMinM', 'oldWorldMaxM',
          'oldComponentCount', 'newVertexMin', 'newVertexMax', 'newWorldMinM', 'newWorldMaxM', 'newWorldSizeM',
          'newComponentCount', 'componentsCreated', 'stripsWritten', 'streamingProxiesAfter',
          'componentSizeQuads', 'numSubsections', 'subsectionSizeQuads', 'heightmapZScale',
          'preservedBeforeM', 'preservedAfterM', 'maxPreservedDeltaM', 'outerSamplesM', 'outerReliefM',
          'heightmapBackupPath', 'backupBytes']

TRACES = [('home_pad_trace', 750.0, 750.0), ('house_trace', 760.0, 783.0), ('road_start_trace', 750.0, 665.0),
          ('road_mid_trace', 222.0, 215.0), ('old_edge_west', -1000.0, 0.0), ('old_edge_north', 0.0, 1000.0),
          ('outer_south_west', -1900.0, -1900.0), ('outer_north_east', 1900.0, 1900.0),
          ('outer_north', 0.0, 1900.0), ('outer_east', 1900.0, 0.0), ('outer_west', -1900.0, 0.0),
          ('outer_south', 0.0, -1900.0), ('outer_centre_west', -1500.0, 750.0)]

level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
editor_subsystem = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)


def log(message):
    unreal.log('P4B-EXP: ' + str(message))
    report['steps'].append(str(message))


def fail(message):
    unreal.log_error('P4B-EXP: ' + str(message))
    report['failed'].append(str(message))


def jsonable(value):
    if isinstance(value, (bool, int, float, str)) or value is None:
        return value
    if hasattr(value, 'x') and hasattr(value, 'y'):
        try:
            return [round(float(value.x), 3), round(float(value.y), 3)]
        except Exception:  # noqa: BLE001
            return str(value)
    if hasattr(value, 'get'):
        out = {}
        try:
            for key in value:
                out[str(key)] = jsonable(value[key])
            return out
        except Exception:  # noqa: BLE001
            return str(value)
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return str(value)


def capture(struct):
    out = {}
    for field in FIELDS:
        try:
            out[field] = jsonable(struct.get_editor_property(field))
        except Exception:  # noqa: BLE001
            out[field] = 'n/a'
    return out


def labels():
    return ['{0} [{1}]'.format(actor.get_actor_label(), actor.get_class().get_name())
            for actor in actor_subsystem.get_all_level_actors()]


def ground_z(world, x_m, y_m):
    start = unreal.Vector(x_m * 100.0, y_m * 100.0, 60000.0)
    end = unreal.Vector(x_m * 100.0, y_m * 100.0, -60000.0)
    hit = unreal.SystemLibrary.line_trace_single(world, start, end, unreal.TraceTypeQuery.ECC_VISIBILITY,
                                                 True, [], unreal.DrawDebugTrace.NONE, True)
    if hit is None:
        return None
    try:
        location = hit.to_dict().get('location')
        return round(float(location.z) / 100.0, 2)
    except Exception:  # noqa: BLE001
        return None


def landscape_metrics():
    """Streaming proxy count and world extent measured from the loaded proxies."""
    proxies = 0
    components = 0
    minimum = None
    maximum = None
    for actor in actor_subsystem.get_all_level_actors():
        klass = actor.get_class().get_name()
        if klass not in ('Landscape', 'LandscapeStreamingProxy'):
            continue
        if klass == 'LandscapeStreamingProxy':
            proxies += 1
        try:
            components += len(actor.get_components_by_class(unreal.LandscapeComponent))
        except Exception:  # noqa: BLE001
            pass
        try:
            origin, extent = actor.get_actor_bounds(only_colliding_components=False)
            if extent.x > 1.0 or extent.y > 1.0:
                low = (origin.x - extent.x, origin.y - extent.y)
                high = (origin.x + extent.x, origin.y + extent.y)
                minimum = low if minimum is None else (min(minimum[0], low[0]), min(minimum[1], low[1]))
                maximum = high if maximum is None else (max(maximum[0], high[0]), max(maximum[1], high[1]))
        except Exception:  # noqa: BLE001
            pass
    metrics = {'streaming_proxies': proxies, 'components_seen': components}
    if minimum is not None and maximum is not None:
        metrics['world_min_m'] = [round(minimum[0] / 100.0, 1), round(minimum[1] / 100.0, 1)]
        metrics['world_max_m'] = [round(maximum[0] / 100.0, 1), round(maximum[1] / 100.0, 1)]
        metrics['world_size_m'] = [round((maximum[0] - minimum[0]) / 100.0, 1),
                                   round((maximum[1] - minimum[1]) / 100.0, 1)]
    return metrics


def expand_helper():
    """The UE Python name of ExpandWorldTo4032 is not obvious (the digits are glued to
    the last word), so every plausible spelling is accepted."""
    for name in ('expand_world_to_4032', 'expand_world_to4032', 'expand_worldto4032'):
        helper = getattr(unreal.Phase4BTerrainExpander, name, None)
        if helper is not None:
            log('expand helper resolved as {0}'.format(name))
            return helper
    return None


# ------------------------------------------------------------------ run
if not os.path.isdir(SAVED_DIR):
    os.makedirs(SAVED_DIR)

level_subsystem.load_level(LEVEL)
world = editor_subsystem.get_editor_world()
before = labels()
report['actors_before'] = len(before)
log('level loaded, actors before: {0}'.format(len(before)))

# The block that must keep its exact heights is the Phase 4A world: 2016 m x 2016 m at
# 1 m per quad. The sidecar is the contract ExpandWorldTo4032() reads, so it must describe
# exactly this block; the expansion itself never rewrites it.
PRESERVED_MIN = (0, 0)
PRESERVED_MAX = (2016, 2016)
EXPECTED_EXTENT = {'min_x': PRESERVED_MIN[0], 'min_y': PRESERVED_MIN[1],
                   'max_x': PRESERVED_MAX[0], 'max_y': PRESERVED_MAX[1]}


def read_sidecar(path):
    values = {}
    try:
        with open(path, 'r') as handle:
            for line in handle:
                if '=' in line:
                    key, value = line.strip().split('=', 1)
                    try:
                        values[key.strip()] = int(float(value.strip()))
                    except ValueError:
                        continue
    except Exception:  # noqa: BLE001
        return {}
    return values


SIDECAR = BACKUP + '.txt'
existing_sidecar = read_sidecar(SIDECAR)
sidecar_ok = all(existing_sidecar.get(key) == value for key, value in EXPECTED_EXTENT.items())
if os.path.isfile(BACKUP) and sidecar_ok:
    report['backup'] = {'message': 'existing heightmap backup kept',
                        'backupBytes': os.path.getsize(BACKUP), 'heightmapBackupPath': BACKUP,
                        'sidecar': existing_sidecar}
    log('existing backup kept: {0}'.format(SIDECAR))
else:
    if os.path.isfile(SIDECAR):
        log('sidecar did not describe the Phase 4A block - rewriting the backup')
    report['backup'] = capture(unreal.Phase4BTerrainExpander.backup_landscape_region(
        world, unreal.IntPoint(PRESERVED_MIN[0], PRESERVED_MIN[1]),
        unreal.IntPoint(PRESERVED_MAX[0], PRESERVED_MAX[1]), BACKUP))
    log('backup: {0}'.format(report['backup']['message']))

helper = expand_helper()
if helper is None:
    fail('Phase4BTerrainExpander.expand_world_to_4032 is not exposed to Python')
    report['expand'] = {'message': 'helper missing', 'bSuccess': False}
else:
    report['expand'] = capture(helper(world, BACKUP))
for step in report['expand'].get('steps') or []:
    log('expand step: {0}'.format(step))
log('expand: {0}'.format(report['expand']['message']))

level_subsystem.save_current_level()
report['saved'] = True
log('level saved')

level_subsystem.load_level(LEVEL)
world = editor_subsystem.get_editor_world()
after = labels()
report['actors_after'] = len(after)
report['missing_labels'] = [label for label in before if label not in after]
report['new_labels'] = [label for label in after if label not in before][:60]
report['landscape'] = landscape_metrics()
report['traces'] = {}
for name, x_m, y_m in TRACES:
    report['traces'][name] = ground_z(world, x_m, y_m)
log('landscape after: {0}'.format(json.dumps(report['landscape'])))
log('traces: {0}'.format(json.dumps(report['traces'])))

expand = report['expand']
relief = expand.get('outerReliefM') if isinstance(expand.get('outerReliefM'), dict) else {}
preserved_delta = expand.get('maxPreservedDeltaM')
outer_names = ('outer_south_west', 'outer_north_east', 'outer_north', 'outer_east', 'outer_west', 'outer_south')
outer_ok = all(isinstance(report['traces'].get(name), float) for name in outer_names)
traces = report['traces']

def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


outer_values = [value for value in (expand.get('outerSamplesM') or {}).values() if is_number(value)]
outer_min = min(outer_values) if outer_values else None
grid = expand.get('newComponentCount')
checks = {
    'backup_written': bool(report['backup'].get('backupBytes')),
    'expand_success': bool(expand.get('bSuccess')),
    'strips_written': (expand.get('stripsWritten') or 0) == 4,
    'world_is_4032_m': is_number(expand.get('newWorldSizeM'))
                       and abs(float(expand['newWorldSizeM']) - 4032.0) < 2.0,
    'component_grid_32x32': isinstance(grid, list) and grid[:2] == [32, 32],
    'preserved_heights_intact': is_number(preserved_delta) and float(preserved_delta) < 0.05,
    'outer_relief_has_relief': is_number(relief.get('spread')) and float(relief['spread']) > 60.0,
    'outer_area_not_flat': (outer_min is not None) and outer_min > 8.0,
    'outer_sampled_everywhere': len(outer_values) >= 8,
    'no_actors_lost': len(report['missing_labels']) == 0,
    'house_present': any(label.startswith('P4_Prod') for label in after),
    'garage_present': any(label.startswith('P4B_Garage') for label in after),
    'vehicle_present': any(label.startswith('Vehicle') for label in after),
    'player_start_present': any(label.startswith('PlayerStart_Home') for label in after),
    'interaction_present': any(label.startswith('InteractionTestObject') for label in after),
    'road_route_present': any(label.startswith('Road_Route_') for label in after),
    'home_pad_still_elevated': is_number(traces.get('home_pad_trace')) and traces['home_pad_trace'] > 140.0,
}
report['checks'] = checks
report['ok'] = all(checks.values())
report['result'] = 'OK' if report['ok'] else 'CHECK'
log('checks: {0}'.format(json.dumps(checks, default=str)))
log('result: {0}'.format(report['result']))

out_path = os.path.join(SAVED_DIR, 'phase4b_expansion.json')
with open(out_path, 'w') as handle:
    json.dump(report, handle, indent=2, default=str)
log('report written: {0}'.format(out_path))
