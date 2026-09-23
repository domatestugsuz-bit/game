"""Phase 4B focused probe: are the placed property actors registered and collidable?"""
import json

import unreal

LEVEL = '/Game/Game/Environment/Lvl_Rural'
LABELS = ['P4B_House', 'P4B_Veranda', 'P4B_Garage', 'P4B_Shed', 'P4B_ConcreteYard', 'P4B_Driveway']

level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
world_subsystem = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
level_subsystem.load_level(LEVEL)
world = world_subsystem.get_editor_world()

out = {'actors': {}, 'traces': {}}

for actor in actor_subsystem.get_all_level_actors():
    label = actor.get_actor_label()
    if label not in LABELS:
        continue
    entry = {}
    components = actor.get_components_by_class(unreal.StaticMeshComponent)
    entry['component_count'] = len(components)
    if components:
        component = components[0]
        for name in ('is_registered', 'is_visible'):
            try:
                entry[name] = str(getattr(component, name)())
            except Exception as exc:  # noqa: BLE001
                entry[name] = 'n/a: {0}'.format(exc)
        try:
            entry['mobility'] = str(component.get_editor_property('mobility'))
        except Exception as exc:  # noqa: BLE001
            entry['mobility'] = str(exc)
        try:
            entry['mesh'] = str(component.get_editor_property('static_mesh').get_name())
        except Exception as exc:  # noqa: BLE001
            entry['mesh'] = str(exc)
        try:
            body = component.get_editor_property('body_instance')
            entry['collision_enabled'] = str(body.get_editor_property('collision_enabled'))
        except Exception as exc:  # noqa: BLE001
            entry['collision_enabled'] = str(exc)
    out['actors'][label] = entry


def trace(x_m, y_m, start_z_m, complex_trace):
    start = unreal.Vector(x_m * 100.0, y_m * 100.0, start_z_m * 100.0)
    end = unreal.Vector(x_m * 100.0, y_m * 100.0, (start_z_m - 30.0) * 100.0)
    hit = unreal.SystemLibrary.line_trace_single(
        world, start, end, unreal.TraceTypeQuery.ECC_VISIBILITY, complex_trace, [],
        unreal.DrawDebugTrace.NONE, True)
    if hit is None:
        return {'z_m': None}
    data = hit.to_dict()
    if not data.get('blocking_hit', True):
        return {'z_m': None, 'blocking': False}
    component = data.get('hit_component')
    actor = data.get('hit_actor')
    return {
        'z_m': round(float(data['location'].z) / 100.0, 3),
        'component': str(component.get_name()) if component is not None else None,
        'actor': str(actor.get_actor_label()) if actor is not None else None,
    }


probes = {
    'yard_centre': (752.0, 766.0),
    'house_centre': (760.0, 786.0),
    'veranda_centre': (760.0, 793.0),
    'garage_centre': (750.0, 746.0),
    'shed_centre': (729.0, 744.0),
    'control_open_ground': (800.0, 700.0),
}
for name, (x, y) in probes.items():
    out['traces'][name + '|simple'] = trace(x, y, 160.0, False)
    out['traces'][name + '|complex'] = trace(x, y, 160.0, True)

# Try per-triangle physics (complex as simple) on the placed structures.
MESHES = ['SM_P4B_House', 'SM_P4B_Veranda', 'SM_P4B_Garage', 'SM_P4B_Shed',
          'SM_P4B_ConcreteYard', 'SM_P4B_Grill']
flipped = {}
for name in MESHES:
    mesh = unreal.EditorAssetLibrary.load_asset('/Game/Game/Environment/Home/' + name)
    if mesh is None:
        continue
    try:
        body = mesh.get_editor_property('body_setup')
        body.set_editor_property('collision_trace_flag', unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
        body.invalidate_physics_data()
        body.create_physics_meshes()
        flipped[name] = 'ok'
    except Exception as exc:  # noqa: BLE001
        flipped[name] = str(exc)
out['flipped'] = flipped
out['traces_after_flip'] = {}
for name, (x, y) in probes.items():
    out['traces_after_flip'][name] = trace(x, y, 160.0, False)

with open('C:/Users/azize/AppData/Local/Temp/MyProject_Phase4B/collision_probe2.json', 'w') as handle:
    json.dump(out, handle, indent=2, default=str)
unreal.log('P4B-PROBE2: ' + json.dumps(out, default=str))
