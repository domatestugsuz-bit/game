# -*- coding: utf-8 -*-
"""Phase 4 - read-only probe of the Unreal project before the Blender house import.

Collects (and writes a JSON report):
  * the Lvl_Rural actor inventory in the home area (labels, classes, world bounds)
  * the Phase 4B / 4B-1 property and house actors the imported house must respect
  * the terrain height through collision (C++ Phase4B1HouseBuilder.ground_height_m)
  * the /Game/Game/Environment/Home and /House asset inventory with mesh bounds

Run - the project path contains a space, so the whole argument list must be passed as
ONE string. A PowerShell array argument splits the path at the space and Unreal then
starts with no project at all, silently:

  UnrealEditor-Cmd.exe "<Project>.uproject" -ExecutePythonScript="<this file>" ^
      -unattended -nosplash -nullrhi -stdout -NoSourceControl -NoLogTimes

Nothing is modified: no asset is created, no level is saved.
"""

import json
import os
from datetime import datetime

import unreal

LEVEL = '/Game/Game/Environment/Lvl_Rural'
HOME_DIR = '/Game/Game/Environment/Home'
HOUSE_DIR = '/Game/Game/Environment/House'
PROBE_DIR = 'C:/Temp/MyProject_Phase4/run'

# world positions (meters) that matter for the new house
PROBE_POINTS = [
    ('house_center', 760.0, 785.8),
    ('house_front_south', 760.0, 779.0),
    ('house_rear_north', 760.0, 792.0),
    ('veranda_deck', 760.0, 794.0),
    ('player_start', 758.0, 773.0),
    ('yard_center', 750.0, 764.0),
    ('driveway', 733.0, 762.0),
    ('garage_apron', 748.0, 754.0),
    ('garden_east', 776.0, 790.0),
    ('garden_west', 744.0, 790.0),
    ('north_field', 760.0, 806.0),
    ('south_field', 760.0, 764.0),
]

KEY_MESHES = [
    HOME_DIR + '/SM_P4B_House',
    HOME_DIR + '/SM_P4B_Veranda',
    HOME_DIR + '/SM_P4B_Garage',
    HOME_DIR + '/SM_P4B_Shed',
    HOME_DIR + '/SM_P4B_ConcreteYard',
    HOME_DIR + '/SM_P4B_Driveway',
    HOME_DIR + '/SM_P4B_Grill',
]

report = {
    'phase': 'Phase 4 house import probe',
    'timestamp': datetime.now().isoformat(timespec='seconds'),
    'level': LEVEL,
    'failed': [],
    'notes': [],
    'actors': [],
    'actor_classes': {},
    'traces': {},
    'assets': {},
    'meshes': {},
}


def note(message):
    report['notes'].append(str(message))
    unreal.log('P4PROBE: {0}'.format(message))
    try:
        with open(PROBE_DIR + '/probe_progress.txt', 'a') as handle:
            handle.write(str(message) + '\n')
    except Exception:  # noqa: BLE001
        pass


def fail(message):
    report['failed'].append(str(message))
    note('FAILED: ' + str(message))


def m(vector):
    """Centimetres -> metres, rounded for readable reports."""
    return [round(vector.x / 100.0, 3), round(vector.y / 100.0, 3), round(vector.z / 100.0, 3)]



def actor_bounds(actor):
    try:
        origin, extent = actor.get_actor_bounds(False)
        return {'bounds_origin_m': m(origin), 'bounds_extent_m': m(extent)}
    except Exception as exc:  # noqa: BLE001
        return {'bounds_error': str(exc)[:120]}


def mesh_facts(path):
    if not unreal.EditorAssetLibrary.does_asset_exist(path):
        return {'error': 'missing'}
    mesh = unreal.EditorAssetLibrary.load_asset(path)
    if mesh is None:
        return {'error': 'not loadable'}
    facts = {}
    try:
        box = mesh.get_bounding_box()
        facts['bounds_m'] = {'min': m(box.min), 'max': m(box.max)}
        facts['size_m'] = [round((box.max.x - box.min.x) / 100.0, 3),
                           round((box.max.y - box.min.y) / 100.0, 3),
                           round((box.max.z - box.min.z) / 100.0, 3)]
    except Exception as exc:  # noqa: BLE001
        facts['bounds_m'] = 'ERR ' + str(exc)[:120]
    for key, getter in (
            ('nanite', lambda: bool(mesh.get_editor_property('nanite_settings').enabled)),
            ('lods', lambda: len(mesh.get_editor_property('render_data').lod_resources)),
            ('materials', lambda: [slot.get_editor_property('material_interface').get_name()
                                   for slot in mesh.get_editor_property('static_materials')]),
            ('trace_flag', lambda: str(mesh.get_editor_property('body_setup')
                                       .get_editor_property('collision_trace_flag'))),
    ):
        try:
            facts[key] = getter()
        except Exception as exc:  # noqa: BLE001
            facts[key] = 'ERR ' + str(exc)[:90]
    try:
        facts['vertex_count'] = unreal.EditorStaticMeshLibrary.get_number_vertices(mesh)
    except Exception as exc:  # noqa: BLE001
        facts['vertex_count'] = 'ERR ' + str(exc)[:90]
    return facts


