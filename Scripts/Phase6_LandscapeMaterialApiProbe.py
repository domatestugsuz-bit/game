# Probe the landscape material API so the assignment can follow the editor path (the current
# direct property write crashes a -game build with
# "SetParentEditorOnly() may only be used to initialize (not change) the parent").
import unreal

level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
level_subsystem.load_level('/Game/Game/Environment/Lvl_Rural')

actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
landscape = None
proxy = None
for actor in actors:
    name = actor.get_class().get_name()
    if name == 'Landscape' and landscape is None:
        landscape = actor
    if name == 'LandscapeStreamingProxy' and proxy is None:
        proxy = actor

for label, actor in (('Landscape', landscape), ('StreamingProxy', proxy)):
    if actor is None:
        print('P7PROBE {0}: missing'.format(label))
        continue
    names = [item for item in dir(actor) if 'material' in item.lower()]
    print('P7PROBE {0} material api: {1}'.format(label, sorted(names)))
    try:
        current = actor.get_editor_property('landscape_material')
        print('P7PROBE {0} current material: {1}'.format(label, current.get_path_name() if current else None))
    except Exception as exc:
        print('P7PROBE {0} material read failed: {1}'.format(label, exc))
    for function_name in ('update_material_instances', 'update_all_component_material_instances',
                          'update_material_instances_and_parameters', 'recreate_components'):
        function = getattr(actor, function_name, None)
        print('P7PROBE {0} has {1}: {2}'.format(label, function_name, function is not None))

components = []
if landscape is not None:
    try:
        components = list(landscape.get_components_by_class(unreal.LandscapeComponent))
    except Exception as exc:
        print('P7PROBE component list failed: {0}'.format(exc))
print('P7PROBE landscape component count: {0}'.format(len(components)))
if components:
    names = [item for item in dir(components[0]) if 'material' in item.lower()]
    print('P7PROBE component material api: {0}'.format(sorted(names)))

print('P7PROBE_DONE')
