# -*- coding: utf-8 -*-
"""Phase 7 - open the level and start PIE for a real play session.

The mouse look works in PIE (the editor path never hits the landscape material instance
assert that a -game build hits), so this starts PIE and then stays out of the way: the tick
callback is never unregistered and PIE is never stopped, which leaves the window playable.

Launch with the EDITOR binary (not -Cmd) so the window is fully interactive:
  UnrealEditor.exe "<project>.uproject" -ExecCmds="py <this file>" -windowed -ResX=1280 -ResY=720
"""

import unreal

LEVEL = '/Game/Game/Environment/Lvl_Rural'
state = {'time': 0.0, 'started': False, 'reported': False}


def log(message):
    print('PHASE7-PLAY: ' + str(message))


def begin_play():
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).editor_request_begin_play()
    log('PIE requested - WASD to walk, mouse/touchpad to look around')


def report_input():
    world = None
    try:
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_game_world()
    except Exception as exc:
        log('game world not readable: {0}'.format(exc))
    if world is None:
        log('PIE world not up yet')
        return False
    pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
    if pawn is None:
        log('no pawn yet')
        return False
    mapping = None
    try:
        mapping = pawn.get_editor_property('imc_game')
    except Exception:
        pass
    log('pawn={0} imc_game={1}'.format(pawn.get_class().get_name(),
                                       mapping.get_path_name() if mapping else 'unknown'))
    return True


def tick(delta_seconds):
    state['time'] += delta_seconds
    if not state['started'] and state['time'] > 6.0:
        state['started'] = True
        begin_play()
        return
    if state['started'] and not state['reported'] and state['time'] > 25.0:
        state['reported'] = report_input()


unreal.EditorLoadingAndSavingUtils.load_map(LEVEL)
log('level loaded: ' + LEVEL)
state['handle'] = unreal.register_slate_post_tick_callback(tick)
log('waiting for the editor to settle, then PIE starts (the window stays playable)')
