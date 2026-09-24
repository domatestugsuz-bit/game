# -*- coding: utf-8 -*-
"""Phase 4B - build the upgraded forest on the 4032 m world (placement step).

Replaces the Phase 4B placeholder pine blocks (trunk + canopy pairs, 6400 instances) with the
production pine family imported by Phase4B_VegetationImport.py, placed with density masks instead
of a uniform sprinkle:

  * slope      - nothing on cliffs, thinning on steep ground
  * elevation  - a tree line high on the ridges, denser in the valleys
  * clearings  - value noise carves real open meadows into the forest
  * home       - the property envelope (house, garage, yard, driveway, veranda, grill, shed,
                 vehicle spawn, player start) stays completely clear, then thins out into a yard
  * road       - both road routes are sampled as polylines, the corridor stays clear and the
                 forest edge thickens behind it

Trees are instanced: one HISM component per pine variant inside one actor per 64 m World Partition
cell, mobility static, so streaming, HLOD and shadow culling work exactly like the rest of the
level. Nothing is ever placed as one actor per tree.
"""

import json
import math
import os
import random

import unreal

LEVEL = '/Game/Game/Environment/Lvl_Rural'
SAVED_DIR = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir()),
                         'Phase4B')
TREE_DIR = '/Game/Game/Environment/Vegetation/Trees/Pine'
PREFIX = 'P4B_Forest_'
OLD_TREE_PREFIX = 'P4B_Trees_'
WORLD_HALF_M = 2016.0
# World Partition streaming cell: one forest actor per cell keeps the actor count in the same
# order as the rest of the level instead of one actor per 64 m patch.
CELL_M = 256.0
LANDSCAPE_EDGE_M = 2008.0
SINK_MIN_M = 0.15
SINK_MAX_M = 0.80
SEED = 20260924
CM_PER_M = 100.0

# The footprint of the property that must stay clear (metres of clearance outside the envelope).
PROPERTY_HARD_M = 8.0
PROPERTY_RAMP_M = 45.0
ROAD_HARD_M = 16.0
ROAD_RAMP_M = 45.0
# Elevation / slope limits for a pine forest.
TREE_LINE_M = 205.0
TREE_LINE_RAMP_M = 165.0
SLOPE_HARD_DEG = 32.0
SLOPE_RAMP_DEG = 20.0
TREE_LINE_FLOOR = 0.25
# The added landscape ring of the Phase 4B expansion carries uninitialised heights (raw 0, which
# reads as about -255 m). Nothing may be planted below sea level, otherwise the forest grows inside
# that trench instead of on the terrain.
GROUND_FLOOR_M = 0.0

# rings: (inner, outer, spacing) - the forest gets sparser and more mature with distance
RINGS = [(0.0, 340.0, 10.0), (340.0, 800.0, 18.0), (800.0, 1350.0, 30.0), (1350.0, 2100.0, 50.0)]
RING_VARIANTS = [
    [('Pine_Young_A', 0.22), ('Pine_Medium_B', 0.34), ('Pine_Sparse_F', 0.16),
     ('Pine_Mature_C', 0.20), ('Pine_Bent_E', 0.08)],
    [('Pine_Medium_B', 0.26), ('Pine_Mature_C', 0.34), ('Pine_Dense_G', 0.20),
     ('Pine_Bent_E', 0.12), ('Pine_Sparse_F', 0.08)],
    [('Pine_Mature_C', 0.30), ('Pine_Dense_G', 0.24), ('Pine_LargeOld_D', 0.22),
     ('Pine_DenseTall_H', 0.14), ('Pine_Bent_E', 0.10)],
    [('Pine_LargeOld_D', 0.34), ('Pine_DenseTall_H', 0.30), ('Pine_Mature_C', 0.22),
     ('Pine_Dense_G', 0.14)],
]
PROTECTED_PREFIXES = ('P4_Prod', 'P4B_', 'Road_Route_', 'Vehicle', 'PlayerStart_Home',
                      'InteractionTestObject')
