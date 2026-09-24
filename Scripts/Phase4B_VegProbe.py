# -*- coding: utf-8 -*-
"""Phase 4B - vegetation / material probe (read only).

The forest upgrade needs three things that are not guessable from the outside:
  1. what the existing Phase 4B pine assets (SM_P4B_PineTrunk_*/Canopy_*) look like as
     assets (collision, Nanite, material slots) and how they are placed in the level,
  2. which material parameters the existing masters expose, so the new vegetation and
     landscape materials reuse the project's conventions instead of new ones,
  3. which editor APIs this engine build actually exposes to Python (material graph
     editing, static mesh collision / Nanite, foliage types).

Everything is read only: no asset is modified, nothing is saved.
"""

import json
import os

import unreal

SAVED_DIR = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir()),
                         'Phase4B')
LEVEL = '/Game/Game/Environment/Lvl_Rural'
HOME_DIR = '/Game/Game/Environment/Home'
WORLD_DIR = '/Game/Game/Environment/World'
MESHES = ['SM_P4B_PineTrunk_A', 'SM_P4B_PineCanopy_A', 'SM_P4B_House']
MATERIALS = [HOME_DIR + '/M_RuralSurface', HOME_DIR + '/MI_Needles', HOME_DIR + '/MI_Bark',
             WORLD_DIR + '/M_LandscapeBlockout', WORLD_DIR + '/MI_LandscapeBlockout']

report = {'result': 'OK'}


def safe(function, default=None):
    try:
        return function()
    except Exception as exc:  # noqa: BLE001
        return default if default is not None else 'n/a: {0}'.format(str(exc)[:160])


def names(prefixes, values):
    return sorted(value for value in values
                  if any(prefix.lower() in value.lower() for prefix in prefixes))


# ---------------------------------------------------------------- 1. existing assets
report['meshes'] = {}
for name in MESHES:
    mesh = unreal.EditorAssetLibrary.load_asset(HOME_DIR + '/' + name)
    if mesh is None:
        report['meshes'][name] = 'missing'
        continue
    entry = {}
    entry['triangles'] = safe(lambda: mesh.get_num_triangles())
    entry['material_slots'] = safe(lambda: [str(slot.get_editor_property('material_interface'))
                                            for slot in mesh.get_editor_property('static_materials')])
    nanite = safe(lambda: mesh.get_editor_property('nanite_settings'))
    entry['nanite'] = {field: safe(lambda: str(nanite.get_editor_property(field)))
                       for field in ('enabled', 'preserve_area', 'position_precision')}
    entry['complex_collision'] = safe(lambda: str(mesh.get_editor_property('complex_collision_trace_flag')))
    entry['body_setup'] = safe(lambda: str(mesh.get_editor_property('body_setup')
                                           .get_editor_property('collision_trace_flag')))
    entry['has_simple_collision'] = safe(lambda: str(mesh.get_editor_property('body_setup')
                                                     .get_editor_property('has_any_simple_collision')))
    entry['bounds_m'] = safe(lambda: [[round(float(value) / 100.0, 2) for value in
                                       (mesh.get_bounding_box().min.x, mesh.get_bounding_box().min.y,
                                        mesh.get_bounding_box().min.z)],
                                      [round(float(value) / 100.0, 2) for value in
                                       (mesh.get_bounding_box().max.x, mesh.get_bounding_box().max.y,
                                        mesh.get_bounding_box().max.z)]])
    report['meshes'][name] = entry

# ---------------------------------------------------------------- 2. level placement
level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
level_subsystem.load_level(LEVEL)
actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors = list(actor_subsystem.get_all_level_actors())

