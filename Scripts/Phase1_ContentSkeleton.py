# -*- coding: utf-8 -*-
"""Phase 1 - /Game/Game content skeleton for MyProject (UE 5.8, Python 3.11).

Creates the empty folder skeleton only, through the Unreal Editor asset API.

Safety contract
  * idempotent: a second run changes nothing and reports "already_exists"
  * folders are created with unreal.EditorAssetLibrary.make_directory
    (never raw filesystem writes into Content/)
  * no asset is created, loaded, saved, moved, renamed or deleted
  * no .ini / .uproject / .uasset / .umap file is written by this script
  * dry-run performs zero filesystem changes
  * a run report is written to <Project>/Saved/Phase1/ (generated folder)

Headless usage
  UnrealEditor-Cmd.exe "<Project>.uproject" -run=PythonScriptCommandlet -script="<this file>"
  dry run: append -Phase1DryRun, or set the environment variable PHASE1_DRY_RUN=1

Result markers: PHASE1_RESULT: OK | DRY_RUN_OK | FAILED
"""

import json
import os
import sys
from datetime import datetime

import unreal

GAME_ROOT = "/Game/Game"

# Target skeleton (parents always precede their children).
TARGET_FOLDERS = [
    "/Game/Game/Core",
    "/Game/Game/Characters",
    "/Game/Game/Characters/Player",
    "/Game/Game/Characters/NPC",
    "/Game/Game/Vehicles",
    "/Game/Game/Vehicles/Base",
    "/Game/Game/Vehicles/Parts",
    "/Game/Game/Vehicles/Assembly",
    "/Game/Game/Vehicles/Systems",
    "/Game/Game/Vehicles/Systems/Fuel",
    "/Game/Game/Vehicles/Systems/Electrical",
    "/Game/Game/Vehicles/Systems/Thermal",
    "/Game/Game/Vehicles/Systems/Wear",
    "/Game/Game/Environment",
    "/Game/Game/Interaction",
    "/Game/Game/Systems",
    "/Game/Game/Systems/Inventory",
    "/Game/Game/Systems/Tools",
    "/Game/Game/Systems/SaveLoad",
    "/Game/Game/Systems/TimeOfDay",
    "/Game/Game/Systems/Weather",
    "/Game/Game/Systems/Economy",
    "/Game/Game/UI",
    "/Game/Game/Audio",
    "/Game/Game/Data",
    "/Game/Game/Tools",
    "/Game/Game/Tools/Tests",
]

# Template folders that must stay untouched. Read-only evidence gathering.
PROTECTED_FOLDERS = [
    "/Game/FirstPerson",
    "/Game/Characters",
    "/Game/Input",
    "/Game/LevelPrototyping",
]


# --------------------------------------------------------------------------- #
# Logging helpers
# --------------------------------------------------------------------------- #

def log_info(message):
    unreal.log("PHASE1: " + message)


def log_warning(message):
    unreal.log_warning("PHASE1: " + message)


def log_error(message):
    unreal.log_error("PHASE1: " + message)


def safe(call, default):
    """Call a function defensively; never let reporting break the run."""
    try:
        return call()
    except Exception as exc:
        log_warning("safe() fallback ({0}): {1}".format(default, exc))
        return default


# --------------------------------------------------------------------------- #
# Runtime context
# --------------------------------------------------------------------------- #

def command_line():
    """Best-effort command line of the hosting editor process."""
    for getter in (lambda: unreal.SystemLibrary.get_command_line(),
                   lambda: unreal.SystemLibrary.get_editor_command_line()):
        try:
            value = getter()
            if value:
                return str(value)
        except Exception:
            continue
    return ""


def is_dry_run():
    """Dry-run requested through command line, argv or environment variable."""
    tokens = [command_line().lower(), " ".join(sys.argv).lower()]
    for token in tokens:
        if "phase1dryrun" in token or "-dry-run" in token:
            return True
    return os.environ.get("PHASE1_DRY_RUN", "").strip() == "1"


def saved_phase1_dir():
    """<Project>/Saved/Phase1 as an absolute path."""
    relative = safe(lambda: unreal.Paths.project_saved_dir() + "Phase1/", "")
    if relative:
        full = safe(lambda: unreal.Paths.convert_relative_path_to_full(relative), "")
        if full:
            return full
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Saved", "Phase1")


def engine_version():
    return safe(lambda: str(unreal.SystemLibrary.get_engine_version()), "unknown")


def project_file():
    return safe(lambda: str(unreal.Paths.get_project_file_path()), "unknown")


def asset_count(folder):
    """Read-only asset registry count. Never loads or modifies an asset."""
    return safe(lambda: len(unreal.EditorAssetLibrary.list_assets(
        folder, recursive=True, include_folder=False)), -1)


# --------------------------------------------------------------------------- #
# Steps
# --------------------------------------------------------------------------- #

def collect_asset_snapshot():
    """Asset counts for the protected template folders (read-only evidence)."""
    return dict((folder, asset_count(folder)) for folder in PROTECTED_FOLDERS)