# actors whose bounds make up the property envelope (everything except the long road routes)
ENVELOPE_EXCLUDE = ('Road_Route_',)

report = {'steps': [], 'result': 'FAILED', 'failed': [], 'warnings': []}
actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor_subsystem = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)


def log(message):
    unreal.log('P4B-FOREST: ' + str(message))
    report['steps'].append(str(message))


def fail(message):
    unreal.log_error('P4B-FOREST: ' + str(message))
    report['failed'].append(str(message))


def warn(message):
    unreal.log_warning('P4B-FOREST: ' + str(message))
    report['warnings'].append(str(message))


level_subsystem.load_level(LEVEL)
world = editor_subsystem.get_editor_world()
log('level loaded: {0}'.format(world.get_name() if world else 'None'))


# ---------------------------------------------------------------- terrain / mask helpers
def ground_z(x_m, y_m):
    """Terrain height at a world position (metres) via a long vertical trace."""
    start = unreal.Vector(x_m * CM_PER_M, y_m * CM_PER_M, 400000.0)
    end = unreal.Vector(x_m * CM_PER_M, y_m * CM_PER_M, -60000.0)
    hit = unreal.SystemLibrary.line_trace_single(world, start, end, unreal.TraceTypeQuery.ECC_VISIBILITY,
                                                 False, [], unreal.DrawDebugTrace.NONE, True)
    if hit is None:
        return None
    data = hit.to_dict()
    if not data.get('blocking_hit', True):
        return None
    location = data.get('location')
    if location is None:
        return None
    try:
        return float(location.z) / CM_PER_M
    except Exception:  # noqa: BLE001
        return None


def slope_deg(x_m, y_m, z_m, step_m=6.0):
    """Slope at a point from two extra probes, so cliff faces can be excluded."""
    zx = ground_z(x_m + step_m, y_m)
    zy = ground_z(x_m, y_m + step_m)
    if zx is None or zy is None:
        return None
    rise = max(abs(zx - z_m), abs(zy - z_m))
    return math.degrees(math.atan2(rise, step_m))


def hash01(a, b, salt):
    value = math.sin(a * 127.1 + b * 311.7 + salt * 74.7) * 43758.5453
    return value - math.floor(value)


def value_noise(x, y, cell_m, salt):
    cell = max(1.0, cell_m)
    fx = x / cell
    fy = y / cell
    ix = math.floor(fx)
    iy = math.floor(fy)
    tx = fx - ix
    ty = fy - iy
    tx = tx * tx * (3.0 - 2.0 * tx)
    ty = ty * ty * (3.0 - 2.0 * ty)
    v00 = hash01(ix, iy, salt)
    v10 = hash01(ix + 1, iy, salt)
    v01 = hash01(ix, iy + 1, salt)
    v11 = hash01(ix + 1, iy + 1, salt)
    top = v00 * (1.0 - tx) + v10 * tx
    bottom = v01 * (1.0 - tx) + v11 * tx
    return top * (1.0 - ty) + bottom * ty


def clearing_noise(x, y):
    """Two octaves: big open meadows with smaller glades inside them."""
    return 0.68 * value_noise(x, y, 300.0, 1.0) + 0.32 * value_noise(x, y, 108.0, 2.0)


def ramp(value, hard, soft):
    """0 at `hard` (rejected) -> 1 at `soft` and beyond."""
    if value <= hard:
        return 0.0
    if value >= soft:
        return 1.0
    return (value - hard) / (soft - hard)


