# -*- coding: utf-8 -*-
"""Phase 4A - step 2: write the designed terrain into the level's World Partition
landscape, place the home-area layout placeholders and validate. Layout only - no art."""

import json
import os

import unreal

LEVEL = '/Game/Game/Environment/Lvl_Rural'
MI = '/Game/Game/Environment/World/MI_LandscapeBlockout'
WORLD_DIR = '/Game/Game/Environment/World'
CUBE = '/Engine/BasicShapes/Cube.Cube'
VEHICLE_CLASS = '/Game/Game/Vehicles/Base/BP_VehicleBase.BP_VehicleBase_C'
TEST_OBJECT_CLASS = '/Game/Game/Interaction/BP_InteractionTestObject.BP_InteractionTestObject_C'
HOME_INSET_M = 516.0

report = {'steps': [], 'result': 'FAILED', 'failed': []}

level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
editor_subsystem = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)


def log(message):
    unreal.log('P4A-S2: ' + str(message))
    report['steps'].append(str(message))


def warn(message):
    unreal.log_warning('P4A-S2: ' + str(message))
    report['failed'].append(str(message))


def actors():
    return list(actor_subsystem.get_all_level_actors())


def labels():
    return ['{0} [{1}]'.format(a.get_actor_label(), a.get_class().get_name()) for a in actors()]


def make_movable(component):
    try:
        component.unregister_component()
    except Exception:
        pass
    for value in (unreal.ComponentMobility.MOVABLE, 'MOVABLE'):
        try:
            component.set_editor_property('mobility', value)
            break
        except Exception:
            continue
    try:
        component.reregister_component()
    except Exception:
        pass


def material(name):
    path = WORLD_DIR + '/' + name
    return (unreal.EditorAssetLibrary.load_asset(path)
            if unreal.EditorAssetLibrary.does_asset_exist(path) else None)


def spawn_box(label, x_m, y_m, z_m, size_m, material_name, yaw=0.0):
    actor = actor_subsystem.spawn_actor_from_class(
        unreal.StaticMeshActor, unreal.Vector(x_m * 100.0, y_m * 100.0, z_m * 100.0),
        unreal.Rotator(0.0, 0.0, yaw))
    if actor is None:
        warn('could not spawn ' + label)
        return None
    actor.set_actor_label(label)
    actor.set_actor_scale3d(unreal.Vector(size_m[0], size_m[1], size_m[2]))
    component = actor.get_components_by_class(unreal.StaticMeshComponent)[0]
    mesh = unreal.EditorAssetLibrary.load_asset(CUBE)
    if mesh is not None:
        component.set_editor_property('static_mesh', mesh)
    asset = material(material_name)
    if asset is not None:
        component.set_material(0, asset)
    make_movable(component)
    return actor


def spawn_class(class_path, x_m, y_m, z_m, yaw, label):
    actor_class = unreal.load_class(None, class_path)
    if actor_class is None:
        warn('class not found: ' + class_path)
        return None
    actor = actor_subsystem.spawn_actor_from_class(
        actor_class, unreal.Vector(x_m * 100.0, y_m * 100.0, z_m * 100.0),
        unreal.Rotator(0.0, 0.0, yaw))
    if actor is None:
        warn('could not spawn ' + label)
        return None
    actor.set_actor_label(label)
    return actor


def ground_z(world, x_m, y_m):
    """Best effort terrain query via a line trace (returns meters or None)."""
    start = unreal.Vector(x_m * 100.0, y_m * 100.0, 400000.0)
    end = unreal.Vector(x_m * 100.0, y_m * 100.0, -60000.0)
    hit = unreal.SystemLibrary.line_trace_single(
        world, start, end, unreal.TraceTypeQuery.ECC_VISIBILITY, True, [],
        unreal.DrawDebugTrace.NONE, True)
    if hit is None:
        return None
    try:
        data = hit.to_dict()
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    if once['hit_attributes'] is None:
        once['hit_attributes'] = sorted(data.keys())
    blocking = data.get('b_blocking_hit', data.get('bBlockingHit', data.get('blocking_hit', True)))
    location = data.get('location', data.get('Location'))
    if not blocking or location is None:
        return None
    try:
        z = location.get('z', location.z) if hasattr(location, 'get') else location.z
        return round(float(z) / 100.0, 2)
    except Exception:
        return None


