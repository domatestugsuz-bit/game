# -*- coding: utf-8 -*-
"""Phase 4B-1 - realistic rural Turkish house.

Replaces the Phase 4B graybox house (four wall blocks) with a properly built
single storey family house on the existing home pad:

  1. materials : 24 parametric material instances under House/Materials
  2. assets    : the C++ builder generates the architecture kit (foundation,
                 exterior and interior walls with real openings, floors,
                 ceilings, pitched roof, chimney, door/window joinery, glazing,
                 trim, wall details) plus the furniture and prop meshes
  3. layout    : the house is placed, each door leaf, furniture piece and
                 interior light individually, and the Phase 4B placeholder is
                 removed once the new house exists
  4. validation: collision measurements (size, wall thickness, floor, ceiling,
                 roof pitch, chimney, doorway clearance, walkability, furniture
                 fit) plus Python side sanity traces

Everything is idempotent: re-running replaces what Phase 4B-1 created before.
"""

import json
import os

import unreal

LEVEL = '/Game/Game/Environment/Lvl_Rural'
HOUSE_DIR = '/Game/Game/Environment/House'
MAT_DIR = HOUSE_DIR + '/Materials'
MASTER = '/Game/Game/Environment/Home/M_RuralSurface'

# House placement (meters, world space) - must match the C++ spec defaults.
HOUSE_CENTER = (760.0, 785.8)
FOOTPRINT = (12.04, 9.0)
PAD_HEIGHT = 147.492                    # Phase 4A/4B home pad

# Surface palette: name -> (base, mottle, roughness, metallic, mottle scale, strength)
SURFACES = {
    'MI_Plaster':    ((0.72, 0.69, 0.62), (0.56, 0.53, 0.46), 0.80, 0.0, 0.55, 0.45),
    'MI_WallPaint':  ((0.88, 0.86, 0.81), (0.80, 0.78, 0.73), 0.85, 0.0, 0.35, 0.35),
    'MI_Ceiling':    ((0.93, 0.93, 0.91), (0.88, 0.88, 0.86), 0.88, 0.0, 0.40, 0.25),
    'MI_FloorWood':  ((0.40, 0.27, 0.16), (0.26, 0.17, 0.10), 0.65, 0.0, 1.60, 0.55),
    'MI_FloorTile':  ((0.74, 0.72, 0.68), (0.62, 0.60, 0.56), 0.30, 0.0, 1.20, 0.40),
    'MI_Concrete':   ((0.42, 0.42, 0.41), (0.32, 0.32, 0.31), 0.86, 0.0, 0.35, 0.55),
    'MI_StoneBase':  ((0.34, 0.33, 0.31), (0.26, 0.25, 0.23), 0.90, 0.0, 0.90, 0.60),
    'MI_RoofTile':   ((0.30, 0.11, 0.08), (0.20, 0.07, 0.05), 0.85, 0.0, 0.90, 0.50),
    'MI_WoodTrim':   ((0.52, 0.40, 0.27), (0.40, 0.30, 0.20), 0.60, 0.0, 1.40, 0.40),
    'MI_WoodDark':   ((0.24, 0.16, 0.10), (0.17, 0.11, 0.07), 0.70, 0.0, 1.50, 0.45),
    'MI_DoorInt':    ((0.58, 0.43, 0.28), (0.46, 0.33, 0.20), 0.65, 0.0, 1.20, 0.35),
    'MI_DoorExt':    ((0.32, 0.20, 0.12), (0.24, 0.14, 0.08), 0.60, 0.0, 1.20, 0.40),
    'MI_Metal':      ((0.52, 0.53, 0.55), (0.40, 0.41, 0.43), 0.35, 0.85, 0.80, 0.40),
    'MI_WhiteMetal': ((0.86, 0.87, 0.88), (0.76, 0.77, 0.78), 0.35, 0.25, 0.60, 0.35),
    'MI_Glass':      ((0.10, 0.14, 0.16), (0.14, 0.18, 0.20), 0.08, 0.0, 0.30, 0.30),
    'MI_Fabric':     ((0.30, 0.26, 0.22), (0.24, 0.20, 0.17), 0.90, 0.0, 1.80, 0.35),
    'MI_FabricRed':  ((0.45, 0.18, 0.13), (0.34, 0.13, 0.10), 0.90, 0.0, 1.60, 0.45),
    'MI_Carpet':     ((0.36, 0.22, 0.16), (0.28, 0.16, 0.12), 0.95, 0.0, 2.20, 0.50),
    'MI_Counter':    ((0.20, 0.19, 0.18), (0.15, 0.14, 0.13), 0.35, 0.10, 0.70, 0.35),
    'MI_Ceramic':    ((0.94, 0.94, 0.93), (0.86, 0.86, 0.85), 0.12, 0.0, 0.50, 0.20),
    'MI_Mirror':     ((0.78, 0.80, 0.82), (0.70, 0.72, 0.74), 0.04, 1.00, 0.30, 0.15),
    'MI_LampShade':  ((0.96, 0.92, 0.80), (0.90, 0.85, 0.72), 0.55, 0.0, 0.60, 0.25),
    'MI_Curtain':    ((0.66, 0.62, 0.55), (0.56, 0.52, 0.46), 0.92, 0.0, 1.40, 0.35),
    'MI_Mattress':   ((0.92, 0.91, 0.88), (0.84, 0.83, 0.80), 0.80, 0.0, 0.80, 0.25),
}