def create_skeleton(dry_run):
    """Create only the missing target folders; existing folders are untouched."""
    actions = []
    for folder in TARGET_FOLDERS:
        if unreal.EditorAssetLibrary.does_directory_exist(folder):
            actions.append({"path": folder, "action": "already_exists", "result": "ok"})
            log_info("already exists, untouched: " + folder)
            continue
        if dry_run:
            actions.append({"path": folder, "action": "would_create", "result": "dry_run"})
            log_info("[DRY-RUN] would create: " + folder)
            continue
        created = bool(unreal.EditorAssetLibrary.make_directory(folder))
        actions.append({"path": folder, "action": "created",
                        "result": "ok" if created else "failed"})
        if created:
            log_info("created: " + folder)
        else:
            log_error("FAILED to create: " + folder)
    return actions


def verify_skeleton(dry_run):
    """Verify that every target folder exists. Never modifies anything."""
    results = []
    for folder in TARGET_FOLDERS:
        exists = bool(unreal.EditorAssetLibrary.does_directory_exist(folder))
        results.append({"path": folder, "exists": exists})
        if not exists:
            if dry_run:
                log_warning("missing (dry-run created nothing): " + folder)
            else:
                log_error("VERIFY FAILED, missing folder: " + folder)
    return results


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #

def build_text_report(report):
    summary = report["summary"]
    lines = [
        "Phase 1 - Content skeleton report",
        "=" * 64,
        "timestamp        : " + report["timestamp"],
        "engine version   : " + report["engine_version"],
        "project file     : " + report["project_file"],
        "dry run          : " + str(report["dry_run"]),
        "target folders   : " + str(summary["target_count"]),
        "created          : " + str(summary["created"]),
        "already existing : " + str(summary["already_exists"]),
        "would create     : " + str(summary["would_create"]),
        "failed           : " + str(summary["failed"]),
        "verified present : " + str(summary["verified_present"]),
        "asset writes     : " + str(summary["asset_writes"]) + "   (must be 0)",
        "",
        "Folder actions:",
    ]
    for item in report["folder_actions"]:
        lines.append("  [{0}] {1} -> {2}".format(item["result"], item["action"], item["path"]))
    lines.append("")
    lines.append("Protected template folders (asset count before / after):")
    for folder in PROTECTED_FOLDERS:
        before = report["protected_before"].get(folder, -1)
        after = report["protected_after"].get(folder, -1)
        state = "UNCHANGED" if before == after else "CHANGED!"
        lines.append("  {0:<26} before={1:<5} after={2:<5} {3}".format(folder, before, after, state))
    lines.append("")
    lines.append("Result: " + report["result"])
    return "\n".join(lines) + "\n"


def write_report(report):
    """Write the run report into <Project>/Saved/Phase1/ (generated folder)."""
    files = {}
    try:
        out_dir = saved_phase1_dir()
        if not os.path.isdir(out_dir):
            os.makedirs(out_dir)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_path = os.path.join(out_dir, "phase1_content_skeleton_{0}.json".format(stamp))
        txt_path = os.path.join(out_dir, "phase1_content_skeleton_{0}.txt".format(stamp))
        with open(json_path, "w") as handle:
            json.dump(report, handle, indent=2)
        with open(txt_path, "w") as handle:
            handle.write(build_text_report(report))
        files = {"json": json_path, "txt": txt_path}
        log_info("report: " + json_path)
        log_info("report: " + txt_path)
    except Exception as exc:
        log_warning("report file could not be written: {0}".format(exc))
    return files


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def main():
    dry_run = is_dry_run()
    log_info("start (dry_run={0})".format(dry_run))
    log_info("project file: " + project_file())

    protected_before = collect_asset_snapshot()
    actions = create_skeleton(dry_run)
    verification = verify_skeleton(dry_run)
    protected_after = collect_asset_snapshot()

    created = len([a for a in actions if a["action"] == "created" and a["result"] == "ok"])
    already = len([a for a in actions if a["action"] == "already_exists"])
    would = len([a for a in actions if a["action"] == "would_create"])
    failed = len([a for a in actions if a["result"] == "failed"])
    present = len([v for v in verification if v["exists"]])

    protected_unchanged = protected_before == protected_after
    ok = (present == len(TARGET_FOLDERS)) and protected_unchanged and failed == 0
    if ok:
        result = "OK"
    elif dry_run and protected_unchanged and failed == 0:
        result = "DRY_RUN_OK"
    else:
        result = "FAILED"

    report = {
        "phase": "Phase 1 - Content skeleton",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "engine_version": engine_version(),
        "project_file": project_file(),
        "dry_run": dry_run,
        "game_root": GAME_ROOT,
        "folder_actions": actions,
        "verification": verification,
        "protected_folders": PROTECTED_FOLDERS,
        "protected_before": protected_before,
        "protected_after": protected_after,
        "summary": {
            "target_count": len(TARGET_FOLDERS),
            "created": created,
            "already_exists": already,
            "would_create": would,
            "failed": failed,
            "verified_present": present,
            "asset_writes": 0,
        },
        "result": result,
    }
    report["report_files"] = write_report(report)

    summary = ("targets={0} created={1} already_exists={2} would_create={3} failed={4} "
               "verified_present={5} protected_unchanged={6}").format(
        len(TARGET_FOLDERS), created, already, would, failed, present, protected_unchanged)
    log_info(summary)
    print("PHASE1_SUMMARY: " + summary)
    print("PHASE1_RESULT: " + result)
    if not ok and not dry_run:
        log_error("Phase 1 skeleton did not reach the expected end state.")
    return report


if __name__ == "__main__":
    main()