# ---------------------------------------------------------------- protected areas
envelope = {'min_x': None, 'min_y': None, 'max_x': None, 'max_y': None}
roads = []
previous_forest = []
previous_trees = []
for actor in actor_subsystem.get_all_level_actors():
    label = actor.get_actor_label()
    if label.startswith(PREFIX):
        previous_forest.append(actor)
        continue
    if label.startswith(OLD_TREE_PREFIX):
        previous_trees.append(actor)
        continue
    if not label.startswith(PROTECTED_PREFIXES):
        continue
    if label.startswith(ENVELOPE_EXCLUDE):
        splines = actor.get_components_by_class(unreal.SplineComponent)
        if splines:
            spline = splines[0]
            length_cm = float(spline.get_spline_length())
            points = []
            # 4 m sampling: the polyline distance error stays under 2 m, which is well inside
            # the road clearance the masks enforce
            step_count = max(2, int(length_cm / (4.0 * CM_PER_M)) + 1)
            for index in range(step_count):
                point = spline.get_location_at_distance_along_spline(
                    length_cm * index / (step_count - 1), unreal.SplineCoordinateSpace.WORLD)
                points.append((float(point.x) / CM_PER_M, float(point.y) / CM_PER_M))
            roads.append({'label': label, 'length_m': round(length_cm / CM_PER_M, 1), 'points': points})
        continue
    origin, extent = actor.get_actor_bounds(False)
    if not isinstance(origin, unreal.Vector):
        continue
    min_x = (float(origin.x) - float(extent.x)) / CM_PER_M
    max_x = (float(origin.x) + float(extent.x)) / CM_PER_M
    min_y = (float(origin.y) - float(extent.y)) / CM_PER_M
    max_y = (float(origin.y) + float(extent.y)) / CM_PER_M
    if envelope['min_x'] is None:
        envelope.update(min_x=min_x, max_x=max_x, min_y=min_y, max_y=max_y)
    else:
        envelope['min_x'] = min(envelope['min_x'], min_x)
        envelope['max_x'] = max(envelope['max_x'], max_x)
        envelope['min_y'] = min(envelope['min_y'], min_y)
        envelope['max_y'] = max(envelope['max_y'], max_y)

report['envelope_m'] = {key: round(value, 2) for key, value in envelope.items()} if envelope['min_x'] else {}
report['roads'] = [{'label': road['label'], 'length_m': road['length_m'], 'points': len(road['points'])}
                   for road in roads]
report['previous_forest_actors'] = len(previous_forest)
report['previous_placeholder_trees'] = len(previous_trees)
log('property envelope: {0}'.format(json.dumps(report['envelope_m'])))
log('roads: {0}'.format(json.dumps(report['roads'])))
log('previous forest actors: {0}, placeholder tree actors: {1}'.format(len(previous_forest),
                                                                      len(previous_trees)))


def envelope_distance(x, y):
    """Distance outside the property rectangle (0 inside)."""
    dx = max(envelope['min_x'] - x, 0.0, x - envelope['max_x']) if envelope['min_x'] else 1e9
    dy = max(envelope['min_y'] - y, 0.0, y - envelope['max_y']) if envelope['min_x'] else 1e9
    return math.hypot(dx, dy)


# The road polyline has about a thousand points; testing every candidate against all of them
# would dominate the runtime, so the points are bucketed and only the 3x3 neighbourhood of a
# candidate is searched.
ROAD_BUCKET_M = 50.0
road_buckets = {}
for road in roads:
    for point in road['points']:
        key = (int(math.floor(point[0] / ROAD_BUCKET_M)), int(math.floor(point[1] / ROAD_BUCKET_M)))
        road_buckets.setdefault(key, []).append(point)


def road_distance(x, y):
    bx = int(math.floor(x / ROAD_BUCKET_M))
    by = int(math.floor(y / ROAD_BUCKET_M))
    best = 1e9
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            points = road_buckets.get((bx + dx, by + dy))
            if not points:
                continue
            for px, py in points:
                distance = math.hypot(x - px, y - py)
                if distance < best:
                    best = distance
    return best if best < 999.0 else 999.0