once = {'hit_attributes': None}

# ------------------------------------------------------------------ write terrain
level_subsystem.load_level(LEVEL)
world = editor_subsystem.get_editor_world()
log('level loaded: ' + world.get_path_name())

instance = unreal.EditorAssetLibrary.load_asset(MI)
if instance is None:
    warn('landscape material instance missing: ' + MI)

build = unreal.Phase4ATerrainBuilder.build_rural_terrain(world, instance)
result = {}
for field in ('message', 'landscape_label', 'heightmap_size_x', 'heightmap_size_y',
              'component_size_quads', 'num_subsections', 'subsection_size_quads', 'proxy_count',
              'vertex_min_x', 'vertex_min_y', 'vertex_max_x', 'vertex_max_y',
              'world_min_m', 'world_max_m', 'world_size_meters', 'quad_size_meters',
              'clearing_flatness_spread_m', 'town_flatness_spread_m', 'max_road_rise_step_m',
              'home_road_length_m', 'home_road_start_height_m', 'home_road_end_height_m',
              'home_road_max_grade', 'cleared_actor_count', 'route_actor_labels',
              'component_count_x', 'home_center', 'home_pad_height_m'):
    try:
        result[field] = getattr(build, field)
    except Exception:  # noqa: BLE001
        result[field] = 'n/a'
samples = {}
try:
    samples = {str(k): round(float(v), 2) for k, v in build.elevation_samples_m.items()}
except Exception as exc:  # noqa: BLE001
    warn('could not read elevation samples: {0}'.format(exc))
readback = {}
try:
    readback = {str(k): round(float(v), 2) for k, v in build.readback_samples_m.items()}
except Exception as exc:  # noqa: BLE001
    warn('could not read the heightmap readback: {0}'.format(exc))
report['readback_samples_m'] = readback
comparison = {}
for key, value in samples.items():
    name = key.split(' ')[0]
    match = None
    for read_key, read_value in readback.items():
        if read_key.startswith(name + ' '):
            match = read_value
            break
    if match is not None:
        comparison[name] = round(match - value, 2)
report['readback_minus_designed_m'] = comparison
report['build'] = result
report['elevation_samples_m'] = samples
log('build message: ' + str(result['message']))
log('world={0} m quad={1} m components={2} proxies={3} componentSizeQuads={4} subsections={5} subsectionQuads={6}'.format(
    result['world_size_meters'], result['quad_size_meters'], result['component_count_x'],
    result['proxy_count'], result['component_size_quads'], result['num_subsections'],
    result['subsection_size_quads']))
log('samples: ' + json.dumps(samples))

level_subsystem.save_current_level()
report['saved'] = True
log('level saved')

level_subsystem.load_level(LEVEL)
world = editor_subsystem.get_editor_world()

landscape_actors = [a for a in actors() if 'Landscape' in a.get_class().get_name()]
report['landscape_actors_after_reload'] = len(landscape_actors)
landscape = None
for actor in landscape_actors:
    if actor.get_class().get_name() == 'Landscape':
        landscape = actor
        break
if landscape is not None:
    report['landscape_label'] = landscape.get_actor_label()
    report['landscape_bounds'] = str(landscape.get_actor_bounds(only_colliding_components=False))
    try:
        report['landscape_material'] = str(landscape.get_editor_property('landscape_material'))
    except Exception:  # noqa: BLE001
        report['landscape_material'] = 'n/a'
else:
    warn('no ALandscape after reload')

# ------------------------------------------------------------------ layout anchor
world_max = result['world_max_m']
world_min = result['world_min_m']

# The builder reports 'home_clearing (X,Y)' and its height; take the coordinates from
# that sample key so the layout always lands on the pad the terrain builder created.
home_x = None
home_y = None
pad = None
for key, value in samples.items():
    if key.startswith('home_clearing') and '(' in key:
        coords = key.split('(')[1].rstrip(')').split(',')
        try:
            home_x = float(coords[0])
            home_y = float(coords[1])
            pad = float(value)
        except Exception:  # noqa: BLE001
            home_x = home_y = None
        break
