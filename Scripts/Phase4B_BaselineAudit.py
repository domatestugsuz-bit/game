# -*- coding: utf-8 -*-
"""Phase 4B - baseline audit of the delivered rural world.

READ ONLY: this script inspects the level, the landscape, World Partition, the
existing vegetation and the rendering configuration and writes a JSON report to
Saved/Phase4B/. It never modifies, saves or deletes anything in the level.
"""

import json
import os

import unreal

LEVEL = '/Game/Game/Environment/Lvl_Rural'
PROJECT_DIR = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
SAVED_DIR = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir()), 'Phase4B')
CONFIG_DIR = os.path.join(PROJECT_DIR, 'Config')

report = {'steps': [], 'result': 'FAILED', 'read_only': True}
warnings = []


def log(message):
    unreal.log('P4B-BASE: ' + str(message))
    report['steps'].append(str(message))


def warn(message):
    unreal.log_warning('P4B-BASE: ' + str(message))
    warnings.append(str(message))


def number(value, default=None):
    try:
        return float(value)
    except Exception:  # noqa: BLE001
        return default


def labels_with_class():
    out = []
    subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for actor in subsystem.get_all_level_actors():
        try:
            out.append([actor.get_actor_label(), actor.get_class().get_name()])
        except Exception:  # noqa: BLE001
            continue
    return out


def class_counts(rows):
    counts = {}
    for _label, klass in rows:
        counts[klass] = counts.get(klass, 0) + 1
    return counts


def asset_inventory(root='/Game/Game'):
    """Counts every asset under root by class (AssetRegistry, read only)."""
    result = {'root': root, 'total': 0, 'by_class': {}, 'by_folder': {}, 'meshes': {}, 'textures': []}
    try:
        registry = unreal.AssetRegistryHelpers.get_asset_registry()
        assets = registry.get_assets_by_path(root, recursive=True)
    except Exception as exc:  # noqa: BLE001
        warn('asset registry query failed: {0}'.format(exc))
        return result
    for asset in assets:
        result['total'] += 1
        try:
            klass = str(asset.asset_class_path.asset_name)
        except Exception:  # noqa: BLE001
            klass = str(asset.asset_class)
        result['by_class'][klass] = result['by_class'].get(klass, 0) + 1
        folder = str(asset.package_name).rsplit('/', 1)[0]
        result['by_folder'][folder] = result['by_folder'].get(folder, 0) + 1
    return result


def static_mesh_stats(paths):
    """Triangle / Nanite / LOD summary for the assets we care about."""
    out = []
    for path in paths:
        entry = {'path': path}
        try:
            mesh = unreal.EditorAssetLibrary.load_asset(path)
        except Exception:  # noqa: BLE001
            mesh = None
        if mesh is None or not isinstance(mesh, unreal.StaticMesh):
            entry['error'] = 'not a static mesh / missing'
            out.append(entry)
            continue
        try:
            entry['lod_count'] = mesh.get_num_lods()
        except Exception:  # noqa: BLE001
            entry['lod_count'] = 'n/a'
        try:
            entry['triangles_lod0'] = mesh.get_num_triangles(0)
        except Exception:  # noqa: BLE001
            entry['triangles_lod0'] = 'n/a'
        try:
            settings = mesh.get_editor_property('nanite_settings')
            entry['nanite_enabled'] = bool(settings.get_editor_property('enabled'))
        except Exception:  # noqa: BLE001
            entry['nanite_enabled'] = 'n/a'
        out.append(entry)
    return out