# ---------------------------------------------------------------- placement
rng = random.Random(SEED)
instances = []           # (variant, x, y, z, yaw, scale)
mask_stats = {'candidates': 0, 'no_ground': 0, 'below_floor': 0, 'slope': 0, 'elevation': 0,
              'clearing': 0, 'property': 0, 'road': 0, 'accepted': 0}
outside = 0
no_ground_samples = []
elevations = []
for ring_index, (inner, outer, spacing) in enumerate(RINGS):
    table = RING_VARIANTS[ring_index]
    total_weight = sum(weight for _, weight in table)
    step = spacing
    count = int((outer * 2.0) / step) + 1
    for ix in range(count):
        for iy in range(count):
            x = -outer + ix * step + rng.uniform(-0.42, 0.42) * step
            y = -outer + iy * step + rng.uniform(-0.42, 0.42) * step
            radius = math.hypot(x, y)
            if radius < inner or radius > outer:
                continue
            if abs(x) > LANDSCAPE_EDGE_M or abs(y) > LANDSCAPE_EDGE_M:
                outside += 1
                continue                                # beyond the landscape: nothing to plant on
            mask_stats['candidates'] += 1
            z = ground_z(x, y)
            if z is None:
                mask_stats['no_ground'] += 1
                if len(no_ground_samples) < 12:
                    no_ground_samples.append([round(x, 1), round(y, 1)])
                continue
            if z < GROUND_FLOOR_M:
                mask_stats['below_floor'] += 1
                continue
            slope = slope_deg(x, y, z)
            if slope is None or slope > SLOPE_HARD_DEG:
                mask_stats['slope'] += 1
                continue
            if z > TREE_LINE_M:
                mask_stats['elevation'] += 1
                continue
            probability = 1.0
            probability *= ramp(slope, SLOPE_RAMP_DEG, SLOPE_HARD_DEG) if slope > SLOPE_RAMP_DEG else 1.0
            # tree line: the ridges thin out instead of stopping at a hard line
            if z > TREE_LINE_RAMP_M:
                probability *= max(TREE_LINE_FLOOR,
                                   1.0 - 0.75 * ramp(z, TREE_LINE_RAMP_M, TREE_LINE_M))
            # clearings
            noise = clearing_noise(x, y)
            if noise < 0.37:
                mask_stats['clearing'] += 1
                continue
            if noise < 0.50:
                probability *= (noise - 0.37) / 0.13
            property_gap = envelope_distance(x, y)
            if property_gap < PROPERTY_HARD_M:
                mask_stats['property'] += 1
                continue
            probability *= ramp(property_gap, PROPERTY_HARD_M, PROPERTY_RAMP_M)
            road_gap = road_distance(x, y)
            if road_gap < ROAD_HARD_M:
                mask_stats['road'] += 1
                continue
            probability *= ramp(road_gap, ROAD_HARD_M, ROAD_RAMP_M)
            if rng.random() > probability:
                continue
            mask_stats['accepted'] += 1
            pick = rng.random() * total_weight
            variant = table[-1][0]
            for name, weight in table:
                pick -= weight
                if pick <= 0.0:
                    variant = name
                    break
            # On a slope the trunk base has to be buried or the tree floats on the downhill side;
            # the sink grows with the local slope and is capped so nothing disappears underground.
            sink = min(SINK_MAX_M, SINK_MIN_M + 0.55 * (min(slope, SLOPE_HARD_DEG) / SLOPE_HARD_DEG))
            instances.append((variant, x, y, z - sink, rng.uniform(0.0, 360.0),
                              rng.uniform(0.82, 1.18), sink))
            elevations.append(z)
    log('ring {0}-{1} m: {2} trees so far'.format(int(inner), int(outer), len(instances)))

report['mask_stats'] = mask_stats
report['elevation_m'] = {'min': round(min(elevations), 1) if elevations else None,
                         'max': round(max(elevations), 1) if elevations else None}
log('placement: {0} trees, masks {1}'.format(len(instances), json.dumps(mask_stats)))