if home_x is None or home_y is None:
    design_scale = max(0.25, min(2.0, float(result['world_size_meters']) / 4032.0))
    home_x = float(world_max.x) - 516.0 * design_scale
    home_y = float(world_max.y) - 516.0 * design_scale
    warn('home clearing sample missing, derived the home centre from the world size')
report['home_center_m'] = [round(home_x, 1), round(home_y, 1)]
log('home centre = ({0}, {1}) m'.format(home_x, home_y))

probes = {
    'home_clearing': (home_x, home_y),
    'hill_summit': (home_x + 280.0, home_y + 290.0),
    'forest_belt': (home_x - 600.0, home_y - 600.0),
    'lowland_south_west': (float(world_min.x) + 300.0, float(world_min.y) + 300.0),
    'lowland_centre': ((float(world_min.x) + float(world_max.x)) * 0.5,
                       (float(world_min.y) + float(world_max.y)) * 0.5),
    'outside_world_east': (float(world_max.x) + 400.0, 0.0),
    'outside_world_south': (0.0, float(world_min.y) - 400.0),
}
report['traces'] = {}
for name, (x, y) in probes.items():
    report['traces'][name] = ground_z(world, x, y)
report['hit_attributes'] = once['hit_attributes']
log('traces: ' + json.dumps(report['traces']))
log('hit attributes: ' + json.dumps(report['hit_attributes']))

# ---------------------------------------------------------------- home layout
if pad is None:
    pad = result.get('home_pad_height_m')
if not isinstance(pad, (int, float)) or not pad:
    pad = ground_z(world, home_x, home_y) or 170.0
    warn('home clearing height unavailable from the builder, using fallback')
report['home_pad_height_m'] = round(float(pad), 2)
log('home pad height = {0} m'.format(report['home_pad_height_m']))

for actor in actors():
    if actor.get_class().get_name() == 'PlayerStart':
        actor_subsystem.destroy_actor(actor)
        log('removed template PlayerStart')

# idempotency: drop layout actors created by an earlier run of this script
for actor in actors():
    label = actor.get_actor_label()
    if (label.startswith('Home_') or label in ('Vehicle', 'InteractionTestObject', 'PlayerStart_Home')):
        actor_subsystem.destroy_actor(actor)
        log('removed previous layout actor ' + label)

placed = []
placed.append(spawn_box('Home_House_Body', home_x, home_y + 70.0, pad + 1.6, (12, 9, 3.2), 'MI_house'))
placed.append(spawn_box('Home_House_Roof', home_x, home_y + 70.0, pad + 3.4, (13, 10, 0.4), 'MI_roof'))
placed.append(spawn_box('Home_House_Door', home_x, home_y + 25.2, pad + 1.1, (1.6, 0.2, 2.2), 'MI_door'))
placed.append(spawn_box('Home_Veranda_Slab', home_x + 10.0, home_y + 12.0, pad + 0.03, (16, 10, 0.06), 'MI_road'))
placed.append(spawn_box('Home_Garage_BackWall', home_x, home_y - 74.0, pad + 1.5, (8, 0.4, 3.0), 'MI_garage'))
placed.append(spawn_box('Home_Garage_WallLeft', home_x - 44.0, home_y - 120.0, pad + 1.5, (0.4, 9.2, 3.0), 'MI_garage'))
placed.append(spawn_box('Home_Garage_WallRight', home_x + 44.0, home_y - 120.0, pad + 1.5, (0.4, 9.2, 3.0), 'MI_garage'))
placed.append(spawn_box('Home_Garage_Roof', home_x, home_y - 120.0, pad + 3.2, (9, 10, 0.4), 'MI_roof'))
placed.append(spawn_box('Home_Garage_Floor', home_x, home_y - 120.0, pad + 0.03, (7.2, 9.2, 0.06), 'MI_road'))
placed.append(spawn_class(VEHICLE_CLASS, home_x, home_y - 130.0, pad + 0.63, 0.0, 'Vehicle'))
placed.append(spawn_class(TEST_OBJECT_CLASS, home_x + 85.0, home_y, pad + 0.45, 180.0, 'InteractionTestObject'))
start = spawn_class('/Script/Engine.PlayerStart', home_x + 20.0, home_y - 42.0, pad + 0.9, 270.0, 'PlayerStart_Home')
placed.append(start)
# The spawn point must exist before the world partition has streamed any cell,
# otherwise the game would spawn the player at the world origin.
if start is not None:
    try:
        start.set_editor_property('is_spatially_loaded', False)
        log('PlayerStart_Home marked as always loaded')
    except Exception as exc:  # noqa: BLE001
        warn('could not mark the PlayerStart as always loaded: {0}'.format(exc))