def landscape_report():
    info = {'actors': [], 'streaming_proxies': 0, 'components': 0, 'proxy_components': {},
            'nanite_components': 0, 'bounds': None, 'grid': {}, 'labels': []}
    subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    min_v = None
    max_v = None
    for actor in subsystem.get_all_level_actors():
        try:
            klass = actor.get_class().get_name()
        except Exception:  # noqa: BLE001
            continue
        if klass not in ('Landscape', 'LandscapeStreamingProxy'):
            continue
        info['labels'].append('{0} [{1}]'.format(actor.get_actor_label(), klass))
        if klass == 'LandscapeStreamingProxy':
            info['streaming_proxies'] += 1
        # the landscape actor itself owns no components when the data lives in
        # streaming proxies, so the world extent is accumulated from actor bounds
        try:
            origin, extent = actor.get_actor_bounds(only_colliding_components=False)
            if extent.x > 1.0 or extent.y > 1.0:
                low = (origin.x - extent.x, origin.y - extent.y)
                high = (origin.x + extent.x, origin.y + extent.y)
                min_v = low if min_v is None else (min(min_v[0], low[0]), min(min_v[1], low[1]))
                max_v = high if max_v is None else (max(max_v[0], high[0]), max(max_v[1], high[1]))
        except Exception as exc:  # noqa: BLE001
            warn('component bounds query failed on {0}: {1}'.format(klass, exc))
        try:
            components = actor.get_components_by_class(unreal.LandscapeComponent)
            info['proxy_components'][actor.get_actor_label()] = len(components)
            info['components'] += len(components)
        except Exception as exc:  # noqa: BLE001
            warn('component query failed on {0}: {1}'.format(klass, exc))
        try:
            info['nanite_components'] += len(actor.get_components_by_class(unreal.LandscapeNaniteComponent))
        except Exception:  # noqa: BLE001
            pass
        if klass == 'Landscape':
            info['label'] = actor.get_actor_label()
            try:
                _origin, _extent = actor.get_actor_bounds(only_colliding_components=False)
                info['bounds'] = {'origin': [_origin.x, _origin.y, _origin.z],
                                  'extent': [_extent.x, _extent.y, _extent.z]}
            except Exception as exc:  # noqa: BLE001
                warn('landscape bounds failed: {0}'.format(exc))
            for field in ('component_size_quads', 'num_subsections', 'subsection_size_quads',
                          'landscape_material', 'landscape_guid', 'nanite_enabled',
                          'max_lod_level', 'lod0_screen_size', 'lod0_distribution_setting'):
                try:
                    info['grid'][field] = str(actor.get_editor_property(field))
                except Exception:  # noqa: BLE001
                    info['grid'][field] = 'n/a'
    if min_v is not None and max_v is not None:
        info['world_extent_m'] = {'min': [round(min_v[0] / 100.0, 1), round(min_v[1] / 100.0, 1)],
                                 'max': [round(max_v[0] / 100.0, 1), round(max_v[1] / 100.0, 1)]}
        info['size_m'] = [round((max_v[0] - min_v[0]) / 100.0, 1),
                          round((max_v[1] - min_v[1]) / 100.0, 1)]
    return info


def foliage_report():
    """Vegetation: instanced foliage actors, the Phase 4B tree actors and the
    instance counts of their mesh components."""
    info = {'actors': [], 'total_instances': 0, 'by_actor': {}, 'by_mesh': {}}
    subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for actor in subsystem.get_all_level_actors():
        try:
            klass = actor.get_class().get_name()
            label = actor.get_actor_label()
        except Exception:  # noqa: BLE001
            continue
        if 'Foliage' not in klass and not label.startswith(('P4B_Trees', 'P4B_Shrub', 'P4B_Rock')):
            continue
        entry = {'label': label, 'class': klass, 'components': [], 'instances': 0}
        try:
            components = actor.get_components_by_class(unreal.InstancedStaticMeshComponent)
        except Exception:  # noqa: BLE001
            components = []
        for component in components:
            try:
                count = int(component.get_instance_count())
            except Exception:  # noqa: BLE001
                count = 'n/a'
            try:
                mesh = str(component.get_editor_property('static_mesh').get_path_name())
            except Exception:  # noqa: BLE001
                mesh = 'n/a'
            entry['components'].append({'mesh': mesh, 'instances': count})
            if isinstance(count, int):
                entry['instances'] += count
                info['total_instances'] += count
                info['by_mesh'][mesh] = info['by_mesh'].get(mesh, 0) + count
        info['by_actor'][label] = entry['instances']
        info['actors'].append(entry)
    return info


