# -*- coding: utf-8 -*-
"""Phase 3A - create the gameplay vertical-slice assets through Unreal Editor Python.

Run in EDITOR mode (headless):
  UnrealEditor-Cmd.exe "<Project>.uproject" -ExecutePythonScript="<this file>"
                       -unattended -nosplash -nullrhi -stdout -NoSourceControl

Requires the C++ module to be compiled: it subclasses AMyProjectPlayerCharacter,
AInteractionTestActor, UInteractionComponent, UInteractionPromptWidget and
UInteractionConfig. Idempotent: existing assets are reported and left alone.
Never touches template assets (FirstPerson/, Input/, Characters/, LevelPrototyping/).
"""

import json
import os
from datetime import datetime

import unreal

PROJECT = '/Game/Game'

PATHS = {
    'core': PROJECT + '/Core',
    'data': PROJECT + '/Data',
    'ui': PROJECT + '/UI',
    'input': PROJECT + '/Input',
    'player': PROJECT + '/Characters/Player',
    'interaction': PROJECT + '/Interaction',
    'environment': PROJECT + '/Environment',
}

NATIVE_CLASSES = {
    'player_character': '/Script/MyProject.MyProjectPlayerCharacter',
    'interaction_component': '/Script/MyProject.InteractionComponent',
    'prompt_widget': '/Script/MyProject.InteractionPromptWidget',
    'interaction_config': '/Script/MyProject.InteractionConfig',
    'interaction_test_actor': '/Script/MyProject.InteractionTestActor',
}

TEMPLATE_ASSETS = {
    'move_action': '/Game/Input/Actions/IA_Move.IA_Move',
    'look_action': '/Game/Input/Actions/IA_Look.IA_Look',
    'jump_action': '/Game/Input/Actions/IA_Jump.IA_Jump',
    'template_player_controller': '/Game/FirstPerson/Blueprints/BP_FirstPersonPlayerController.BP_FirstPersonPlayerController_C',
}

report = {
    'phase': 'Phase 3A - asset creation',
    'timestamp': datetime.now().isoformat(timespec='seconds'),
    'created': [],
    'existing': [],
    'failed': [],
    'configured': [],
    'notes': [],
}


def log(message):
    unreal.log('PHASE3A-ASSETS: ' + str(message))


def warn(message):
    unreal.log_warning('PHASE3A-ASSETS: ' + str(message))
    report['notes'].append(str(message))


def fail(message):
    unreal.log_error('PHASE3A-ASSETS: ' + str(message))
    report['failed'].append(str(message))


def asset_tools():
    return unreal.AssetToolsHelpers.get_asset_tools()


def ensure_folder(path):
    if not unreal.EditorAssetLibrary.does_directory_exist(path):
        unreal.EditorAssetLibrary.make_directory(path)
    return path


def load_native_class(key):
    cls = unreal.load_class(None, NATIVE_CLASSES[key])
    if cls is None:
        fail('native class not found: {0} ({1}) - was the C++ module compiled?'.format(key, NATIVE_CLASSES[key]))
    return cls


def load_template_asset(key):
    """Loads a template asset or template class ("..._C" paths are classes)."""
    path = TEMPLATE_ASSETS[key]
    if path.endswith('_C'):
        loaded = unreal.load_class(None, path)
    else:
        loaded = unreal.EditorAssetLibrary.load_asset(path)
    if loaded is None:
        warn('template asset not found: {0}'.format(path))
    return loaded


def create_asset(asset_path, asset_class, factory, unique=True):
    """Creates an asset unless it already exists (idempotent)."""
    name = asset_path.split('/')[-1]
    folder = asset_path.rsplit('/', 1)[0]
    if unreal.EditorAssetLibrary.does_asset_exist(asset_path):
        report['existing'].append(asset_path)
        log('already exists, left untouched: ' + asset_path)
        return unreal.EditorAssetLibrary.load_asset(asset_path)

    ensure_folder(folder)
    try:
        created = asset_tools().create_asset(name, folder, asset_class, factory)
    except Exception as exc:
        fail('create_asset raised for {0}: {1}'.format(asset_path, exc))
        return None
    if created is None:
        fail('could not create asset: ' + asset_path)
        return None
    report['created'].append(asset_path)
    log('created: ' + asset_path)
    return created


def get_default_object_for(asset):
    """CDO of a Blueprint asset's generated class (after compiling it)."""
    try:
        unreal.BlueprintEditorLibrary.compile_blueprint(asset)
    except Exception as exc:
        warn('compile_blueprint({0}) failed: {1}'.format(asset.get_name(), exc))
    generated = asset.generated_class()
    if generated is None:
        fail('generated_class() is None for ' + asset.get_name())
        return None
    return unreal.get_default_object(generated)