report['placed'] = [a.get_actor_label() for a in placed if a is not None]
log('placed {0} layout actors'.format(len(report['placed'])))

level_subsystem.save_current_level()
log('level saved (2nd)')

# ---------------------------------------------------------------- final verify
level_subsystem.load_level(LEVEL)
final_labels = labels()
report['final_actor_count'] = len(final_labels)
report['final_labels'] = final_labels
report['final_has_landscape'] = any('Landscape' in x for x in final_labels)
report['final_has_vehicle'] = any(x.startswith('Vehicle [') for x in final_labels)
report['final_has_playerstart'] = any(x.startswith('PlayerStart_Home [') for x in final_labels)
report['final_has_interaction'] = any(x.startswith('InteractionTestObject [') for x in final_labels)
report['final_route_actors'] = [x for x in final_labels if x.startswith('Road_Route_')]

final_world = editor_subsystem.get_editor_world()
report['final_world_partition_is_none'] = (
    final_world.get_world_settings().get_editor_property('world_partition') is None)


def number(value):
    return value if isinstance(value, (int, float)) else None


def sample_value(prefix):
    for key, value in samples.items():
        if key.startswith(prefix):
            return float(value)
    return None


home_z = sample_value('home_clearing')
lowland_z = sample_value('lowland_south_west')
forest_z = sample_value('forest_belt')
road_start_z = sample_value('home_road_start')
road_end_z = sample_value('home_road_end')
report['relief'] = {
    'home_clearing_m': home_z,
    'forest_belt_m': forest_z,
    'lowland_south_west_m': lowland_z,
    'road_start_m': road_start_z,
    'road_end_m': road_end_z,
    'home_above_lowland_m': None if (home_z is None or lowland_z is None) else round(home_z - lowland_z, 1),
}

checks = {
    'terrain_written': (isinstance(result['message'], str) and 'written into' in result['message']),
    'components_edited': (number(result['component_count_x']) is not None and result['component_count_x'] > 0),
    'world_large': (number(result['world_size_meters']) is not None and result['world_size_meters'] >= 1900.0),
    'world_partition_enabled': not report['final_world_partition_is_none'],
    'landscape_present': report['final_has_landscape'],
    'clearing_flat': (number(result['clearing_flatness_spread_m']) is not None
                      and result['clearing_flatness_spread_m'] < 1.5),
    'town_flat': (number(result['town_flatness_spread_m']) is not None
                  and result['town_flatness_spread_m'] < 2.5),
    'road_descends': (number(result['max_road_rise_step_m']) is not None
                      and result['max_road_rise_step_m'] < 0.5),
    'road_grade_ok': (number(result['home_road_max_grade']) is not None
                      and result['home_road_max_grade'] < 0.12),
    'road_long': (number(result['home_road_length_m']) is not None
                  and result['home_road_length_m'] > 1500.0),
    'home_above_lowland': (home_z is not None and lowland_z is not None and (home_z - lowland_z) > 80.0),
    'forest_above_lowland': (forest_z is not None and lowland_z is not None and (forest_z - lowland_z) > 20.0),
    'spawn_valid': report['final_has_playerstart'],
    'vehicle_present': report['final_has_vehicle'],
    'interaction_present': report['final_has_interaction'],
}
report['checks'] = checks
report['ok'] = all(checks.values())
report['result'] = 'OK' if report['ok'] else 'CHECK'
log('checks: ' + json.dumps(checks))
log('result: ' + report['result'])

out_dir = os.path.join(os.environ.get('TEMP', '.'), 'MyProject_Phase4A')
with open(os.path.join(out_dir, 'phase4a_step2.json'), 'w') as handle:
    json.dump(report, handle, indent=2, default=str)
log('report written: ' + os.path.join(out_dir, 'phase4a_step2.json'))