def lighting_report():
    """Lights, sky atmosphere, fog and post process volumes that drive the look."""
    info = {'actors': []}
    wanted = ('DirectionalLight', 'SkyLight', 'SkyAtmosphere', 'ExponentialHeightFog',
              'VolumetricCloud', 'SphereReflectionCapture', 'PlayerStart', 'PostProcessVolume')
    subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for actor in subsystem.get_all_level_actors():
        try:
            klass = actor.get_class().get_name()
            label = actor.get_actor_label()
        except Exception:  # noqa: BLE001
            continue
        if klass not in wanted:
            continue
        entry = {'label': label, 'class': klass}
        try:
            origin, _extent = actor.get_actor_bounds(only_colliding_components=False)
            entry['location'] = [round(origin.x, 1), round(origin.y, 1), round(origin.z, 1)]
        except Exception:  # noqa: BLE001
            entry['location'] = 'n/a'
        if klass == 'DirectionalLight':
            try:
                component = actor.get_components_by_class(unreal.DirectionalLightComponent)[0]
                entry['intensity_lux'] = round(float(component.get_editor_property('intensity')), 1)
                entry['mobility'] = str(component.get_editor_property('mobility'))
                entry['cast_shadows'] = bool(component.get_editor_property('cast_shadows'))
                entry['atmosphere_sun_light'] = bool(component.get_editor_property('atmosphere_sun_light'))
            except Exception as exc:  # noqa: BLE001
                entry['error'] = str(exc)
        if klass == 'SkyLight':
            try:
                component = actor.get_components_by_class(unreal.SkyLightComponent)[0]
                entry['intensity'] = round(float(component.get_editor_property('intensity')), 3)
                entry['real_time_capture'] = bool(component.get_editor_property('real_time_capture'))
                entry['mobility'] = str(component.get_editor_property('mobility'))
            except Exception as exc:  # noqa: BLE001
                entry['error'] = str(exc)
        if klass == 'ExponentialHeightFog':
            try:
                component = actor.get_components_by_class(unreal.ExponentialHeightFogComponent)[0]
                entry['volumetric_fog'] = bool(component.get_editor_property('volumetric_fog'))
                entry['fog_density'] = round(float(component.get_editor_property('fog_density')), 4)
            except Exception as exc:  # noqa: BLE001
                entry['error'] = str(exc)
        info['actors'].append(entry)
    return info


def console_variables(names):
    """Best-effort CVar read back (the Python surface differs between builds)."""
    out = {}
    for name in names:
        value = None
        for getter, caster in (('get_console_variable_float_value', float),
                               ('get_console_variable_int_value', int),
                               ('get_console_variable_string_value', str)):
            try:
                raw = getattr(unreal.SystemLibrary, getter)(name)
                value = caster(raw)
                break
            except Exception:  # noqa: BLE001
                continue
        out[name] = value if value is not None else 'n/a'
    return out


def ini_report():
    """The project / renderer ini sections this audit must record."""
    saved_config = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir()),
                                'Config', 'WindowsEditor')
    candidates = [os.path.join(CONFIG_DIR, 'DefaultEngine.ini'),
                  os.path.join(CONFIG_DIR, 'DefaultScalability.ini'),
                  os.path.join(saved_config, 'EditorPerProjectUserSettings.ini'),
                  os.path.join(saved_config, 'Scalability.ini')]
    out = {'present': [p for p in candidates if os.path.isfile(p)],
           'missing': [p for p in candidates if not os.path.isfile(p)],
           'renderer_lines': [], 'scalability_lines': []}
    for index, path in enumerate(candidates):
        if not os.path.isfile(path):
            continue
        key = 'renderer_lines' if index == 0 else 'scalability_lines'
        try:
            with open(path, 'r') as handle:
                for line in handle:
                    stripped = line.strip()
                    if any(token in stripped for token in ('r.', 'sg.', 'D3D12', 'Substrate', 'RayTracing')):
                        out[key].append(stripped)
        except Exception as exc:  # noqa: BLE001
            warn('could not read {0}: {1}'.format(path, exc))
    return out