def apply_defaults(target, properties, label):
    """Sets class-default properties, reporting each one (never silently)."""
    for prop, value in properties.items():
        if value is None:
            warn('{0}: {1} skipped (source value missing)'.format(label, prop))
            continue
        try:
            target.set_editor_property(prop, value)
            report['configured'].append('{0}.{1}'.format(label, prop))
        except Exception as exc:
            warn('{0}.{1} failed: {2}'.format(label, prop, exc))


def create_input_assets():
    """IA_Interact (E) + IMC_Game. Template input assets stay untouched."""
    action_class = unreal.InputAction
    ia_interact = create_asset(PATHS['input'] + '/IA_Interact', action_class, unreal.InputAction_Factory())
    if ia_interact:
        apply_defaults(ia_interact, {
            'value_type': unreal.InputActionValueType.BOOLEAN,
            'trigger_when_paused': False,
        }, 'IA_Interact')

    imc = create_asset(PATHS['input'] + '/IMC_Game', unreal.InputMappingContext, unreal.InputMappingContext_Factory())
    if imc and ia_interact:
        try:
            key = unreal.Key()
            key.set_editor_property('key_name', 'E')
            imc.map_key(ia_interact, key)
            report['configured'].append('IMC_Game: E -> IA_Interact')
            log('IMC_Game: mapped E to IA_Interact')
        except Exception as exc:
            warn('IMC_Game.map_key(E) failed: {0}'.format(exc))
    return ia_interact, imc


def create_prompt_widget():
    """WBP_InteractionPrompt : UInteractionPromptWidget (+ a TextBlock when possible)."""
    base_class = load_native_class('prompt_widget')
    if base_class is None:
        return None

    factory = unreal.WidgetBlueprintFactory()
    try:
        factory.set_editor_property('parent_class', base_class)
    except Exception as exc:
        warn('WidgetBlueprintFactory.parent_class failed: {0}'.format(exc))

    wbp = create_asset(PATHS['ui'] + '/WBP_InteractionPrompt', unreal.WidgetBlueprint, factory)
    if wbp is None:
        return None

    try:
        tree = wbp.get_editor_property('widget_tree')
        root = tree.get_editor_property('root_widget') if tree else None
        if root is None:
            warn('WBP_InteractionPrompt: empty widget tree - add a TextBlock named "PromptText" manually')
            return wbp

        text = unreal.new_object(unreal.TextBlock, tree)
        text.set_editor_property('text', unreal.Text('Etkilesim'))
        try:
            text.set_font_size(22)
        except Exception:
            pass
        root.add_child(text)
        report['configured'].append('WBP_InteractionPrompt: TextBlock added to root')
        log('WBP_InteractionPrompt: TextBlock added')
    except Exception as exc:
        warn('WBP_InteractionPrompt widget tree edit failed: {0}'.format(exc))
    return wbp


def create_data_asset():
    """DA_InteractionConfig - the data-driven tuning asset for the interaction."""
    config_class = load_native_class('interaction_config')
    if config_class is None:
        return None

    factory = unreal.DataAssetFactory()
    try:
        factory.set_editor_property('data_asset_class', config_class)
    except Exception as exc:
        warn('DataAssetFactory.data_asset_class failed: {0}'.format(exc))

    data_asset = create_asset(PATHS['data'] + '/DA_InteractionConfig', unreal.DataAsset, factory)
    if data_asset is None:
        return None

    apply_defaults(data_asset, {
        'trace_distance': 250.0,
        'trace_radius': 12.0,
        'trace_interval': 0.05,
        'prompt_format': unreal.Text('[E] {0}'),
        'trace_channel': unreal.CollisionChannel.ECC_VISIBILITY,
        'use_sphere_trace': True,
    }, 'DA_InteractionConfig')
    return data_asset


def create_player_blueprint(imc, ia_interact, prompt_widget, data_asset):
    """BP_PlayerCharacter : AMyProjectPlayerCharacter (first person only)."""
    player_class = load_native_class('player_character')
    if player_class is None:
        return None

    factory = unreal.BlueprintFactory()
    factory.set_editor_property('parent_class', player_class)
    bp = create_asset(PATHS['player'] + '/BP_PlayerCharacter', unreal.Blueprint, factory)
    if bp is None:
        return bp

    # The prompt widget class is referenced by the config data asset.
    if data_asset and prompt_widget:
        try:
            prompt_class = unreal.BlueprintEditorLibrary.generated_class(prompt_widget)
            data_asset.set_editor_property('prompt_widget_class', prompt_class)
            report['configured'].append('DA_InteractionConfig.prompt_widget_class')
        except Exception as exc:
            warn('DA_InteractionConfig.prompt_widget_class failed: {0}'.format(exc))

    cdo = get_default_object_for(bp)
    if cdo is None:
        return bp

    apply_defaults(cdo, {
        'default_mapping_context': imc,
        'move_action': load_template_asset('move_action'),
        'look_action': load_template_asset('look_action'),
        'jump_action': load_template_asset('jump_action'),
        'interact_action': ia_interact,
        'eye_height': 64.0,
    }, 'BP_PlayerCharacter')

    try:
        component = cdo.get_editor_property('interaction_component')
        if component and data_asset:
            component.set_editor_property('config', data_asset)
            report['configured'].append('BP_PlayerCharacter.InteractionComponent.config')
    except Exception as exc:
        warn('BP_PlayerCharacter interaction component config failed: {0}'.format(exc))

    return bp


