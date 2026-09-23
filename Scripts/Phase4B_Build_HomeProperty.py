# -*- coding: utf-8 -*-
"""Phase 4B - player home property.

Builds the home property inside the Phase 4A world (Lvl_Rural) completely from
procedural content:

  1. materials  : one parametric master material + one instance per surface
  2. terrain    : the Phase 4A home pad is refined locally (level construction
                  area, natural slope around it, graded driveway out of it) -
                  the rest of the world is untouched
  3. meshes     : house, veranda, garage, shed, concrete yard, driveway, grill
                  and four pine variants are generated in C++
  4. forest     : instanced pines around the property (dense close by, thinning
                  with distance, stopping at the tree line)
  5. layout     : structures, vehicle, interaction test object and PlayerStart

Everything is idempotent: re-running replaces what Phase 4B created before.
"""

import json
import os

import unreal

LEVEL = '/Game/Game/Environment/Lvl_Rural'
HOME_DIR = '/Game/Game/Environment/Home'
MASTER = HOME_DIR + '/M_RuralSurface'
VEHICLE_CLASS = '/Game/Game/Vehicles/Base/BP_VehicleBase.BP_VehicleBase_C'
TEST_OBJECT_CLASS = '/Game/Game/Interaction/BP_InteractionTestObject.BP_InteractionTestObject_C'

# World space property anchors (meters) - must match the C++ spec defaults.
PROPERTY_CENTER = (750.0, 750.0)
HOUSE_CENTER = (760.0, 786.0)
PLAYER_START = (758.0, 773.0, 90.0)        # x, y, yaw (facing the house front door)
VEHICLE = (748.0, 764.0, 270.0)            # parked in the yard, nose towards the garage
TEST_OBJECT = (761.5, 776.5)

# Surface palette: name -> (base colour, mottle colour, roughness, metallic, mottle scale, mottle strength)
SURFACES = {
    'MI_Plaster':   ((0.72, 0.69, 0.62), (0.57, 0.54, 0.47), 0.78, 0.0, 0.55, 0.45),
    'MI_RoofTile':  ((0.30, 0.11, 0.08), (0.20, 0.07, 0.05), 0.85, 0.0, 0.90, 0.50),
    'MI_WoodTrim':  ((0.30, 0.19, 0.11), (0.20, 0.13, 0.08), 0.62, 0.0, 1.40, 0.45),
    'MI_WoodPlank': ((0.38, 0.28, 0.18), (0.26, 0.19, 0.12), 0.85, 0.0, 1.60, 0.60),
    'MI_MetalDoor': ((0.32, 0.34, 0.35), (0.26, 0.20, 0.16), 0.45, 0.65, 1.10, 0.55),
    'MI_Glass':     ((0.045, 0.055, 0.06), (0.05, 0.07, 0.08), 0.12, 0.0, 0.30, 0.30),
    'MI_Concrete':  ((0.40, 0.40, 0.39), (0.30, 0.30, 0.29), 0.86, 0.0, 0.35, 0.55),
    'MI_Gravel':    ((0.36, 0.34, 0.30), (0.27, 0.25, 0.22), 0.92, 0.0, 0.80, 0.60),
    'MI_Bark':      ((0.20, 0.145, 0.10), (0.12, 0.09, 0.065), 0.88, 0.0, 2.00, 0.55),
    'MI_Needles':   ((0.045, 0.115, 0.045), (0.075, 0.16, 0.06), 0.75, 0.0, 1.80, 0.50),
    'MI_Brick':     ((0.42, 0.24, 0.18), (0.30, 0.17, 0.13), 0.85, 0.0, 1.20, 0.50),
}

# label -> mesh asset name (all property meshes are authored in world XY and placed
# at the pad height, so the actors sit at the world origin)
STRUCTURES = [
    ('P4B_House', 'SM_P4B_House'),
    ('P4B_Veranda', 'SM_P4B_Veranda'),
    ('P4B_Garage', 'SM_P4B_Garage'),
    ('P4B_Shed', 'SM_P4B_Shed'),
    ('P4B_ConcreteYard', 'SM_P4B_ConcreteYard'),
    ('P4B_Driveway', 'SM_P4B_Driveway'),
    ('P4B_Grill', 'SM_P4B_Grill'),
]

