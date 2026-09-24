# -*- coding: utf-8 -*-
"""How far does the landscape actually reach after the Phase 4B expansion?

The seam probe found no trace hit west of x = -1300 m and a bogus -255 m hit at x = -1200 m, while
the expansion report claims a 4032 m world. This census lists every landscape streaming proxy with
its bounds and component count, the landscape actor bounds, and traces with several channels so it
is clear whether the outer strips have geometry at all, geometry without collision, or nothing.
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


def trace(x_m, y_m, channel):
    start = unreal.Vector(x_m * CM, y_m * CM, 400000.0)
    end = unreal.Vector(x_m * CM, y_m * CM, -60000.0)
    hit = unreal.SystemLibrary.line_trace_single(world, start, end, channel, False, [],
                                                 unreal.DrawDebugTrace.NONE, True)
    if hit is None:
        return None
    data = hit.to_dict()
    if not data.get('blocking_hit', True):
        return None
    location = data.get('location')
    return round(float(location.z) / CM, 1) if location else None


proxies = []
landscape_actor = None
for actor in actor_subsystem.get_all_level_actors():
    name = actor.get_class().get_name()
    if name == 'LandscapeStreamingProxy':
        origin, extent = actor.get_actor_bounds(False)
        entry = {'label': actor.get_actor_label(),
                 'components': len(actor.get_components_by_class(unreal.LandscapeComponent))}
        if isinstance(origin, unreal.Vector):
            entry.update(centre_x_m=round(float(origin.x) / CM, 1), centre_y_m=round(float(origin.y) / CM, 1),
                         extent_m=round(float(extent.x) / CM, 1))
        proxies.append(entry)
    elif name == 'Landscape':
        landscape_actor = actor
        origin, extent = actor.get_actor_bounds(False)
        if isinstance(origin, unreal.Vector):
            report['landscape_bounds_m'] = {
                'min': [round((float(origin.x) - float(extent.x)) / CM, 1),
                        round((float(origin.y) - float(extent.y)) / CM, 1)],
                'max': [round((float(origin.x) + float(extent.x)) / CM, 1),
                        round((float(origin.y) + float(extent.y)) / CM, 1)],
            }
        report['landscape_components'] = len(actor.get_components_by_class(unreal.LandscapeComponent))

report['proxy_count'] = len(proxies)
report['proxies_with_components'] = len([entry for entry in proxies if entry['components'] > 0])
report['proxy_component_total'] = sum(entry['components'] for entry in proxies)
x_values = sorted(set(entry.get('centre_x_m', 0.0) for entry in proxies))
report['proxy_centre_x_values'] = x_values[:40]
report['proxy_centre_x_count'] = len(x_values)
report['proxies_sample'] = sorted(proxies, key=lambda entry: (entry.get('centre_x_m', 0.0),
                                                             entry.get('centre_y_m', 0.0)))[:24]

scan = {}
for x_m in (-2010.0, -1900.0, -1500.0, -1300.0, -1200.0, -1100.0, -1000.0, 0.0, 1000.0, 2010.0):
    scan['{0:.0f}'.format(x_m)] = {
        'visibility': trace(x_m, 0.0, unreal.TraceTypeQuery.ECC_VISIBILITY),
        'camera': trace(x_m, 0.0, unreal.TraceTypeQuery.ECC_CAMERA),
    }
report['scan_y0'] = scan

if not os.path.isdir(SAVED_DIR):
    os.makedirs(SAVED_DIR)
out_path = os.path.join(SAVED_DIR, 'phase4b_landscape_census.json')
with open(out_path, 'w') as handle:
    json.dump(report, handle, indent=2, default=str)
unreal.log_warning('P4B-CENSUS: written ' + out_path)