# ---------------------------------------------------------------- actors / instancing
# retire the placeholder forest and any previous run of this script (only our own labels)
removed = {'forest': 0, 'placeholder': 0, 'placeholder_instances': 0}
for actor in previous_forest:
    actor_subsystem.destroy_actor(actor)
    removed['forest'] += 1
for actor in previous_trees:
    for component in actor.get_components_by_class(unreal.InstancedStaticMeshComponent):
        removed['placeholder_instances'] += int(component.get_instance_count())
    actor_subsystem.destroy_actor(actor)
    removed['placeholder'] += 1
report['removed'] = removed
log('removed: {0}'.format(json.dumps(removed)))

meshes = {}
for variant in set(name for name, _ in sum((list(table) for table in RING_VARIANTS), [])):
    path = TREE_DIR + '/SM_Veg_' + variant
    mesh = unreal.EditorAssetLibrary.load_asset(path)
    if mesh is None:
        fail('pine mesh missing: ' + path)
    else:
        meshes[variant] = mesh
log('pine variants available: {0}'.format(len(meshes)))

cells = {}
for variant, x, y, z, yaw, scale, sink in instances:
    key = (int(math.floor(x / CELL_M)), int(math.floor(y / CELL_M)))
    cells.setdefault(key, {}).setdefault(variant, []).append((x, y, z, yaw, scale))

actors = []
for (cx, cy) in sorted(cells.keys()):
    location = unreal.Vector((cx + 0.5) * CELL_M * CM_PER_M, (cy + 0.5) * CELL_M * CM_PER_M, 0.0)
    actor = actor_subsystem.spawn_actor_from_class(unreal.Actor, location, unreal.Rotator())
    if actor is None:
        fail('could not spawn forest actor for cell {0},{1}'.format(cx, cy))
        continue
    actor.set_actor_label('{0}{1}_{2}'.format(PREFIX, cx, cy))
    far_cell = max(abs((cx + 0.5) * CELL_M), abs((cy + 0.5) * CELL_M)) > 900.0
    for variant, entries in sorted(cells[(cx, cy)].items()):
        mesh = meshes.get(variant)
        if mesh is None:
            continue
        component = unreal.new_object(unreal.HierarchicalInstancedStaticMeshComponent, actor)
        component.set_editor_property('static_mesh', mesh)
        try:
            component.set_editor_property('mobility', unreal.ComponentMobility.STATIC)
        except Exception as exc:  # noqa: BLE001
            warn('mobility: ' + str(exc)[:100])
        # beyond the shadow range of the property the trees stay out of the shadow pass
        component.set_editor_property('cast_shadow', not far_cell)
        for x, y, z, yaw, scale in entries:
            component.add_instance(unreal.Transform(
                unreal.Vector(x * CM_PER_M, y * CM_PER_M, z * CM_PER_M),
                unreal.Rotator(0.0, 0.0, yaw),
                unreal.Vector(scale, scale, scale)), True)
    actors.append(actor)

placed = sum(len(entries) for cell in cells.values() for entries in cell.values())
report['placement'] = {
    'actors': len(actors),
    'instances': placed,
    'cell_size_m': CELL_M,
    'components': sum(len(cell) for cell in cells.values()),
}
report['variants'] = {}
for variant in sorted(meshes.keys()):
    count = sum(len(entries) for cell in cells.values() for name, entries in cell.items() if name == variant)
    report['variants'][variant] = count
log('forest built: {0} instances in {1} actors'.format(placed, len(actors)))
log('variants: {0}'.format(json.dumps(report['variants'])))


# ---------------------------------------------------------------- verification
# Clearance, ground contact and instance distribution are the three things a misplaced forest gets
# wrong, and all three can be measured from the placement data itself.
min_property_gap = 1e9
min_road_gap = 1e9
worst_sink = 0.0
max_xy_error = 0.0
inside_property = 0
for variant, x, y, z, yaw, scale, sink in instances:
    gap = envelope_distance(x, y)
    if gap < min_property_gap:
        min_property_gap = gap
    if gap <= 0.0:
        inside_property += 1
    road_gap = road_distance(x, y)
    if road_gap < min_road_gap:
        min_road_gap = road_gap
    worst_sink = max(worst_sink, sink)

