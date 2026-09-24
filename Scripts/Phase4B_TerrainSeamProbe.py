# -*- coding: utf-8 -*-
"""Why does a band of terrain around x = -1330 m have no trace hit?

The forest passes reported ~3000 candidate positions where a vertical trace found no ground at
all, and every sample sits in a narrow band of x. A band like that means either missing landscape
collision or a hole in the terrain, and both would also affect the player, so it is measured here
with a scan line plus a component census instead of being guessed at.
"""

import json
import os

import unreal

LEVEL = '/Game/Game/Environment/Lvl_Rural'
SAVED_DIR = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir()),
                         'Phase4B')
CM = 100.0

level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
level_subsystem.load_level(LEVEL)
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

report = {'result': 'OK'}


def trace(x_m, y_m):
    start = unreal.Vector(x_m * CM, y_m * CM, 400000.0)
    end = unreal.Vector(x_m * CM, y_m * CM, -60000.0)
    hit = unreal.SystemLibrary.line_trace_single(world, start, end, unreal.TraceTypeQuery.ECC_VISIBILITY,
                                                 False, [], unreal.DrawDebugTrace.NONE, True)
    if hit is None:
        return {'z_m': None, 'actor': None}
    data = hit.to_dict()
    if not data.get('blocking_hit', True):
        return {'z_m': None, 'actor': None, 'reason': 'no blocking hit'}
    location = data.get('location')
    actor = data.get('actor')
    label = None
    if actor is not None:
        try:
            label = actor.get_actor_label()
        except Exception:  # noqa: BLE001
            label = str(actor)
    return {'z_m': round(float(location.z) / CM, 2) if location else None, 'actor': label}


# scan line across the suspicious band, plus the reference points that did work
scan = {}
for x_m in (-1900.0, -1700.0, -1500.0, -1400.0, -1360.0, -1340.0, -1330.0, -1320.0, -1300.0,
            -1200.0, -1100.0, -1000.0, 0.0, 1000.0, 1900.0):
    scan['{0:.0f}'.format(x_m)] = {'y0': trace(x_m, 0.0), 'y300': trace(x_m, 300.0)}
report['scan'] = scan

# component / proxy census: names and world bounds of the streaming proxies on the west side
proxies = []
landscape_components = 0
for actor in actor_subsystem.get_all_level_actors():
    name = actor.get_class().get_name()
    if name == 'LandscapeStreamingProxy':
        origin, extent = actor.get_actor_bounds(False)
        if isinstance(origin, unreal.Vector) and float(origin.x) / CM < -1000.0:
            proxies.append({
                'label': actor.get_actor_label(),
                'min_x_m': round((float(origin.x) - float(extent.x)) / CM, 1),
                'max_x_m': round((float(origin.x) + float(extent.x)) / CM, 1),
                'min_y_m': round((float(origin.y) - float(extent.y)) / CM, 1),
                'max_y_m': round((float(origin.y) + float(extent.y)) / CM, 1),
            })
    elif name == 'Landscape':
        report['landscape_label'] = actor.get_actor_label()
        landscape_components = len(actor.get_components_by_class(unreal.LandscapeComponent))
report['west_proxies'] = sorted(proxies, key=lambda entry: entry['min_x_m'])
report['landscape_components_on_actor'] = landscape_components

if not os.path.isdir(SAVED_DIR):
    os.makedirs(SAVED_DIR)
out_path = os.path.join(SAVED_DIR, 'phase4b_terrain_seam_probe.json')
with open(out_path, 'w') as handle:
    json.dump(report, handle, indent=2, default=str)
unreal.log_warning('P4B-SEAM: written ' + out_path)