report['placement'] = {'tree_actors': [], 'total_tree_instances': 0, 'landscape': {}, 'lights': {}}
for actor in actors:
    label = actor.get_actor_label()
    class_name = actor.get_class().get_name()
    if label.startswith('P4B_Trees'):
        entry = {'label': label, 'class': class_name, 'components': []}
        for component in actor.get_components_by_class(unreal.InstancedStaticMeshComponent):
            mesh = safe(lambda: component.get_editor_property('static_mesh'))
            instances = safe(lambda: component.get_instance_count(), 0)
            entry['components'].append({
                'class': component.get_class().get_name(),
                'mesh': str(mesh) if mesh else None,
                'instances': instances,
                'mobility': safe(lambda: str(component.get_editor_property('mobility'))),
                'cast_shadow': safe(lambda: str(component.get_editor_property('cast_shadow'))),
                'nanite_override': safe(lambda: str(component.get_editor_property('nanite_override'))),
                'foliage_override': safe(lambda: str(component.get_editor_property('foliage_override'))),
            })
            if isinstance(instances, int):
                report['placement']['total_tree_instances'] += instances
        report['placement']['tree_actors'].append(entry)
    elif class_name in ('Landscape', 'LandscapeStreamingProxy'):
        report['placement']['landscape'].setdefault('material', safe(lambda: str(
            actor.get_editor_property('landscape_material'))))
        report['placement']['landscape']['proxy_count'] = report['placement']['landscape'].get('proxy_count', 0) + 1
    elif class_name in ('DirectionalLight', 'SkyLight', 'ExponentialHeightFog', 'SkyAtmosphere',
                        'VolumetricCloud'):
        entry = report['placement']['lights'].setdefault(class_name, {})
        entry['label'] = label
        location = actor.get_actor_location()
        rotation = actor.get_actor_rotation()
        entry['location_m'] = [round(float(value) / 100.0, 2) for value in (location.x, location.y, location.z)]
        entry['rotation'] = [round(float(value), 2) for value in (rotation.roll, rotation.pitch, rotation.yaw)]
        if class_name == 'DirectionalLight':
            components = actor.get_components_by_class(unreal.DirectionalLightComponent)
            if components:
                component = components[0]
                for field in ('intensity', 'dynamic_shadow_distance', 'atmosphere_sun_light',
                              'affects_world', 'use_temperature'):
                    entry[field] = safe(lambda: str(component.get_editor_property(field)))
                entry['cast_shadows'] = safe(lambda: str(component.get_editor_property('cast_shadows')))
                entry['cascaded_shadow_maps'] = safe(lambda: str(
                    component.get_editor_property('cascaded_shadow_maps')))
        if class_name == 'SkyLight':
            components = actor.get_components_by_class(unreal.SkyLightComponent)
            if components:
                entry['intensity'] = safe(lambda: str(components[0].get_editor_property('intensity')))
                entry['real_time_capture'] = safe(lambda: str(
                    components[0].get_editor_property('real_time_capture')))



# ---------------------------------------------------------------- 3. material parameters
report['materials'] = {}
for path in MATERIALS + [report['placement']['landscape'].get('material')]:
    if not path:
        continue
    path = str(path).split('.')[0]
    asset = unreal.EditorAssetLibrary.load_asset(path)
    if asset is None:
        report['materials'][path] = 'missing'
        continue
    library = unreal.MaterialEditingLibrary
    entry = {
        'class': asset.get_class().get_name(),
        'blend_mode': safe(lambda: str(asset.get_editor_property('blend_mode'))),
        'two_sided': safe(lambda: str(asset.get_editor_property('two_sided'))),
        'shading_model': safe(lambda: str(asset.get_editor_property('shading_model'))),
        'opacity_mask_clip': safe(lambda: asset.get_editor_property('opacity_mask_clip_value')),
        'scalar': safe(lambda: sorted(library.get_scalar_parameter_names(asset))),
        'vector': safe(lambda: sorted(library.get_vector_parameter_names(asset))),
        'texture': safe(lambda: sorted(library.get_texture_parameter_names(asset))),
        'static_switch': safe(lambda: sorted(library.get_static_switch_parameter_names(asset))),
    }
    if asset.get_class().get_name() == 'MaterialInstanceConstant':
        entry['parent'] = safe(lambda: str(asset.get_editor_property('parent')))
    report['materials'][path] = entry

# ---------------------------------------------------------------- 4. available APIs
report['api'] = {
    'material_editing_library': names(['expression', 'connect', 'parameter', 'layout', 'recompile'],
                                      dir(unreal.MaterialEditingLibrary)),
    'static_mesh_editor_subsystem': names(['collision', 'nanite', 'simple', 'convex', 'lod'],
                                          dir(unreal.StaticMeshEditorSubsystem)),
    'editor_static_mesh_library': names(['collision', 'convex', 'simple'], dir(unreal.EditorStaticMeshLibrary)),
    'material_property': sorted(value for value in dir(unreal.MaterialProperty) if not value.startswith('_')),
    'material_sampler_type': sorted(value for value in dir(unreal.MaterialSamplerType) if not value.startswith('_')),
    'blend_mode': sorted(value for value in dir(unreal.BlendMode) if not value.startswith('_')),
    'texture_compression': sorted(value for value in dir(unreal.TextureCompressionSettings)
                                  if not value.startswith('_')),
    'texture_group': sorted(value for value in dir(unreal.TextureGroup) if not value.startswith('_')),
    'material_class_members': names(['two_sided', 'blend', 'opacity', 'shading', 'translucen', 'usage'],
                                    dir(unreal.Material)),
    'texture_class_members': names(['srgb', 'compression', 'group', 'flip', 'never_stream', 'virtual'],
                                   dir(unreal.Texture2D)),
    'foliage_classes': names(['foliage'], dir(unreal)),
    'instanced_classes': names(['instancedstaticmesh'], dir(unreal)),
    'material_factory': names(['material'], dir(unreal.MaterialFactoryNew)),
}

if not os.path.isdir(SAVED_DIR):
    os.makedirs(SAVED_DIR)
out_path = os.path.join(SAVED_DIR, 'phase4b_veg_probe.json')
with open(out_path, 'w') as handle:
    json.dump(report, handle, indent=2, default=str)
unreal.log('P4B-VEGPROBE: written ' + out_path)
unreal.log('P4B-VEGPROBE: ' + json.dumps(report, default=str))
