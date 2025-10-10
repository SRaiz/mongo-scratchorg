#!/usr/bin/env python3
"""
Interactive pull wizard for Salesforce source using the sf CLI.

Usage examples:
  python3 scripts/cli-tools/pull_metadata.py
  python3 scripts/cli-tools/pull_metadata.py --target-org tstools-14367
"""

from __future__ import annotations
from pathlib import Path
import argparse
import json
import subprocess
import sys
import shlex

import logger  # your loguru-based logger module

# -----------------------------
# Helper: run shell commands
# -----------------------------
def run(cmd: list[str], *, cwd: Path | None = None, passthrough: bool = True) -> str | None:
    pretty = " ".join(shlex.quote(c) for c in cmd)
    logger.status(f"$ {pretty}")
    try:
        if passthrough:
            subprocess.run(cmd, check=True, cwd=str(cwd) if cwd else None)
            logger.success(pretty)
            return None
        else:
            out = subprocess.run(
                cmd,
                cwd=str(cwd) if cwd else None,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            logger.success(pretty)
            return out.stdout
    except subprocess.CalledProcessError as e:
        logger.error(f"FAILED: {pretty}")
        if getattr(e, "stdout", None):
            print(e.stdout)
        sys.exit(1)

# -----------------------------
# Project discovery
# -----------------------------
def find_project_root(start: Path) -> Path:
    """
    Walk up until we find sfdx-project.json.
    """
    p = start.resolve()
    for parent in [p, *p.parents]:
        if (parent / "sfdx-project.json").exists():
            return parent
    logger.error("Couldn't find sfdx-project.json up the directory tree.")
    sys.exit(1)

# -----------------------------
# Input helpers
# -----------------------------
def ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}] " if default else " "
    val = input(f"{prompt}{suffix}").strip()
    return val or (default or "")

def ask_bool(prompt: str, default: bool = False) -> bool:
    suffix = " [Y/n] " if default else " [y/N] "
    val = input(f"{prompt}{suffix}").strip().lower()
    if not val:
        return default
    return val in {"y", "yes"}

def choose_many(prompt: str, options: list[str]) -> list[str]:
    """
    Let user select multiple items by index: "1,3,7"
    Returns chosen strings.
    """
    print()
    logger.info(prompt)
    for i, opt in enumerate(options, start=1):
        print(f"  {i:2d}) {opt}")
    print()
    raw = input("Enter number(s) separated by comma, or leave blank to cancel: ").strip()
    if not raw:
        return []
    picks: list[str] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        if not token.isdigit():
            logger.warning(f"Ignoring '{token}' (not a number).")
            continue
        idx = int(token)
        if 1 <= idx <= len(options):
            picks.append(options[idx - 1])
        else:
            logger.warning(f"Ignoring '{token}' (out of range).")
    return picks

# -----------------------------
# Curated metadata menu
# -----------------------------
CURATED_TYPES = [
    "ApexClass",
    "ApexTrigger",
    "ApexPage",
    "ApexComponent",
    "LightningComponentBundle",     # LWC
    "AuraDefinitionBundle",         # Aura
    "LightningMessageChannel",
    "CustomObject",
    "CustomField",                  # use with CustomObject or by itself in manifest scenarios
    "Layout",
    "RecordType",
    "Flow",
    "FlowDefinition",
    "ValidationRule",
    "PermissionSet",
    "PermissionSetGroup",
    "Profile",
    "FlexiPage",
    "GlobalValueSet",
    "StaticResource",
    "CustomApplication",
    "CustomTab",
    "RemoteSiteSetting",
    "NamedCredential",
    "ConnectedApp",
    "EmailTemplate",
    "Report",
    "Dashboard",
    "ReportType",
    "Translations",
]

# -----------------------------
# Pull modes
# -----------------------------
def pull_everything(project_root: Path, target_org: str, ignore_conflicts: bool):
    cmd = [
        "sf", "project", "retrieve", "start",
        "--target-org", target_org,
    ]
    if ignore_conflicts:
        cmd.append("--ignore-conflicts")
    run(cmd, cwd=project_root, passthrough=True)

def pull_by_types(project_root: Path, target_org: str, ignore_conflicts: bool):
    picks = choose_many("Select metadata types to retrieve:", CURATED_TYPES)
    print()
    extra = ask("Optionally enter additional types (comma-separated), e.g. 'NamedCredential,CustomMetadata':")
    extra = extra.strip()
    types = picks.copy()
    if extra:
        types += [t.strip() for t in extra.split(",") if t.strip()]

    if not types:
        logger.warning("No types selected. Nothing to do.")
        return

    cmd = [
        "sf", "project", "retrieve", "start",
        "--target-org", target_org,
    ]
    for t in types:
        cmd += ["--metadata", f"{t}:*"]

    if ignore_conflicts:
        cmd.append("--ignore-conflicts")

    run(cmd, cwd=project_root, passthrough=True)