def create_game_mode_blueprint(player_bp):
    """BP_GameMode : template game mode, with the new pawn class (template stays intact)."""
    parent_class = unreal.load_class(None, '/Game/FirstPerson/Blueprints/BP_FirstPersonGameMode.BP_FirstPersonGameMode_C')
    if parent_class is None:
        warn('template game mode class not found, falling back to GameModeBase')
        parent_class = unreal.GameModeBase

    factory = unreal.BlueprintFactory()
    factory.set_editor_property('parent_class', parent_class)
    bp = create_asset(PATHS['core'] + '/BP_GameMode', unreal.Blueprint, factory)
    if bp is None:
        return bp

    cdo = get_default_object_for(bp)
    if cdo is None:
        return bp

    pawn_class = unreal.BlueprintEditorLibrary.generated_class(player_bp) if player_bp else None
    apply_defaults(cdo, {
        'default_pawn_class': pawn_class,
        'player_controller_class': load_template_asset('template_player_controller'),
    }, 'BP_GameMode')
    return bp


def create_test_object_blueprint():
    """BP_InteractionTestObject : AInteractionTestActor (implements the interface)."""
    actor_class = load_native_class('interaction_test_actor')
    if actor_class is None:
        return None

    factory = unreal.BlueprintFactory()
    factory.set_editor_property('parent_class', actor_class)
    bp = create_asset(PATHS['interaction'] + '/BP_InteractionTestObject', unreal.Blueprint, factory)
    if bp is None:
        return bp

    cdo = get_default_object_for(bp)
    if cdo:
        apply_defaults(cdo, {
            'interaction_text': unreal.Text('Kutuyu a\u00e7'),
            'activated_interaction_text': unreal.Text('Kutuyu kapat'),
            'inactive_color': unreal.LinearColor(0.75, 0.35, 0.10, 1.0),
            'active_color': unreal.LinearColor(0.15, 0.60, 0.25, 1.0),
        }, 'BP_InteractionTestObject')
    return bp


def create_interaction_component_blueprint():
    """BPC_Interaction : UInteractionComponent.

    Reserved Blueprint extension point for interaction behaviour. The active
    component used by BP_PlayerCharacter is the C++ subobject injected by
    AMyProjectPlayerCharacter (same class family, no duplicated component).
    """
    component_class = load_native_class('interaction_component')
    if component_class is None:
        return None

    factory = unreal.BlueprintFactory()
    factory.set_editor_property('parent_class', component_class)
    return create_asset(PATHS['interaction'] + '/BPC_Interaction', unreal.Blueprint, factory)


def save_everything():
    saved = 0
    for path in list(report['created']) + list(report['existing']):
        try:
            if unreal.EditorAssetLibrary.save_asset(path, only_if_is_dirty=False):
                saved += 1
            else:
                warn('save_asset returned false: ' + path)
        except Exception as exc:
            warn('save_asset failed for {0}: {1}'.format(path, exc))
    report['saved'] = saved
    log('saved assets: {0}'.format(saved))


def write_report():
    rel = unreal.Paths.project_saved_dir() + 'Phase3A/'
    out_dir = unreal.Paths.convert_relative_path_to_full(rel)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    report['result'] = 'OK' if not report['failed'] else 'FAILED'
    path = os.path.join(out_dir, 'phase3a_assets_report.json')
    with open(path, 'w') as handle:
        json.dump(report, handle, indent=2)
    return path


def main():
    for key in ('input', 'ui', 'data', 'core', 'player', 'interaction', 'environment'):
        ensure_folder(PATHS[key])

    ia_interact, imc = create_input_assets()
    prompt_widget = create_prompt_widget()
    data_asset = create_data_asset()
    player_bp = create_player_blueprint(imc, ia_interact, prompt_widget, data_asset)
    game_mode_bp = create_game_mode_blueprint(player_bp)
    create_test_object_blueprint()
    create_interaction_component_blueprint()

    save_everything()
    path = write_report()

    print('PHASE3A_ASSETS_DONE ' + path)
    print('PHASE3A_ASSETS created={0} existing={1} failed={2}'.format(
        len(report['created']), len(report['existing']), len(report['failed'])))
    for note in report['notes'][:25]:
        print('PHASE3A_NOTE: ' + note)
    print('PHASE3A_RESULT: ' + report['result'])


if __name__ == '__main__':
    main()