# ------------------------------------------------------------------ 1. load the level
world = unreal.EditorLoadingAndSavingUtils.load_map(LEVEL)
editor_subsystem = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
if world is None:
    world = editor_subsystem.get_editor_world()
note('world = {0}'.format(world.get_name() if world else 'None'))
if world is None:
    fail('no world after load_map')

actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors = list(actor_subsystem.get_all_level_actors()) if world else []
report['actor_count'] = len(actors)
histogram = {}
for actor in actors:
    cls = actor.get_class().get_name()
    histogram[cls] = histogram.get(cls, 0) + 1
report['actor_classes'] = dict(sorted(histogram.items()))
note('level actor count = {0}'.format(len(actors)))
note('actor classes: ' + json.dumps(report['actor_classes']))

# ------------------------------------------------------------------ 2. property actors
for actor in actors:
    label = actor.get_actor_label()
    if not (label.startswith('P4B') or label.startswith('PlayerStart')
            or 'Vehicle' in label or 'Home' in label):
        continue
    entry = {
        'label': label,
        'class': actor.get_class().get_name(),
        'location_m': m(actor.get_actor_location()),
    }
    entry.update(actor_bounds(actor))
    report['actors'].append(entry)
report['actors'].sort(key=lambda item: item['label'])
note('property related actors: ' + str(len(report['actors'])))
for entry in report['actors'][:30]:
    note('  {0}  {1}  at {2} {3}'.format(entry['label'], entry['class'],
                                         entry['location_m'], entry.get('bounds_extent_m', '')))


# ------------------------------------------------------------------ 3. terrain heights
builder = getattr(unreal, 'Phase4B1HouseBuilder', None)
report['builder_available'] = builder is not None
if builder is None:
    fail('unreal.Phase4B1HouseBuilder is not exposed to Python')
else:
    for name, x_m, y_m in PROBE_POINTS:
        try:
            height, hit = builder.ground_height_m(world, float(x_m), float(y_m))
            entry = {'height_m': round(float(height), 3), 'hit': bool(hit)}
        except Exception as exc:  # noqa: BLE001
            entry = {'error': str(exc)[:140]}
        report['traces'][name] = dict(entry, x_m=x_m, y_m=y_m)
    note('terrain heights: ' + json.dumps(report['traces']))

# ------------------------------------------------------------------ 4. asset inventory
registry = unreal.AssetRegistryHelpers.get_asset_registry()
try:
    registry.scan_paths_synchronous([HOME_DIR, HOUSE_DIR], True)
except Exception as exc:  # noqa: BLE001
    fail('asset registry scan: {0}'.format(exc))
for root in (HOME_DIR, HOUSE_DIR):
    assets = list(registry.get_assets_by_path(root, recursive=True))
    folders = {}
    for asset in assets:
        folder = str(asset.package_name).rsplit('/', 1)[0]
        folders[folder] = folders.get(folder, 0) + 1
    report['assets'][root] = {'count': len(assets),
                              'folders': dict(sorted(folders.items())),
                              'names': sorted(str(asset.asset_name) for asset in assets)}
    note('assets under {0}: {1} {2}'.format(root, len(assets),
                                            json.dumps(dict(sorted(folders.items())))))

for path in KEY_MESHES:
    report['meshes'][path.rsplit('/', 1)[-1]] = mesh_facts(path)
for name, facts in sorted(report['meshes'].items()):
    note('mesh {0}: {1}'.format(name, json.dumps(facts)))

note('world partition api: ' + json.dumps([a for a in dir(unreal) if 'WorldPartition' in a]))

# ------------------------------------------------------------------ 5. write the report
report['result'] = 'FAILED' if report['failed'] else 'OK'
saved_dir = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir())
out_dir = os.path.join(saved_dir, 'Phase4')
os.makedirs(out_dir, exist_ok=True)
out_path = os.path.join(out_dir, 'phase4_probe.json')
try:
    with open(out_path, 'w') as handle:
        handle.write(json.dumps(report, indent=2))
    note('report written: ' + out_path)
except Exception as exc:  # noqa: BLE001
    fail('could not write report {0}: {1}'.format(out_path, exc))
unreal.log('P4PROBE: result = {0}'.format(report['result']))


