"""Phase 4B collision probe: why do the ground traces not hit the generated property meshes?"""
import json

import unreal

LEVEL = '/Game/Game/Environment/Lvl_Rural'
HOME_DIR = '/Game/Game/Environment/Home'
MESHES = ['SM_P4B_House', 'SM_P4B_Veranda', 'SM_P4B_Garage', 'SM_P4B_Shed',
          'SM_P4B_ConcreteYard', 'SM_P4B_Grill', 'SM_P4B_Driveway']
LABELS = ['Home_House', 'Home_Veranda', 'Home_Garage', 'Home_Shed',
          'Home_ConcreteYard', 'Home_Grill', 'Home_Driveway']

editor_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
world_subsystem = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
editor_subsystem.load_level(LEVEL)
world = world_subsystem.get_editor_world()

out = {'meshes': {}, 'actors': {}, 'traces': {}}
for name in MESHES:
    mesh = unreal.EditorAssetLibrary.load_asset(HOME_DIR + '/' + name)
    if mesh is None:
        out['meshes'][name] = 'missing'
        continue
    info = {}
    for prop in ('complex_collision_trace_flag', 'allow_cpu_access'):
        try:
            info[prop] = str(mesh.get_editor_property(prop))
        except Exception as exc:  # noqa: BLE001
            info[prop] = 'n/a: {0}'.format(exc)
    body = None
    try:
        body = mesh.get_editor_property('body_setup')
    except Exception:
        pass
    if body is not None:
        for prop in ('collision_trace_flag', 'has_any_simple_collision'):
            try:
                info[prop] = str(body.get_editor_property(prop))
            except Exception:
                info[prop] = 'n/a'
    out['meshes'][name] = info

for label in LABELS + ['Vehicle', 'PlayerStart_Home']:
    for actor in actor_subsystem.get_all_level_actors():
        if actor.get_actor_label() != label:
            continue
        entry = {'class': actor.get_class().get_name(),
                 'location': [round(float(c) / 100.0, 2) for c in
                              (actor.get_actor_location().x, actor.get_actor_location().y,
                               actor.get_actor_location().z)]}
        try:
            origin, extent = actor.get_actor_bounds(False)
            entry['bounds_m'] = {'min': [round((float(o) - float(e)) / 100.0, 2) for o, e in
                                         ((origin.x, extent.x), (origin.y, extent.y), (origin.z, extent.z))],
                                 'max': [round((float(o) + float(e)) / 100.0, 2) for o, e in
                                         ((origin.x, extent.x), (origin.y, extent.y), (origin.z, extent.z))]}
        except Exception as exc:  # noqa: BLE001
            entry['bounds_m'] = 'n/a: {0}'.format(exc)
        for component in actor.get_components_by_class(unreal.StaticMeshComponent):
            coll = {}
            try:
                body_instance = component.get_editor_property('body_instance')
                coll['collision_enabled'] = str(body_instance.get_editor_property('collision_enabled'))
                coll['profile'] = str(body_instance.get_editor_property('collision_profile_name'))
            except Exception as exc:  # noqa: BLE001
                coll['error'] = str(exc)
            entry['collision'] = coll
            break
        out['actors'][label] = entry
        break


def trace(x_m, y_m, complex_trace):
    start = unreal.Vector(x_m * 100.0, y_m * 100.0, 60000.0)
    end = unreal.Vector(x_m * 100.0, y_m * 100.0, -60000.0)
    hit = unreal.SystemLibrary.line_trace_single(
        world, start, end, unreal.TraceTypeQuery.ECC_VISIBILITY, complex_trace, [],
        unreal.DrawDebugTrace.NONE, True)
    if hit is None:
        return {'z_m': None, 'actor': None}
    data = hit.to_dict()
    if not data.get('blocking_hit', True):
        return {'z_m': None, 'actor': None, 'keys': sorted(data.keys())}
    location = data.get('location')
    height = round(float(location.z) / 100.0, 2) if location is not None else None
    label = None
    for key in ('actor', 'hit_actor'):
        actor = data.get(key)
        if actor is None:
            continue
        try:
            label = actor.get_actor_label()
        except Exception:
            label = str(actor)
        break
    return {'z_m': height, 'actor': label, 'keys': sorted(data.keys())}


probes = {
    'yard_centre': (752.0, 766.0),
    'veranda_apron': (760.0, 798.0),
    'house_front': (760.0, 780.0),
    'shed_apron': (733.0, 744.0),
    'driveway_join': (721.7, 636.7),
}
for name, (x, y) in probes.items():
    out['traces'][name + ' (simple)'] = trace(x, y, False)
    out['traces'][name + ' (complex)'] = trace(x, y, True)

with open('C:/Users/azize/AppData/Local/Temp/MyProject_Phase4B/collision_probe.json', 'w') as handle:
    json.dump(out, handle, indent=2, default=str)
unreal.log('P4B-PROBE: ' + json.dumps(out, default=str))