def pull_by_paths(project_root: Path, target_org: str, ignore_conflicts: bool):
    logger.info("Enter one or more project paths (relative to repo root),")
    logger.info("for example:")
    logger.info("  force-app/main/default/classes")
    logger.info("  force-app/main/default/objects/Account")
    logger.info("Separate multiple entries with commas.")
    print()
    raw = input("Paths: ").strip()
    if not raw:
        logger.warning("No paths provided. Nothing to do.")
        return

    paths = [p.strip() for p in raw.split(",") if p.strip()]
    cmd = [
        "sf", "project", "retrieve", "start",
        "--target-org", target_org,
    ]
    for p in paths:
        cmd += ["--source-dir", p]

    if ignore_conflicts:
        cmd.append("--ignore-conflicts")

    run(cmd, cwd=project_root, passthrough=True)

def pull_by_manifest(project_root: Path, target_org: str, ignore_conflicts: bool):
    logger.info("Choose one:")
    print("  1) Use existing package.xml")
    print("  2) Generate package.xml from org, then retrieve")
    choice = input("Enter 1 or 2: ").strip()

    manifest_path: Path | None = None

    if choice == "1":
        default_manifest = project_root / "manifest" / "package.xml"
        mp = ask("Path to package.xml", str(default_manifest if default_manifest.exists() else "manifest/package.xml"))
        manifest_path = (project_root / mp).resolve()
        if not manifest_path.exists():
            logger.error(f"package.xml not found at: {manifest_path}")
            sys.exit(1)
    elif choice == "2":
        out_dir = project_root / "manifest"
        out_dir.mkdir(parents=True, exist_ok=True)
        run([
            "sf", "project", "generate", "manifest",
            "--from-org", target_org,
            "--output-dir", str(out_dir),
        ], cwd=project_root, passthrough=True)
        manifest_path = out_dir / "package.xml"
        if not manifest_path.exists():
            logger.error("Failed to generate manifest/package.xml")
            sys.exit(1)
    else:
        logger.warning("Invalid choice; aborting manifest flow.")
        return

    cmd = [
        "sf", "project", "retrieve", "start",
        "--target-org", target_org,
        "--manifest", str(manifest_path),
    ]
    if ignore_conflicts:
        cmd.append("--ignore-conflicts")
    run(cmd, cwd=project_root, passthrough=True)

def reset_tracking(project_root: Path, target_org: str):
    logger.warning("This will reset local source tracking. Useful when the workspace and org drift.")
    if not ask_bool("Proceed with reset?", default=False):
        logger.info("Canceled.")
        return
    run(["sf", "project", "reset", "tracking", "--target-org", target_org, "--no-prompt"], cwd=project_root, passthrough=True)

# -----------------------------
# Main menu
# -----------------------------
def main():
    parser = argparse.ArgumentParser(description="Interactive pull wizard for Salesforce metadata (sf CLI).")
    parser.add_argument("--target-org", help="Org alias/username to pull from (e.g., tstools-14367)")
    parser.add_argument("--ignore-conflicts", action="store_true", help="Pass --ignore-conflicts to retrieve commands")
    args = parser.parse_args()

    project_root = find_project_root(Path.cwd())
    logger.header("Salesforce Pull Wizard")
    logger.info(f"Project root: {project_root}")

    # Detect default alias from sf files (optional best-effort)
    default_alias = None
    config_dir = Path.home() / ".sf" / "orgs"
    if config_dir.exists():
        # Try to find an org config that looks like last default
        for f in config_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                if data.get("isDefaultUsername"):
                    default_alias = data.get("alias") or data.get("username")
                    break
            except Exception:
                pass

    target_org = args.target_org or ask("Target org alias/username?", default_alias or "")
    if not target_org:
        logger.error("You must provide a target org alias/username.")
        sys.exit(1)

    ignore_conflicts = args.ignore_conflicts or ask_bool("Ignore conflicts during retrieve?", default=False)

    while True:
        print()
        logger.step("SELECT ACTION")
        print("  1) Pull ALL source-tracked changes")
        print("  2) Pull by METADATA TYPES")
        print("  3) Pull by PATHS/FOLDERS")
        print("  4) Pull by MANIFEST (package.xml)")
        print("  5) RESET TRACKING (then you can pull)")
        print("  6) Exit")
        choice = input("Choose [1-6]: ").strip()

        if choice == "1":
            pull_everything(project_root, target_org, ignore_conflicts)
        elif choice == "2":
            pull_by_types(project_root, target_org, ignore_conflicts)
        elif choice == "3":
            pull_by_paths(project_root, target_org, ignore_conflicts)
        elif choice == "4":
            pull_by_manifest(project_root, target_org, ignore_conflicts)
        elif choice == "5":
            reset_tracking(project_root, target_org)
        elif choice == "6":
            logger.info("Bye!")
            break
        else:
            logger.warning("Invalid choice. Try again.")

if __name__ == "__main__":
    main()