def meshes_under(folder):
    out = []
    try:
        registry = unreal.AssetRegistryHelpers.get_asset_registry()
        for asset in registry.get_assets_by_path(folder, recursive=True):
            try:
                klass = str(asset.asset_class_path.asset_name)
            except Exception:  # noqa: BLE001
                klass = str(asset.asset_class)
            if klass == 'StaticMesh':
                out.append(str(asset.package_name))
    except Exception as exc:  # noqa: BLE001
        warn('mesh query failed for {0}: {1}'.format(folder, exc))
    return out


def ground_z(world, x_m, y_m):
    start = unreal.Vector(x_m * 100.0, y_m * 100.0, 60000.0)
    end = unreal.Vector(x_m * 100.0, y_m * 100.0, -60000.0)
    hit = unreal.SystemLibrary.line_trace_single(world, start, end, unreal.TraceTypeQuery.ECC_VISIBILITY,
                                                 True, [], unreal.DrawDebugTrace.NONE, True)
    if hit is None:
        return None
    try:
        location = hit.to_dict().get('location')
        return round(float(location.z) / 100.0, 2)
    except Exception:  # noqa: BLE001
        return None


# ------------------------------------------------------------------ run audit
CVARS = ['r.DynamicGlobalIlluminationMethod', 'r.ReflectionMethod', 'r.Lumen.HardwareRayTracing',
         'r.Lumen.ScreenProbeGather.DownsampleFactor', 'r.Lumen.TraceMeshSDFs',
         'r.Shadow.Virtual.Enable', 'r.Shadow.Virtual.MaxPhysicalPages', 'r.Nanite',
         'r.Nanite.ProjectEnabled', 'r.Substrate', 'r.RayTracing', 'r.VolumetricFog',
         'r.SkyAtmosphere', 'r.DefaultFeature.AutoExposure', 'r.DefaultFeature.AutoExposure.Method',
         'r.DefaultFeature.AutoExposure.ExtendDefaultLuminanceRange', 'r.DefaultFeature.Bloom',
         'r.DefaultFeature.AmbientOcclusion', 'r.AntiAliasingMethod', 'r.VirtualTextures',
         'r.Streaming.PoolSize', 'r.ViewDistanceScale', 'foliage.DensityScale',
         'foliage.LODDistanceScale', 'grass.CullDistanceScale', 'r.GenerateMeshDistanceFields',
         'r.AllowStaticLighting']

report['engine'] = {}
for key, getter in (('engine_version', 'get_engine_version'), ('project_version', 'get_project_version')):
    try:
        report['engine'][key] = str(getattr(unreal.SystemLibrary, getter)())
    except Exception:  # noqa: BLE001
        report['engine'][key] = 'n/a'

editor_subsystem = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
level_subsystem.load_level(LEVEL)
world = editor_subsystem.get_editor_world()
settings = world.get_world_settings()
partition = settings.get_editor_property('world_partition')
report['level'] = {'path': world.get_path_name(), 'is_partitioned': partition is not None,
                   'actor_count': len(list(unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
                                           .get_all_level_actors()))}
report['world_partition'] = {'class': 'none' if partition is None else partition.get_class().get_name(),
                             'settings': {}}
if partition is not None:
    for field in ('grid_size', 'loading_range', 'enable_streaming', 'enable_server_streaming',
                  'server_loading_range', 'world_partition_class', 'editor_hash', 'runtime_hash'):
        try:
            report['world_partition']['settings'][field] = str(partition.get_editor_property(field))
        except Exception:  # noqa: BLE001
            report['world_partition']['settings'][field] = 'n/a'

