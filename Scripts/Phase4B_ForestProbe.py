# -*- coding: utf-8 -*-
"""Phase 4B - forest placement API probe (writes one test actor, then removes it).

Answers the questions the placement script depends on:
  * how a HISM component can be added to a plain spawned Actor from Python,
  * what classes and bounds the protected property / road actors have (clearance masks),
  * whether the road routes are splines that can be sampled as a polyline.
"""

import json
import os

import unreal

LEVEL = '/Game/Game/Environment/Lvl_Rural'
SAVED_DIR = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir()),
                         'Phase4B')
PATTERNS = ('P4_Prod', 'P4B_', 'Road_Route_', 'Vehicle', 'PlayerStart_Home', 'InteractionTestObject')

report = {'result': 'OK'}


def names(prefixes, values):
    return sorted(value for value in values if any(prefix in value.lower() for prefix in prefixes))


def safe(function, default='n/a'):
    try:
        return function()
    except Exception as exc:  # noqa: BLE001
        return '{0}: {1}'.format(default, str(exc)[:120])


level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
level_subsystem.load_level(LEVEL)
actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

report['actor_api'] = names(('component', 'instance', 'attach', 'root'), dir(unreal.Actor))
report['hism_api'] = names(('instance', 'static_mesh', 'collision', 'cull', 'shadow', 'nanite'),
                           dir(unreal.HierarchicalInstancedStaticMeshComponent))
report['subsystem_api'] = names(('spawn', 'destroy', 'create'), dir(unreal.EditorActorSubsystem))

# ---------------------------------------------------------------- protected actors
protected = {}
for actor in actor_subsystem.get_all_level_actors():
    label = actor.get_actor_label()
    if label.startswith('P4B_Trees') or not label.startswith(PATTERNS):
        continue
    origin, extent = safe(lambda: actor.get_actor_bounds(False), 'no bounds')
    entry = {'label': label, 'class': actor.get_class().get_name()}
    if isinstance(origin, unreal.Vector):
        entry['bounds_m'] = {
            'min': [round((float(origin.x) - float(extent.x)) / 100.0, 2),
                    round((float(origin.y) - float(extent.y)) / 100.0, 2),
                    round((float(origin.z) - float(extent.z)) / 100.0, 2)],
            'max': [round((float(origin.x) + float(extent.x)) / 100.0, 2),
                    round((float(origin.y) + float(extent.y)) / 100.0, 2),
                    round((float(origin.z) + float(extent.z)) / 100.0, 2)],
        }
    splines = actor.get_components_by_class(unreal.SplineComponent)
    if splines:
        spline = splines[0]
        entry['spline'] = {
            'length_m': safe(lambda: round(float(spline.get_spline_length()) / 100.0, 2), None),
            'samples_m': safe(lambda: [[round(float(point.x) / 100.0, 2), round(float(point.y) / 100.0, 2),
                                        round(float(point.z) / 100.0, 2)]
                                       for point in [spline.get_location_at_distance_along_spline(
                                           index * spline.get_spline_length() / 12.0) for index in range(13)]],
                              None),
        }
    protected[label] = entry
report['protected'] = protected

# ---------------------------------------------------------------- component creation test
test_actor = None
try:
    test_actor = actor_subsystem.spawn_actor_from_class(unreal.Actor, unreal.Vector(0.0, 0.0, 0.0),
                                                       unreal.Rotator(0.0, 0.0, 0.0))
    if test_actor is None:
        report['component_test'] = 'spawn_actor_from_class returned None'
    else:
        test_actor.set_actor_label('P4B_VegProbe_Temp')
        component = None
        for attempt in ('add_component_by_class', 'add_component'):
            method = getattr(test_actor, attempt, None)
            if method is None:
                continue
            try:
                component = method(unreal.HierarchicalInstancedStaticMeshComponent, True,
                                   unreal.Transform(), True)
                report['component_test'] = attempt + ' ok'
                break
            except Exception as exc:  # noqa: BLE001
                report['component_test_' + attempt] = str(exc)[:200]
        if component is None:
            component = unreal.new_object(unreal.HierarchicalInstancedStaticMeshComponent, test_actor)
            report['component_test'] = 'new_object fallback'
        if component is not None:
            mesh = unreal.EditorAssetLibrary.load_asset(
                '/Game/Game/Environment/Vegetation/Trees/Pine/SM_Veg_Pine_Mature_C')
            component.set_editor_property('static_mesh', mesh)
            try:
                component.set_editor_property('mobility', unreal.ComponentMobility.STATIC)
            except Exception as exc:  # noqa: BLE001
                report['mobility'] = str(exc)[:120]
            report['component_class'] = component.get_class().get_name()
            report['component_in_actor'] = [entry.get_name() for entry in
                                            test_actor.get_components_by_class(
                                                unreal.HierarchicalInstancedStaticMeshComponent)]
            try:
                index = component.add_instance(unreal.Transform(unreal.Vector(0.0, 0.0, 0.0),
                                                               unreal.Rotator(0.0, 0.0, 0.0),
                                                               unreal.Vector(1.0, 1.0, 1.0)),
                                              True)
                report['add_instance'] = int(index) if index is not None else 'None'
                report['instance_count'] = int(component.get_instance_count())
            except Exception as exc:  # noqa: BLE001
                report['add_instance_error'] = str(exc)[:200]
            for name in ('nanite_override', 'cast_shadow', 'cast_dynamic_shadow', 'cull_distance'):
                try:
                    report[name] = str(component.get_editor_property(name))
                except Exception as exc:  # noqa: BLE001
                    report[name] = str(exc)[:100]
finally:
    if test_actor is not None:
        actor_subsystem.destroy_actor(test_actor)

if not os.path.isdir(SAVED_DIR):
    os.makedirs(SAVED_DIR)
out_path = os.path.join(SAVED_DIR, 'phase4b_forest_probe.json')
with open(out_path, 'w') as handle:
    json.dump(report, handle, indent=2, default=str)
unreal.log('P4B-FORESTPROBE: written ' + out_path)