report = {'steps': [], 'result': 'FAILED', 'failed': []}

level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
editor_subsystem = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
asset_tools = unreal.AssetToolsHelpers.get_asset_tools()


def log(message):
    unreal.log('P4B: ' + str(message))
    report['steps'].append(str(message))


def warn(message):
    unreal.log_warning('P4B: ' + str(message))
    report['failed'].append(str(message))


def actors():
    return list(actor_subsystem.get_all_level_actors())


def load(path):
    return unreal.EditorAssetLibrary.load_asset(path) if unreal.EditorAssetLibrary.does_asset_exist(path) else None


def save(asset):
    try:
        unreal.EditorAssetLibrary.save_loaded_asset(asset)
    except Exception as exc:  # noqa: BLE001
        warn('could not save asset: {0}'.format(exc))


def make_movable(component, mobility='MOVABLE'):
    try:
        component.unregister_component()
    except Exception:
        pass
    for value in (getattr(unreal.ComponentMobility, mobility, None), mobility):
        try:
            component.set_editor_property('mobility', value)
            break
        except Exception:
            continue
    try:
        component.reregister_component()
    except Exception:
        pass


def build_master_graph(master):
    """Parametric master material: base/mottle colour, roughness, metallic, mottle noise."""
    mel = unreal.MaterialEditingLibrary
    try:
        mel.delete_all_material_expressions(master)
    except Exception:
        pass

    uv = mel.create_material_expression(master, unreal.MaterialExpressionTextureCoordinate, -1250, 0)
    scale = mel.create_material_expression(master, unreal.MaterialExpressionScalarParameter, -1250, 150)
    scale.set_editor_property('parameter_name', 'MottleScale')
    scale.set_editor_property('default_value', 0.6)
    uv_scale = mel.create_material_expression(master, unreal.MaterialExpressionMultiply, -1000, 60)
    noise = mel.create_material_expression(master, unreal.MaterialExpressionNoise, -800, 60)
    for name, value in (('scale', 1.0), ('levels', 2), ('output_min', 0.0), ('output_max', 1.0)):
        try:
            noise.set_editor_property(name, value)
        except Exception:
            pass
    try:
        noise.set_editor_property('noise_function', unreal.NoiseFunction.NOISEFUNCTION_VALUE_ALU)
    except Exception:
        try:
            noise.set_editor_property('noise_function', unreal.NoiseFunction.NOISEFUNCTION_GRADIENT_ALU)
        except Exception:
            pass

    strength = mel.create_material_expression(master, unreal.MaterialExpressionScalarParameter, -800, 260)
    strength.set_editor_property('parameter_name', 'MottleStrength')
    strength.set_editor_property('default_value', 0.5)
    mottle = mel.create_material_expression(master, unreal.MaterialExpressionMultiply, -560, 160)

    base = mel.create_material_expression(master, unreal.MaterialExpressionVectorParameter, -800, -420)
    base.set_editor_property('parameter_name', 'BaseColor')
    base.set_editor_property('default_value', unreal.LinearColor(0.7, 0.7, 0.68, 1.0))
    mottle_color = mel.create_material_expression(master, unreal.MaterialExpressionVectorParameter, -800, -240)
    mottle_color.set_editor_property('parameter_name', 'MottleColor')
    mottle_color.set_editor_property('default_value', unreal.LinearColor(0.55, 0.55, 0.53, 1.0))
    blend = mel.create_material_expression(master, unreal.MaterialExpressionLinearInterpolate, -300, -300)

    roughness = mel.create_material_expression(master, unreal.MaterialExpressionScalarParameter, -300, 380)
    roughness.set_editor_property('parameter_name', 'Roughness')
    roughness.set_editor_property('default_value', 0.8)
    metallic = mel.create_material_expression(master, unreal.MaterialExpressionScalarParameter, -300, 520)
    metallic.set_editor_property('parameter_name', 'Metallic')
    metallic.set_editor_property('default_value', 0.0)

    mel.connect_material_expressions(uv, '', uv_scale, 'A')
    mel.connect_material_expressions(scale, '', uv_scale, 'B')
    connected = False
    for pin in ('Position', 'position', 'XYZ', ''):
        try:
            mel.connect_material_expressions(uv_scale, '', noise, pin)
            connected = True
            break
        except Exception:
            continue
    if not connected:
        warn('could not connect the noise input of the master material')
    mel.connect_material_expressions(noise, '', mottle, 'A')
    mel.connect_material_expressions(strength, '', mottle, 'B')
    mel.connect_material_expressions(base, '', blend, 'A')
    mel.connect_material_expressions(mottle_color, '', blend, 'B')
    mel.connect_material_expressions(mottle, '', blend, 'Alpha')

    mel.connect_material_property(blend, '', unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(roughness, '', unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(metallic, '', unreal.MaterialProperty.MP_METALLIC)
    mel.recompile_material(master)
    save(master)


def ensure_materials():
    """Master material + one instance per surface (idempotent)."""
    created = []
    master = load(MASTER)
    if master is None:
        master = asset_tools.create_asset('M_RuralSurface', HOME_DIR, unreal.Material, unreal.MaterialFactoryNew())
        if master is None:
            warn('could not create the master material')
            return created
        log('created master material ' + MASTER)
    existing = []
    try:
        existing = [str(x) for x in unreal.MaterialEditingLibrary.get_vector_parameter_names(master)]
    except Exception:
        pass
    if 'BaseColor' not in existing:
        build_master_graph(master)
        log('master material graph built')
    created.append(MASTER)

    mel = unreal.MaterialEditingLibrary
    for name in sorted(SURFACES.keys()):
        base, mottle, rough, metal, mscale, mstrength = SURFACES[name]
        path = HOME_DIR + '/' + name
        instance = load(path)
        if instance is None:
            instance = asset_tools.create_asset(name, HOME_DIR, unreal.MaterialInstanceConstant,
                                                unreal.MaterialInstanceConstantFactoryNew())
            if instance is None:
                warn('could not create material instance ' + name)
                continue
        mel.set_material_instance_parent(instance, master)
        mel.set_material_instance_vector_parameter_value(
            instance, 'BaseColor', unreal.LinearColor(base[0], base[1], base[2], 1.0))
        mel.set_material_instance_vector_parameter_value(
            instance, 'MottleColor', unreal.LinearColor(mottle[0], mottle[1], mottle[2], 1.0))
        mel.set_material_instance_scalar_parameter_value(instance, 'Roughness', rough)
        mel.set_material_instance_scalar_parameter_value(instance, 'Metallic', metal)
        mel.set_material_instance_scalar_parameter_value(instance, 'MottleScale', mscale)
        mel.set_material_instance_scalar_parameter_value(instance, 'MottleStrength', mstrength)
        save(instance)
        created.append(path)
    return created


def set_mobility(component, mobility):
    for value in (getattr(unreal.ComponentMobility, mobility, None), mobility):
        try:
            component.set_editor_property('mobility', value)
            return True
        except Exception:
            continue
    return False


def assign_mesh(actor, mesh, mobility='STATIC'):
    """Sets the mesh on a spawned StaticMeshActor without the static-mobility warning."""
    component = actor.get_components_by_class(unreal.StaticMeshComponent)[0]
    try:
        component.unregister_component()
    except Exception:
        pass
    set_mobility(component, 'MOVABLE')
    component.set_editor_property('static_mesh', mesh)
    set_mobility(component, mobility)
    try:
        component.reregister_component()
    except Exception:
        pass
    return component


def ground_z(world, x_m, y_m):
    """Terrain height (meters) measured through collision; None when nothing is hit."""
    start = unreal.Vector(x_m * 100.0, y_m * 100.0, 400000.0)
    end = unreal.Vector(x_m * 100.0, y_m * 100.0, -60000.0)
    hit = unreal.SystemLibrary.line_trace_single(
        world, start, end, unreal.TraceTypeQuery.ECC_VISIBILITY, True, [],
        unreal.DrawDebugTrace.NONE, True)
    if hit is None:
        return None
    data = hit.to_dict() if hasattr(hit, 'to_dict') else None
    if not isinstance(data, dict) or not data.get('blocking_hit', True):
        return None
    location = data.get('location')
    try:
        return round(float(location.z) / 100.0, 2)
    except Exception:
        return None


def field(struct, name, default=None):
    try:
        return getattr(struct, name)
    except Exception:
        return default


def jsonable(value):
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(v) for v in value]
    if isinstance(value, (int, float, bool, str)) or value is None:
        return value
    try:
        return str(value)
    except Exception:
        return None


def flag(struct, name):
    """Reads a UPROPERTY bool; UE Python drops the leading 'b' on bool property names."""
    for candidate in ('b_' + name, name):
        try:
            return bool(getattr(struct, candidate))
        except Exception:
            continue
    return False


def number(struct, name, default=0.0):
    """Numeric field read that keeps a legitimate 0 (never falls back on falsy values)."""
    value = field(struct, name, None)
    try:
        return float(value)
    except Exception:
        return default


def probe(world, x_m, y_m):
    """World height of whatever the ground line trace hits, plus the hit actor label.

    Uses simple collision (what the player capsule collides with).
    """
    start = unreal.Vector(x_m * 100.0, y_m * 100.0, 400000.0)
    end = unreal.Vector(x_m * 100.0, y_m * 100.0, -60000.0)
    hit = unreal.SystemLibrary.line_trace_single(
        world, start, end, unreal.TraceTypeQuery.ECC_VISIBILITY, False, [],
        unreal.DrawDebugTrace.NONE, True)
    if hit is None:
        return {'z_m': None, 'actor': None}
    data = hit.to_dict() if hasattr(hit, 'to_dict') else None
    if not isinstance(data, dict) or not data.get('blocking_hit', True):
        return {'z_m': None, 'actor': None}
    location = data.get('location')
    try:
        height = round(float(location.z) / 100.0, 2)
    except Exception:
        height = None
    label = None
    actor = data.get('hit_actor')
    if actor is None:
        actor = data.get('actor')
    if actor is not None:
        try:
            label = actor.get_actor_label()
        except Exception:
            try:
                label = actor.get_name()
            except Exception:
                label = None
    return {'z_m': height, 'actor': label}


def collision_info(mesh):
    """Simple-collision evidence for a static mesh asset (body setup + element counts)."""
    info = {'body_setup': False, 'convex': 0, 'box': 0, 'sphere': 0, 'capsule': 0}
    body = None
    try:
        body = mesh.get_editor_property('body_setup')
    except Exception:
        body = None
    if body is None:
        return info
    info['body_setup'] = True
    try:
        agg = body.get_editor_property('agg_geom')
    except Exception:
        return info
    for name, key in (('convex_elems', 'convex'), ('box_elems', 'box'),
                      ('sphere_elems', 'sphere'), ('sphyl_elems', 'capsule')):
        try:
            info[key] = len(agg.get_editor_property(name))
        except Exception:
            continue
    return info


def struct_report(struct, names):
    out = {}
    for name in names:
        out[name] = jsonable(field(struct, name))
    return out


def build_spec():
    spec = unreal.Phase4BHomeSpec()
    spec.set_editor_property('property_center',
                             unreal.Vector2D(PROPERTY_CENTER[0], PROPERTY_CENTER[1]))
    return spec


# ------------------------------------------------------------------ level + materials
level_subsystem.load_level(LEVEL)
world = editor_subsystem.get_editor_world()
log('level loaded: ' + world.get_path_name())

materials = ensure_materials()
report['materials'] = materials
log('materials ready: {0}'.format(len(materials)))

# Anything Phase 4B created before is replaced (P4B_* actors + legacy Phase 4A layout).
try:
    cleared = int(unreal.Phase4BPropertyBuilder.clear_property_actors(world))
except Exception as exc:  # noqa: BLE001
    cleared = 0
    warn('clear_property_actors failed: {0}'.format(exc))
report['cleared_actors'] = cleared
log('cleared {0} previous Phase 4B actors'.format(cleared))

# ------------------------------------------------------------------ terrain, meshes, forest
spec = build_spec()

terrain = unreal.Phase4BPropertyBuilder.refine_home_terrain(world, spec)
report['terrain'] = struct_report(terrain, (
    'success', 'message', 'pad_height_m', 'edited_component_count', 'work_area_spread_m',
    'natural_slope_spread_m', 'natural_slope_max_percent', 'driveway_length_m',
    'driveway_start_height_m', 'driveway_end_height_m', 'driveway_max_grade',
    'driveway_points_cm', 'elevation_samples_m', 'readback_samples_m'))
pad = number(terrain, 'pad_height_m', 0.0)
report['pad_height_m'] = round(pad, 2)
log('terrain: ' + str(field(terrain, 'message')))
log('pad={0:.2f} m workAreaSpread={1:.3f} m naturalSpread={2:.2f} m maxSlope={3:.1f}%'.format(
    pad, number(terrain, 'work_area_spread_m', 0.0), number(terrain, 'natural_slope_spread_m', 0.0),
    number(terrain, 'natural_slope_max_percent', 0.0)))
log('driveway length={0:.0f} m {1:.2f} -> {2:.2f} m grade={3:.1f}%'.format(
    number(terrain, 'driveway_length_m', 0.0), number(terrain, 'driveway_start_height_m', 0.0),
    number(terrain, 'driveway_end_height_m', 0.0), number(terrain, 'driveway_max_grade', 0.0) * 100.0))

assets = unreal.Phase4BPropertyBuilder.build_property_assets(world, spec)
report['assets'] = struct_report(assets, ('success', 'message', 'created_assets', 'warnings'))
log('assets: ' + str(field(assets, 'message')))
for warning in (field(assets, 'warnings', []) or []):
    warn(str(warning))
for entry in (field(assets, 'created_assets', []) or []):
    log('  ' + str(entry))

forest = unreal.Phase4BPropertyBuilder.place_pine_forest(world, spec)
report['forest'] = struct_report(forest, (
    'success', 'message', 'tree_instance_count', 'tree_instances_per_variant',
    'tree_nearest_to_property_m', 'trees_inside_open_area', 'removed_actors', 'warnings'))
log('forest: ' + str(field(forest, 'message')))
log('trees={0} nearest={1:.1f} m insideProperty={2}'.format(
    field(forest, 'tree_instance_count'), float(field(forest, 'tree_nearest_to_property_m', 0.0)),
    field(forest, 'trees_inside_open_area')))
log('trees per variant: ' + json.dumps(jsonable(field(forest, 'tree_instances_per_variant', {}))))

# ------------------------------------------------------------------ layout
removed = []
for actor in actors():
    label = actor.get_actor_label()
    if label.startswith('Home_') or label in ('Vehicle', 'InteractionTestObject', 'PlayerStart_Home'):
        actor_subsystem.destroy_actor(actor)
        removed.append(label)
report['removed_legacy_actors'] = removed
log('removed {0} legacy Phase 4A layout actors'.format(len(removed)))

placed = []
structure_labels = []
for label, asset_name in STRUCTURES:
    mesh = load(HOME_DIR + '/' + asset_name)
    if mesh is None:
        warn('mesh asset missing: ' + asset_name)
        continue
    actor = actor_subsystem.spawn_actor_from_class(
        unreal.StaticMeshActor, unreal.Vector(0.0, 0.0, pad * 100.0), unreal.Rotator(0.0, 0.0, 0.0))
    if actor is None:
        warn('could not spawn ' + label)
        continue
    actor.set_actor_label(label)
    assign_mesh(actor, mesh, 'STATIC')
    placed.append(actor)
    structure_labels.append(label)
report['structures'] = structure_labels
log('placed {0} property structures'.format(len(structure_labels)))

# Vehicle, interaction test object and the player start.
vehicle_class = unreal.load_class(None, VEHICLE_CLASS)
if vehicle_class is not None:
    vehicle = actor_subsystem.spawn_actor_from_class(
        vehicle_class,
        unreal.Vector(VEHICLE[0] * 100.0, VEHICLE[1] * 100.0, (pad + 0.06 + 0.63) * 100.0),
        unreal.Rotator(0.0, 0.0, VEHICLE[2]))
    if vehicle is not None:
        vehicle.set_actor_label('Vehicle')
        placed.append(vehicle)
    else:
        warn('could not spawn the vehicle')
else:
    warn('vehicle class missing: ' + VEHICLE_CLASS)

test_class = unreal.load_class(None, TEST_OBJECT_CLASS)
if test_class is not None:
    test_object = actor_subsystem.spawn_actor_from_class(
        test_class,
        unreal.Vector(TEST_OBJECT[0] * 100.0, TEST_OBJECT[1] * 100.0, (pad + 0.06 + 0.45) * 100.0),
        unreal.Rotator(0.0, 0.0, 180.0))
    if test_object is not None:
        test_object.set_actor_label('InteractionTestObject')
        placed.append(test_object)
    else:
        warn('could not spawn the interaction test object')
else:
    warn('interaction test object class missing: ' + TEST_OBJECT_CLASS)

start_class = unreal.load_class(None, '/Script/Engine.PlayerStart')
start = None
if start_class is not None:
    start = actor_subsystem.spawn_actor_from_class(
        start_class,
        unreal.Vector(PLAYER_START[0] * 100.0, PLAYER_START[1] * 100.0, (pad + 0.96) * 100.0),
        unreal.Rotator(0.0, 0.0, PLAYER_START[2]))
    if start is not None:
        start.set_actor_label('PlayerStart_Home')
        placed.append(start)
        # The spawn point has to exist before World Partition streams any cell,
        # otherwise the game spawns the player at the world origin.
        try:
            start.set_editor_property('is_spatially_loaded', False)
            log('PlayerStart_Home marked as always loaded')
        except Exception as exc:  # noqa: BLE001
            warn('could not mark the PlayerStart as always loaded: {0}'.format(exc))
    else:
        warn('could not spawn PlayerStart_Home')
else:
    warn('PlayerStart class not found')

report['placed'] = [a.get_actor_label() for a in placed if a is not None]
log('placed {0} actors in total'.format(len(report['placed'])))

# Collision evidence for the generated meshes (the player has to bump into them).
report['mesh_collision'] = {}
for label, asset_name in STRUCTURES:
    mesh = load(HOME_DIR + '/' + asset_name)
    if mesh is None:
        continue
    report['mesh_collision'][asset_name] = collision_info(mesh)
log('mesh collision: ' + json.dumps(report['mesh_collision']))

# Geometry check: where the generated meshes actually sit and how the placed actors collide.
report['mesh_bounds'] = {}
for label, asset_name in STRUCTURES:
    mesh = load(HOME_DIR + '/' + asset_name)
    if mesh is None:
        continue
    entry = {}
    try:
        bounds = mesh.get_bounds()
        entry['origin_m'] = [round(float(v) / 100.0, 2) for v in (bounds.origin.x, bounds.origin.y, bounds.origin.z)]
        entry['extent_m'] = [round(float(v) / 100.0, 2) for v in
                             (bounds.box_extent.x, bounds.box_extent.y, bounds.box_extent.z)]
    except Exception as exc:  # noqa: BLE001
        entry['bounds'] = str(exc)
    report['mesh_bounds'][asset_name] = entry
log('mesh bounds: ' + json.dumps(report['mesh_bounds']))

report['structure_actors'] = {}
for actor in actors():
    label = actor.get_actor_label()
    if label not in structure_labels:
        continue
    location = actor.get_actor_location()
    entry = {'location_m': [round(float(v) / 100.0, 2) for v in (location.x, location.y, location.z)]}
    try:
        origin, extent = actor.get_actor_bounds(False)
        entry['bounds_m'] = {
            'min': [round((float(o) - float(e)) / 100.0, 2) for o, e in
                    ((origin.x, extent.x), (origin.y, extent.y), (origin.z, extent.z))],
            'max': [round((float(o) + float(e)) / 100.0, 2) for o, e in
                    ((origin.x, extent.x), (origin.y, extent.y), (origin.z, extent.z))]}
    except Exception as exc:  # noqa: BLE001
        entry['bounds'] = str(exc)
    for component in actor.get_components_by_class(unreal.StaticMeshComponent):
        try:
            body = component.get_editor_property('body_instance')
            entry['collision_enabled'] = str(body.get_editor_property('collision_enabled'))
            entry['collision_profile'] = str(body.get_editor_property('collision_profile_name'))
        except Exception as exc:  # noqa: BLE001
            entry['collision'] = str(exc)
        break
    report['structure_actors'][label] = entry
log('structure actors: ' + json.dumps(report['structure_actors']))

level_subsystem.save_current_level()
report['saved'] = True
log('level saved')

# ------------------------------------------------------------------ validation
import os as _os  # noqa: E402

level_subsystem.load_level(LEVEL)
world = editor_subsystem.get_editor_world()

probes = {
    'house_front (760,780)': (760.0, 780.0),
    'veranda_apron (760,798)': (760.0, 798.0),
    'yard_centre (752,766)': (752.0, 766.0),
    'garage_apron (750,754)': (750.0, 754.0),
    'shed_apron (733,744)': (733.0, 744.0),
    'driveway_start (733,762)': (733.0, 762.0),
    'driveway_mid (688,710)': (688.0, 710.0),
    'driveway_join (721.7,636.7)': (721.7, 636.7),
    'forest_30m_east (780,790)': (780.0, 790.0),
    'forest_60m_south (750,690)': (750.0, 690.0),
    'forest_120m_west (630,750)': (630.0, 750.0),
    'slope_200m_north_west (610,890)': (610.0, 890.0),
    'lowland_600m_south_west (300,300)': (300.0, 300.0),
    'property_north_edge (750,830)': (750.0, 830.0),
}
traces = {}
probe_actors = {}
for name, (x, y) in probes.items():
    result = probe(world, x, y)
    traces[name] = result['z_m']
    probe_actors[name] = result['actor']
report['traces'] = traces
report['probe_actors'] = probe_actors
log('traces: ' + json.dumps(traces))
log('trace hit actors: ' + json.dumps(probe_actors))

labels_now = ['{0} [{1}]'.format(a.get_actor_label(), a.get_class().get_name()) for a in actors()]
report['actor_count'] = len(labels_now)
report['landscape_actors'] = [x for x in labels_now if 'Landscape' in x]
report['p4b_actors'] = [x for x in labels_now if x.startswith('P4B_')]
report['player_starts'] = {}
for actor in actors():
    if actor.get_actor_label().startswith('PlayerStart'):
        entry = {'class': actor.get_class().get_name(), 'location': str(actor.get_actor_location())}
        try:
            location = actor.get_actor_location()
            entry['location_m'] = [round(float(location.x) / 100.0, 2), round(float(location.y) / 100.0, 2),
                                   round(float(location.z) / 100.0, 2)]
        except Exception:  # noqa: BLE001
            entry['location_m'] = None
        try:
            entry['is_spatially_loaded'] = str(actor.get_editor_property('is_spatially_loaded'))
        except Exception:  # noqa: BLE001
            entry['is_spatially_loaded'] = 'n/a'
        report['player_starts'][actor.get_actor_label()] = entry
report['has_vehicle'] = any(x.startswith('Vehicle [') for x in labels_now)
report['has_interaction'] = any(x.startswith('InteractionTestObject [') for x in labels_now)
report['world_partition_is_none'] = (
    world.get_world_settings().get_editor_property('world_partition') is None)
log('player starts: ' + json.dumps(report['player_starts']))
log('actor count: {0}, landscape actors: {1}'.format(report['actor_count'], len(report['landscape_actors'])))


def near(value, target, tolerance):
    return value is not None and abs(float(value) - float(target)) <= tolerance


tree_count = int(number(forest, 'tree_instance_count', 0.0))
driveway_grade = number(terrain, 'driveway_max_grade', 1.0)
work_spread = number(terrain, 'work_area_spread_m', 99.0)
natural_spread = number(terrain, 'natural_slope_spread_m', 0.0)
natural_slope = number(terrain, 'natural_slope_max_percent', 99.0)
start_location = report['player_starts'].get('PlayerStart_Home', {}).get('location_m') or [0.0, 0.0, 0.0]
start_ok = (near(start_location[0], PLAYER_START[0], 0.5) and near(start_location[1], PLAYER_START[1], 0.5)
            and near(start_location[2], pad + 0.96, 0.6))

checks = {
    'terrain_refined': flag(terrain, 'success') and pad > 100.0,
    'pad_preserved': near(traces.get('yard_centre (752,766)'), pad + 0.06, 0.35),
    'work_area_level': work_spread < 0.05,
    'natural_slope_present': natural_spread > 3.0 and natural_slope < 45.0,
    'driveway_descends': (number(terrain, 'driveway_start_height_m', 0.0)
                          - number(terrain, 'driveway_end_height_m', 0.0)) > 5.0,
    'driveway_grade_ok': driveway_grade < 0.09,
    'driveway_long_enough': number(terrain, 'driveway_length_m', 0.0) > 120.0,
    'meshes_created': flag(assets, 'success') and len(field(assets, 'created_assets', []) or []) >= 15,
    'meshes_have_collision': all(entry.get('convex', 0) >= 1 for name, entry in report['mesh_collision'].items()
                                 if name != 'SM_P4B_Driveway'),
    'structures_placed': len(structure_labels) >= 7,
    'forest_dense': flag(forest, 'success') and tree_count >= 800,
    'forest_clear_of_property': (number(forest, 'trees_inside_open_area', 1.0) == 0.0
                                 and number(forest, 'tree_nearest_to_property_m', 0.0) >= 2.0),
    'forest_variants': len(field(forest, 'tree_instances_per_variant', {}) or {}) >= 4,
    'forest_follows_terrain': (traces.get('forest_30m_east (780,790)') is not None
                               and traces.get('lowland_600m_south_west (300,300)') is not None),
    'landscape_untouched': len(report['landscape_actors']) == 65,
    'world_partition_enabled': not report['world_partition_is_none'],
    'player_start_placed': 'PlayerStart_Home' in report['player_starts'],
    'player_start_always_loaded': report['player_starts'].get('PlayerStart_Home', {}).get(
        'is_spatially_loaded', 'True') == 'False',
    'player_start_height': start_ok,
    'vehicle_present': report['has_vehicle'],
    'interaction_present': report['has_interaction'],
}
report['checks'] = checks
report['ok'] = all(checks.values())
report['result'] = 'OK' if report['ok'] else 'CHECK'
log('checks: ' + json.dumps(checks))
log('result: ' + report['result'])

out_dir = _os.path.join(_os.environ.get('TEMP', '.'), 'MyProject_Phase4B')
try:
    _os.makedirs(out_dir)
except Exception:
    pass
with open(_os.path.join(out_dir, 'phase4b_build.json'), 'w') as handle:
    json.dump(report, handle, indent=2, default=str)
log('report written: ' + _os.path.join(out_dir, 'phase4b_build.json'))