rows = labels_with_class()
report['actors'] = {'total': len(rows), 'by_class': class_counts(rows), 'labels': rows}
report['landscape'] = landscape_report()
report['foliage'] = foliage_report()
report['lighting'] = lighting_report()

report['assets'] = asset_inventory('/Game/Game')
house_meshes = meshes_under('/Game/Game/Environment/House')
report['house_mesh_count'] = len(house_meshes)
report['house_meshes'] = static_mesh_stats(house_meshes)
world_meshes = meshes_under('/Game/Game/Environment/World')
report['world_meshes'] = world_meshes
report['world_mesh_stats'] = static_mesh_stats(world_meshes)
report['house_vegetation_meshes'] = meshes_under('/Game/Game/Environment/House/Vegetation')
report['console'] = console_variables(CVARS)
report['config_files'] = ini_report()

SAMPLE_POINTS = {'home_pad': (750.0, 750.0), 'house': (760.0, 783.0), 'veranda': (772.0, 792.0),
                 'hill_summit': (890.0, 895.0), 'road_start': (750.0, 665.0), 'road_mid': (222.5, 215.0),
                 'road_end': (892.5, -975.0), 'world_sw': (-1000.0, -1000.0), 'world_ne': (1000.0, 1000.0),
                 'world_nw': (-1000.0, 1000.0), 'world_se': (1000.0, -1000.0),
                 'forest_belt': (450.0, 450.0), 'open_west': (-700.0, 0.0)}
report['terrain_traces_m'] = {name: ground_z(world, x, y) for name, (x, y) in SAMPLE_POINTS.items()}

saved_dir = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir())
report['previous_performance'] = {}
previous_path = os.path.join(saved_dir, 'Phase4', 'phase4_validate.json')
if os.path.isfile(previous_path):
    try:
        with open(previous_path, 'r') as handle:
            previous = json.load(handle)
        report['previous_performance'] = {'result': previous.get('result'),
                                          'tests': len(previous.get('tests', [])),
                                          'failed': len(previous.get('failed', [])),
                                          'performance': previous.get('performance')}
    except Exception as exc:  # noqa: BLE001
        warn('could not read the Phase 4 validation report: {0}'.format(exc))

land = report['landscape']
size_m = land.get('size_m') or [0.0, 0.0]
checks = {
    'level_loaded': str(report['level']['path']).startswith('/Game/Game/Environment/Lvl_Rural'),
    'world_partition_enabled': bool(report['level']['is_partitioned']),
    'landscape_present': bool(land.get('label')),
    'landscape_has_components': int(land.get('components') or 0) >= 200,
    'landscape_is_2016_m': abs(float(size_m[0]) - 2016.0) < 6.0,
    'house_present': any(label.startswith('P4_Prod') for label, _k in rows),
    'garage_present': any(label.startswith('P4B_Garage') for label, _k in rows),
    'vehicle_present': any(label.startswith('Vehicle') for label, _k in rows),
    'player_start_present': any(label.startswith('PlayerStart_Home') for label, _k in rows),
    'interaction_present': any(label.startswith('InteractionTestObject') for label, _k in rows),
    'road_route_present': any(label.startswith('Road_Route_') for label, _k in rows),
    'home_pad_elevated': float(report['terrain_traces_m'].get('home_pad') or 0.0) > 140.0,
}
report['checks'] = checks
report['warnings'] = warnings
report['ok'] = all(checks.values())
report['result'] = 'OK' if report['ok'] else 'CHECK'

if not os.path.isdir(SAVED_DIR):
    os.makedirs(SAVED_DIR)
out_path = os.path.join(SAVED_DIR, 'phase4b_baseline.json')
with open(out_path, 'w') as handle:
    json.dump(report, handle, indent=2, default=str)
log('baseline result: ' + report['result'])
log('baseline written: ' + out_path)