report = {'steps': [], 'result': 'FAILED', 'failed': []}

level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
editor_subsystem = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
asset_tools = unreal.AssetToolsHelpers.get_asset_tools()


def log(message):
    unreal.log('P4B1: ' + str(message))
    report['steps'].append(str(message))


def warn(message):
    unreal.log_warning('P4B1: ' + str(message))
    report['failed'].append(str(message))


def load(path):
    return unreal.EditorAssetLibrary.load_asset(path) if unreal.EditorAssetLibrary.does_asset_exist(path) else None


def save(asset):
    try:
        unreal.EditorAssetLibrary.save_loaded_asset(asset)
    except Exception as exc:  # noqa: BLE001
        warn('could not save asset: {0}'.format(exc))


def ensure_materials():
    """Master material reference + one instance per surface (idempotent)."""
    master = load(MASTER)
    if master is None:
        warn('the Phase 4B master material is missing: ' + MASTER)
        return []
    mel = unreal.MaterialEditingLibrary
    created = []
    for name in sorted(SURFACES.keys()):
        base, mottle, rough, metal, mscale, mstrength = SURFACES[name]
        path = MAT_DIR + '/' + name
        instance = load(path)
        if instance is None:
            instance = asset_tools.create_asset(name, MAT_DIR, unreal.MaterialInstanceConstant,
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


def set_prop(obj, name, value):
    """Sets a UPROPERTY; bool properties may be exposed with or without the b_ prefix."""
    for candidate in ('b_' + name, name):
        try:
            obj.set_editor_property(candidate, value)
            return True
        except Exception:  # noqa: BLE001
            continue
    warn('could not set property ' + name)
    return False


def field(struct, name, default=None):
    for candidate in ('b_' + name, name):
        try:
            return getattr(struct, candidate)
        except Exception:  # noqa: BLE001
            continue
    return default


def flag(struct, name):
    return bool(field(struct, name, False))


def number(struct, name, default=0.0):
    try:
        return float(field(struct, name, default))
    except Exception:  # noqa: BLE001
        return default


def make_spec():
    spec = unreal.Phase4B1HouseSpec()
    set_prop(spec, 'house_center', unreal.Vector2D(HOUSE_CENTER[0], HOUSE_CENTER[1]))
    set_prop(spec, 'footprint', unreal.Vector2D(FOOTPRINT[0], FOOTPRINT[1]))
    set_prop(spec, 'pad_height_m', PAD_HEIGHT)
    set_prop(spec, 'interior_lights', True)
    set_prop(spec, 'furniture', True)
    return spec


def ground_z(world, x_m, y_m, start_z_m=400.0, label=''):
    """Height (meters) of the first collision hit below start_z_m."""
    start = unreal.Vector(x_m * 100.0, y_m * 100.0, start_z_m * 100.0)
    end = unreal.Vector(x_m * 100.0, y_m * 100.0, -600.0)
    hit = unreal.SystemLibrary.line_trace_single(
        world, start, end, unreal.TraceTypeQuery.ECC_VISIBILITY, True, [],
        unreal.DrawDebugTrace.NONE, True)
    if hit is None:
        return None
    data = hit.to_dict() if hasattr(hit, 'to_dict') else None
    if not isinstance(data, dict) or not data.get('blocking_hit', True):
        return None
    try:
        return round(float(data.get('location').z) / 100.0, 3)
    except Exception:  # noqa: BLE001
        return None


def room_rows(report_struct):
    rows = []
    rooms = field(report_struct, 'rooms', []) or []
    for room in rooms:
        size = field(room, 'size_m', None)
        size_m = [round(float(size.x), 2), round(float(size.y), 2)] if size is not None else [0.0, 0.0]
        centre = field(room, 'center_m', None)
        centre_m = [round(float(centre.x), 2), round(float(centre.y), 2)] if centre is not None else [0.0, 0.0]
        rows.append({
            'room': str(field(room, 'room', '')),
            'size_m': size_m,
            'area_m2': round(number(room, 'area_m2'), 2),
            'ceiling_height_m': round(number(room, 'ceiling_height_m'), 2),
            'doors': int(number(room, 'doors')),
            'windows': int(number(room, 'windows')),
            'centre_m': centre_m,
            'contents': str(field(room, 'contents', '')),
        })
    rows.sort(key=lambda entry: -entry['area_m2'])
    return rows


def dict_of(struct, name):
    value = field(struct, name, None)
    out = {}
    if value is None:
        return out
    try:
        for key in value.keys():
            out[str(key)] = value[key]
    except Exception:  # noqa: BLE001
        pass
    return out


# ----------------------------------------------------------------- main flow
if not level_subsystem.load_level(LEVEL):
    warn('could not load ' + LEVEL)
else:
    world = editor_subsystem.get_editor_world()
    log('level loaded: ' + LEVEL)

    # 1 - materials
    materials = ensure_materials()
    report['materials'] = materials
    log('material instances ready: {0}'.format(len(materials)))

    spec = make_spec()

    # 2 - assets
    assets_report = unreal.Phase4B1HouseBuilder.build_house_assets(world, spec)
    report['assets'] = {
        'success': flag(assets_report, 'success'),
        'message': str(field(assets_report, 'message', '')),
        'created': [str(x) for x in (field(assets_report, 'created_assets', []) or [])],
        'warnings': [str(x) for x in (field(assets_report, 'warnings', []) or [])],
        'triangles': int(number(assets_report, 'mesh_triangles')),
        'exterior_wall_panels': int(number(assets_report, 'exterior_wall_panels')),
        'interior_wall_panels': int(number(assets_report, 'interior_wall_panels')),
        'doors': int(number(assets_report, 'doors')),
        'windows': int(number(assets_report, 'windows')),
        'light_fixtures': int(number(assets_report, 'light_fixtures')),
    }
    log('assets: ' + report['assets']['message'])
    if not report['assets']['success']:
        warn('the house asset kit was not generated')

    # 3 - layout
    layout_report = unreal.Phase4B1HouseBuilder.build_house_layout(world, spec)
    report['layout'] = {
        'success': flag(layout_report, 'success'),
        'message': str(field(layout_report, 'message', '')),
        'actors': [str(x) for x in (field(layout_report, 'created_actors', []) or [])],
        'removed': [str(x) for x in (field(layout_report, 'removed_actors', []) or [])],
        'furniture_items': int(number(layout_report, 'furniture_items')),
        'doors': int(number(layout_report, 'doors')),
        'windows': int(number(layout_report, 'windows')),
        'lights': int(number(layout_report, 'light_fixtures')),
        'pad_height_m': round(number(layout_report, 'pad_height_m'), 3),
        'floor_level_m': round(number(layout_report, 'floor_level_m'), 3),
        'eave_height_m': round(number(layout_report, 'eave_height_m'), 3),
        'ridge_height_m': round(number(layout_report, 'ridge_height_m'), 3),
        'chimney_top_m': round(number(layout_report, 'chimney_top_m'), 3),
        'gross_footprint_m2': round(number(layout_report, 'gross_footprint_m2'), 2),
        'net_interior_m2': round(number(layout_report, 'net_interior_m2'), 2),
        'room_area_total_m2': round(number(layout_report, 'room_area_total_m2'), 2),
        'interior_wall_area_m2': round(number(layout_report, 'interior_wall_volume_m2'), 2),
        'warnings': [str(x) for x in (field(layout_report, 'warnings', []) or [])],
        'rooms': room_rows(layout_report),
    }
    log('layout: ' + report['layout']['message'])
    log('rooms: ' + json.dumps(report['layout']['rooms']))
    if not report['layout']['success']:
        warn('the house was not placed')

    # 4 - validation through collision
    validate_report = unreal.Phase4B1HouseBuilder.validate_house(world, spec)
    checks = dict_of(validate_report, 'checks')
    measurements = dict_of(validate_report, 'measurements')
    failures = [str(x) for x in (field(validate_report, 'failures', []) or [])]
    report['validation'] = {
        'success': flag(validate_report, 'success'),
        'message': str(field(validate_report, 'message', '')),
        'checks': {str(k): bool(v) for k, v in checks.items()},
        'measurements': {str(k): round(float(v), 3) for k, v in measurements.items()},
        'failures': failures,
    }
    log('validation: ' + report['validation']['message'])
    log('validation checks: ' + json.dumps(report['validation']['checks']))
    log('validation measurements: ' + json.dumps(report['validation']['measurements']))
    for failure in failures:
        warn('validation: ' + failure)

    # 5 - save the level
    try:
        level_subsystem.save_current_level()
        log('level saved')
    except Exception as exc:  # noqa: BLE001
        warn('could not save the level: {0}'.format(exc))

    # 6 - world census: only the house may have changed
    labels = []
    landscape_actors = []
    p4b1_actors = []
    for actor in actor_subsystem.get_all_level_actors():
        try:
            label = str(actor.get_actor_label())
        except Exception:  # noqa: BLE001
            label = str(actor.get_name())
        labels.append(label)
        try:
            class_name = actor.get_class().get_name()
        except Exception:  # noqa: BLE001
            class_name = ''
        if 'Landscape' in class_name:
            landscape_actors.append(label)
        if label.startswith('P4B1_'):
            p4b1_actors.append(label)

    kept = [x for x in labels if x.startswith('P4B_Veranda') or x.startswith('P4B_Garage')
            or x.startswith('P4B_Shed') or x.startswith('P4B_ConcreteYard')
            or x.startswith('P4B_Driveway') or x.startswith('P4B_Grill') or x.startswith('P4B_Trees')]
    report['actor_count'] = len(labels)
    report['landscape_actors'] = len(landscape_actors)
    report['p4b1_actor_count'] = len(p4b1_actors)
    report['p4b1_actors'] = sorted(p4b1_actors)
    report['legacy_house_present'] = any(x.startswith('P4B_House') for x in labels)
    report['phase4b_world_kept'] = sorted(kept)
    report['vehicle_present'] = any(x.startswith('Vehicle') for x in labels)
    report['interaction_present'] = any(x.startswith('InteractionTestObject') for x in labels)
    report['player_start_present'] = any(x.startswith('PlayerStart_Home') for x in labels)
    report['pad_from_terrain_m'] = ground_z(world, HOUSE_CENTER[0] - 9.0, HOUSE_CENTER[1])
    report['roof_over_centre_m'] = ground_z(world, HOUSE_CENTER[0], HOUSE_CENTER[1])
    report['floor_in_hall_m'] = ground_z(world, HOUSE_CENTER[0] - 0.72, HOUSE_CENTER[1], PAD_HEIGHT + 1.5)
    log('actors: {0}, P4B1: {1}, landscape: {2}'.format(
        report['actor_count'], report['p4b1_actor_count'], report['landscape_actors']))
    log('legacy house present: {0}, Phase 4B world kept: {1}'.format(
        report['legacy_house_present'], len(report['phase4b_world_kept'])))
    log('traces: pad={0} roof={1} hall_floor={2}'.format(
        report['pad_from_terrain_m'], report['roof_over_centre_m'], report['floor_in_hall_m']))

    rooms = report['layout']['rooms']
    smallest = min([r['area_m2'] for r in rooms]) if rooms else 0.0
    largest = max([r['area_m2'] for r in rooms]) if rooms else 0.0
    hall = [r for r in rooms if r['room'].startswith('Giris')]
    bed_areas = [r['area_m2'] for r in rooms
                 if r['room'].startswith('Oyuncu') or r['room'].startswith('Ebeveyn')]

    checks = {
        'materials_ready': len(materials) >= 24,
        'meshes_created': report['assets']['success'] and len(report['assets']['created']) >= 40,
        'house_placed': report['layout']['success'] and report['p4b1_actor_count'] >= 15,
        'wall_count_realistic': (report['assets']['exterior_wall_panels'] >= 20
                                 and report['assets']['interior_wall_panels'] >= 30),
        'rooms_present': len(rooms) >= 8,
        'room_sizes_believable': smallest >= 2.0 and largest <= 26.0,
        'bedrooms_present': len(bed_areas) == 2 and all(9.0 <= area <= 18.0 for area in bed_areas),
        'hall_corridor_present': len(hall) == 1 and 10.0 <= hall[0]['area_m2'] <= 14.0,
        'interior_area_in_range': 90.0 <= report['layout']['net_interior_m2'] <= 130.0,
        'ceiling_height_ok': all(abs(r['ceiling_height_m'] - 2.70) < 0.01 for r in rooms),
        'exterior_doors': report['layout']['doors'] >= 8,
        'windows_present': report['layout']['windows'] >= 9,
        'furniture_placed': report['layout']['furniture_items'] >= 55,
        'interior_lights': report['layout']['lights'] >= 9,
        'validation_passed': report['validation']['success'],
        'legacy_graybox_removed': not report['legacy_house_present'],
        'phase4b_world_kept': len(kept) >= 5,
        'landscape_untouched': report['landscape_actors'] == 65,
        'vehicle_present': report['vehicle_present'],
        'interaction_present': report['interaction_present'],
        'player_start_present': report['player_start_present'],
        'pad_preserved': (report['pad_from_terrain_m'] is not None
                          and abs(report['pad_from_terrain_m'] - PAD_HEIGHT) < 0.20),
        'roof_measured': (report['roof_over_centre_m'] is not None
                          and report['roof_over_centre_m'] > PAD_HEIGHT + 4.5),
        'hall_floor_measured': (report['floor_in_hall_m'] is not None
                                and abs(report['floor_in_hall_m'] - (PAD_HEIGHT + 0.45)) < 0.10),
    }
    report['checks'] = checks
    report['ok'] = all(checks.values()) and not report['failed']
    report['result'] = 'OK' if report['ok'] else 'CHECK'
    log('checks: ' + json.dumps(checks))
    log('result: ' + report['result'])

out_dir = os.path.join(os.environ.get('TEMP', '.'), 'MyProject_Phase4B1')
try:
    os.makedirs(out_dir)
except Exception:  # noqa: BLE001
    pass
with open(os.path.join(out_dir, 'phase4b1_build.json'), 'w') as handle:
    json.dump(report, handle, indent=2, default=str)
log('report written: ' + os.path.join(out_dir, 'phase4b1_build.json'))
