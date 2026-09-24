# -*- coding: utf-8 -*-
"""Phase 6 - repair the EXT_Shed_Door (and the rest of the interactables batch) import.

The Blender source mesh is healthy (24 verts / 26 polys, no zero area faces), but the UE
import reports "LogStaticMesh: Error: Bad MeshDescription on .../EXT_Shed_Door" and the door
disappears in game: the FBX static mesh import data had remove_degenerates=True, which strips
the thin (6 cm) door leaf down to nothing.

This script re-imports the batch exactly like Phase 4 did, with remove_degenerates=False, and
reports the mesh bounds before/after so the repair is measurable.

Run in EDITOR mode (headless):
  UnrealEditor-Cmd.exe "<Project>.uproject" -ExecutePythonScript="<this file>"
                       -unattended -nosplash -nullrhi -stdout -NoSourceControl
"""

import json
import os
from datetime import datetime

import unreal

FBX = 'C:/Temp/blender_house/export/House_Interactables.fbx'
DESTINATION = '/Game/Game/Environment/House/Interactables'
TARGET = DESTINATION + '/EXT_Shed_Door'
REPORT_REL = 'Phase6/'
REPORT_NAME = 'phase6_shed_door.json'

report = {'phase': 'Phase 6 - shed door import repair', 'timestamp': datetime.now().isoformat(timespec='seconds'),
          'notes': [], 'result': 'FAILED'}


def log(message):
    print('PHASE6-DOOR: ' + str(message))


def enum_value(enum_type_name, candidates):
    enum = getattr(unreal, enum_type_name, None)
    if enum is None:
        return None
    for candidate in candidates:
        value = getattr(enum, candidate, None)
        if value is not None:
            return value
    return None


def mesh_facts(mesh):
    if mesh is None:
        return {'loaded': False}
    facts = {'loaded': True}
    try:
        box = mesh.get_bounding_box()
        facts['bounds_min_cm'] = [round(box.min.x, 3), round(box.min.y, 3), round(box.min.z, 3)]
        facts['bounds_max_cm'] = [round(box.max.x, 3), round(box.max.y, 3), round(box.max.z, 3)]
        facts['size_cm'] = [round(box.max.x - box.min.x, 3), round(box.max.y - box.min.y, 3),
                            round(box.max.z - box.min.z, 3)]
    except Exception as exc:
        facts['bounds_error'] = str(exc)
    for name in ('get_number_vertices', 'get_num_triangles', 'get_number_triangles'):
        function = getattr(unreal.EditorStaticMeshLibrary, name, None)
        if function is None:
            continue
        try:
            facts[name] = function(mesh)
        except Exception:
            try:
                facts[name] = function(mesh, 0)
            except Exception as exc:
                facts[name] = 'err:{0}'.format(exc)
    return facts


def main():
    out_dir = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir() + REPORT_REL)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    if not os.path.isfile(FBX):
        report['notes'].append('FBX missing: ' + FBX)
    else:
        before = unreal.EditorAssetLibrary.load_asset(TARGET)
        report['before'] = mesh_facts(before)
        log('before: {0}'.format(report['before']))

        options = unreal.FbxImportUI()
        options.import_materials = False
        options.import_textures = False
        options.import_as_skeletal = False
        options.automated_import_should_detect_type = False
        static_mesh_enum = enum_value('FBXImportType', ('FBXIT_STATIC_MESH', 'STATIC_MESH'))
        if static_mesh_enum is not None:
            options.mesh_type_to_import = static_mesh_enum

        data = unreal.FbxStaticMeshImportData()
        data.combine_meshes = False
        # the actual fix: a 6 cm door leaf has slivers that the degenerate pass removed,
        # leaving an empty mesh description.
        data.remove_degenerates = False
        try:
            data.auto_compute_normals = True
        except Exception:
            pass
        collision = enum_value('FbxCollisionType', ('FBCT_USE_MESH', 'USE_MESH'))
        if collision is not None:
            try:
                data.collision_type = collision
            except Exception as exc:
                report['notes'].append('collision_type not set: {0}'.format(exc))
        options.static_mesh_import_data = data

        task = unreal.AssetImportTask()
        task.filename = FBX
        task.destination_path = DESTINATION
        task.destination_name = 'House_Interactables'
        task.automated = True
        task.replace_existing = True
        task.save = True
        task.options = options
        try:
            unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
            paths = [str(path) for path in task.get_editor_property('imported_object_paths')]
            report['imported_paths'] = paths
            log('imported {0} asset(s)'.format(len(paths)))
        except Exception as exc:
            report['notes'].append('import failed: {0}'.format(exc))

        mesh = unreal.EditorAssetLibrary.load_asset(TARGET)
        report['after'] = mesh_facts(mesh)
        log('after: {0}'.format(report['after']))

        size = report['after'].get('size_cm') if report['after'].get('loaded') else None
        repaired = bool(size) and size[2] > 180.0 and size[0] > 90.0
        report['repaired'] = repaired
        if not repaired:
            report['notes'].append('the door mesh still has no usable geometry: {0}'.format(size))

        try:
            report['saved'] = bool(unreal.EditorAssetLibrary.save_loaded_asset(mesh, only_if_is_dirty=False)) \
                if mesh else False
        except Exception as exc:
            report['saved'] = False
            report['notes'].append('save failed: {0}'.format(exc))

    report['result'] = 'OK' if report.get('repaired') and not report['notes'] else 'FAILED'
    path = os.path.join(out_dir, REPORT_NAME)
    with open(path, 'w') as handle:
        json.dump(report, handle, indent=2)
    log('repaired={0} notes={1}'.format(report.get('repaired'), report['notes']))
    print('PHASE6_DOOR_DONE ' + path)


if __name__ == '__main__':
    main()
