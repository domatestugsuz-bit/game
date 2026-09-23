# -*- coding: utf-8 -*-
"""Phase 4B-1 diagnostics: trace probes and actor bounds (temporary)."""

import json
import unreal

PAD = 147.492
ORIGIN = unreal.Vector(76000.0, 78580.0, PAD * 100.0)

world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def trace(x0, y0, z0, x1, y1, z1):
    start = unreal.Vector(ORIGIN.x + x0, ORIGIN.y + y0, ORIGIN.z + z0)
    end = unreal.Vector(ORIGIN.x + x1, ORIGIN.y + y1, ORIGIN.z + z1)
    hit = unreal.SystemLibrary.line_trace_single(
        world, start, end, unreal.TraceTypeQuery.ECC_VISIBILITY, False, [],
        unreal.DrawDebugTrace.NONE, True)
    if hit is None:
        return None
    data = hit.to_dict() if hasattr(hit, 'to_dict') else {}
    label = None
    actor = data.get('hit_actor') or data.get('actor')
    if actor is not None:
        try:
            label = actor.get_actor_label()
        except Exception:  # noqa: BLE001
            label = None
    loc = data.get('location') or data.get('impact_point')
    return {'actor': label, 'x': round((loc.x - ORIGIN.x) / 100.0, 3) if loc else None,
            'y': round((loc.y - ORIGIN.y) / 100.0, 3) if loc else None,
            'z': round((loc.z - ORIGIN.z) / 100.0, 3) if loc else None}


probes = {
    'west_outer_y070': (-1200.0, 70.0, 195.0, 1200.0, 70.0, 195.0),
    'west_inner_y105': (-300.0, 105.0, 195.0, -1200.0, 105.0, 195.0),
    'west_inner_y140': (-300.0, 140.0, 195.0, -1200.0, 140.0, 195.0),
    'west_inner_y172': (-300.0, 172.0, 195.0, -1200.0, 172.0, 195.0),
    'west_inner_y310': (-300.0, 310.0, 195.0, -1200.0, 310.0, 195.0),
    'west_outer_y172': (-1200.0, 172.0, 195.0, 1200.0, 172.0, 195.0),
    'west_outer_y105': (-1200.0, 105.0, 195.0, 1200.0, 105.0, 195.0),
    'part_east_y105': (-72.0, 105.0, 145.0, -500.0, 105.0, 145.0),
    'part_west_y105': (-500.0, 105.0, 145.0, 500.0, 105.0, 145.0),
    'floor_hall': (-72.0, 0.0, 150.0, -72.0, 0.0, -100.0),
    'ceiling_hall': (-72.0, 0.0, 100.0, -72.0, 0.0, 2000.0),
    'chimney_y172': (-300.0, 172.0, 145.0, -500.0, 172.0, 145.0),
}
out = {}
for name, values in probes.items():
    out[name] = trace(*values)

leafs = {}
for actor in actors.get_all_level_actors():
    try:
        label = str(actor.get_actor_label())
    except Exception:  # noqa: BLE001
        continue
    if not label.startswith('P4B1_Door_'):
        continue
    origin, extent = actor.get_actor_bounds(True)
    leafs[label] = {
        'loc': [round((origin.x - ORIGIN.x) / 100.0, 2), round((origin.y - ORIGIN.y) / 100.0, 2)],
        'x': [round((origin.x - extent.x - ORIGIN.x) / 100.0, 2), round((origin.x + extent.x - ORIGIN.x) / 100.0, 2)],
        'y': [round((origin.y - extent.y - ORIGIN.y) / 100.0, 2), round((origin.y + extent.y - ORIGIN.y) / 100.0, 2)],
        'yaw': round(actor.get_actor_rotation().yaw if hasattr(actor, 'get_actor_rotation') else 0.0, 1),
    }
out['leaves'] = leafs

unreal.log('P4B1PROBE: ' + json.dumps(out, indent=2))
with open(r'C:\Temp\MyProject_Phase4B1\probe.json', 'w') as handle:
    json.dump(out, handle, indent=2)
