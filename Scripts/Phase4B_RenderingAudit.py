# -*- coding: utf-8 -*-
"""Phase 4B - rendering / scalability audit (read only).

Verifies the renderer configuration Phase 4B relies on: Lumen on the software RT path,
Virtual Shadow Maps enabled, hardware ray tracing off by default, and the four quality
profiles (LOW / MEDIUM / HIGH / ULTRA) coming from Config/DefaultScalability.ini.
"""

import json
import os

import unreal

SAVED_DIR = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir()), 'Phase4B')
CONFIG_DIR = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()), 'Config')

report = {'steps': [], 'result': 'FAILED', 'failed': []}
warnings = []

CVARS = ['r.DynamicGlobalIlluminationMethod', 'r.ReflectionMethod', 'r.Lumen.HardwareRayTracing',
         'r.Lumen.DiffuseIndirect.Allow', 'r.Lumen.ScreenProbeGather.DownsampleFactor',
         'r.Lumen.TraceMeshSDFs.Allow', 'r.Shadow.Virtual.Enable', 'r.Shadow.Virtual.MaxPhysicalPages',
         'r.Nanite', 'r.Nanite.ProjectEnabled', 'r.Substrate', 'r.RayTracing',
         'r.RayTracing.RayTracingProxies.ProjectEnabled', 'r.VolumetricFog',
         'r.VolumetricFog.GridPixelSize', 'r.SkyAtmosphere', 'r.GenerateMeshDistanceFields',
         'r.AllowStaticLighting', 'r.AntiAliasingMethod', 'r.Streaming.PoolSize', 'r.Streaming.MipBias',
         'foliage.DensityScale', 'grass.DensityScale', 'foliage.LODDistanceScale',
         'grass.CullDistanceScale', 'r.ViewDistanceScale', 'sg.ShadowQuality',
         'sg.GlobalIlluminationQuality', 'sg.ReflectionQuality', 'sg.FoliageQuality',
         'sg.EffectsQuality', 'sg.TextureQuality', 'sg.ViewDistanceQuality']


def log(message):
    unreal.log('P4B-REND: ' + str(message))
    report['steps'].append(str(message))


def warn(message):
    unreal.log_warning('P4B-REND: ' + str(message))
    warnings.append(str(message))


def console_value(name):
    for getter, caster in (('get_console_variable_float_value', float),
                           ('get_console_variable_int_value', int),
                           ('get_console_variable_string_value', str)):
        try:
            return caster(getattr(unreal.SystemLibrary, getter)(name))
        except Exception:  # noqa: BLE001
            continue
    return None


def ini_sections(path):
    """Every [section] name plus the number of CVar lines below it."""
    sections = {}
    current = None
    try:
        with open(path, 'r') as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped or stripped.startswith(';'):
                    continue
                if stripped.startswith('[') and stripped.endswith(']'):
                    current = stripped[1:-1]
                    sections[current] = []
                elif current is not None and '=' in stripped:
                    sections[current].append(stripped)
    except Exception as exc:  # noqa: BLE001
        warn('could not read {0}: {1}'.format(path, exc))
    return sections


scalability_path = os.path.join(CONFIG_DIR, 'DefaultScalability.ini')
engine_path = os.path.join(CONFIG_DIR, 'DefaultEngine.ini')
scalability_sections = ini_sections(scalability_path)
engine_sections = ini_sections(engine_path)

report['files'] = {'scalability_ini': scalability_path, 'scalability_exists': os.path.isfile(scalability_path),
                   'engine_ini': engine_path, 'engine_exists': os.path.isfile(engine_path)}
report['scalability_sections'] = {name: len(lines) for name, lines in scalability_sections.items()}
report['renderer_ini_lines'] = engine_sections.get('/Script/Engine.RendererSettings', [])
report['cvars'] = {name: console_value(name) for name in CVARS}
report['warnings'] = warnings
log('cvars: {0}'.format(json.dumps(report['cvars'], default=str)))

cvars = report['cvars']
PROFILE_GROUPS = ('FoliageQuality', 'ShadowQuality', 'GlobalIlluminationQuality', 'ReflectionQuality',
                  'EffectsQuality', 'TextureQuality', 'ViewDistanceQuality')

checks = {
    'lumen_dynamic_gi': cvars.get('r.DynamicGlobalIlluminationMethod') == 1.0,
    'lumen_software_rt_default': cvars.get('r.Lumen.HardwareRayTracing') == 0.0,
    'hardware_ray_tracing_off': cvars.get('r.RayTracing') == 0.0,
    'ray_tracing_proxies_off': cvars.get('r.RayTracing.RayTracingProxies.ProjectEnabled') == 0.0,
    'virtual_shadow_maps_on': cvars.get('r.Shadow.Virtual.Enable') == 1.0,
    'nanite_on': cvars.get('r.Nanite') == 1.0 and cvars.get('r.Nanite.ProjectEnabled') == 1.0,
    'volumetric_fog_on': cvars.get('r.VolumetricFog') == 1.0,
    'sky_atmosphere_on': cvars.get('r.SkyAtmosphere') == 1.0,
    'static_lighting_off': cvars.get('r.AllowStaticLighting') == 0.0,
    'mesh_distance_fields_on': cvars.get('r.GenerateMeshDistanceFields') == 1.0,
    'scalability_ini_present': report['files']['scalability_exists'],
    'four_quality_levels': all('{0}@{1}'.format(group, level) in scalability_sections
                               for group in PROFILE_GROUPS for level in (0, 1, 2, 3)),
}
report['checks'] = checks
report['ok'] = all(checks.values())
report['result'] = 'OK' if report['ok'] else 'CHECK'
log('checks: {0}'.format(json.dumps(checks)))
log('result: {0}'.format(report['result']))

if not os.path.isdir(SAVED_DIR):
    os.makedirs(SAVED_DIR)
out_path = os.path.join(SAVED_DIR, 'phase4b_rendering.json')
with open(out_path, 'w') as handle:
    json.dump(report, handle, indent=2, default=str)
log('report written: {0}'.format(out_path))