# read the instances back from the level: this proves the transforms really landed in the actors
read_back = 0
component_count = 0
for actor in actor_subsystem.get_all_level_actors():
    if not actor.get_actor_label().startswith(PREFIX):
        continue
    for component in actor.get_components_by_class(unreal.InstancedStaticMeshComponent):
        component_count += 1
        read_back += int(component.get_instance_count())
        for index in range(int(component.get_instance_count())):
            transform = component.get_instance_transform(index, True)
            location = transform.translation
            key = (int(math.floor(float(location.x) / CM_PER_M / CELL_M)),
                   int(math.floor(float(location.y) / CM_PER_M / CELL_M)))
            if key != (int(math.floor(actor.get_actor_location().x / CM_PER_M / CELL_M)),
                       int(math.floor(actor.get_actor_location().y / CM_PER_M / CELL_M))):
                max_xy_error += 1

report['clearance_m'] = {'property_min': round(min_property_gap, 2) if instances else None,
                         'road_min': round(min_road_gap, 2) if instances else None,
                         'property_hard_limit': PROPERTY_HARD_M,
                         'road_hard_limit': ROAD_HARD_M,
                         'instances_inside_property': inside_property,
                         'worst_sink_m': round(worst_sink, 3)}
report['read_back'] = {'instances': read_back, 'components': component_count,
                       'instances_outside_their_cell': max_xy_error}
report['outside_landscape_candidates'] = outside
report['no_ground_samples'] = no_ground_samples
legacy_left = len([actor for actor in actor_subsystem.get_all_level_actors()
                   if actor.get_actor_label().startswith(OLD_TREE_PREFIX)])

level_subsystem.save_current_level()
report['saved'] = True
log('level saved')

checks = {
    'placeholder_forest_replaced': legacy_left == 0 and (removed['placeholder'] > 0
                                                        or report['previous_placeholder_trees'] == 0),
    'no_legacy_placeholder_left': legacy_left == 0,
    'forest_actors_created': len(actors) > 10,
    'instance_count_in_range': 4000 <= placed <= 14000,
    'every_variant_used': all(count > 0 for count in report['variants'].values()) and len(meshes) >= 6,
    'property_clearance_respected': inside_property == 0 and min_property_gap >= PROPERTY_HARD_M - 0.1,
    'road_clearance_respected': min_road_gap >= ROAD_HARD_M - 0.1,
    'instances_read_back': read_back == placed,
    'instances_inside_their_actor_cell': max_xy_error == 0,
    'slope_sink_within_bounds': worst_sink <= SINK_MAX_M + 1e-6,
    'clearings_exist': mask_stats['clearing'] > 0,
    'steep_ground_rejected': mask_stats['slope'] > 0,
    'nothing_below_floor': report['elevation_m']['min'] is not None and report['elevation_m']['min'] >= GROUND_FLOOR_M,
    'road_mask_active': mask_stats['road'] > 0,
    'instancing_used': report['placement']['components'] > report['placement']['actors'],
    'level_saved': bool(report.get('saved')),
}
report['checks'] = checks
report['ok'] = all(checks.values())
report['result'] = 'OK' if report['ok'] else 'CHECK'
log('checks: {0}'.format(json.dumps(checks)))
log('result: {0}'.format(report['result']))

if not os.path.isdir(SAVED_DIR):
    os.makedirs(SAVED_DIR)
out_path = os.path.join(SAVED_DIR, 'phase4b_forest.json')
with open(out_path, 'w') as handle:
    json.dump(report, handle, indent=2, default=str)
log('report written: {0}'.format(out_path))
