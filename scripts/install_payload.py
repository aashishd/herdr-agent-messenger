#!/usr/bin/env python3
"""Atomically copy the plugin checkout to its durable integration payload."""

import os
import shutil
import sys
import tempfile
from pathlib import Path


MARKER = ".herdr-agent-messenger-payload"
REQUIRED_PATHS = (
    ".claude-plugin/marketplace.json",
    ".claude-plugin/plugin.json",
    ".codex-plugin/plugin.json",
    "adapters/claude-code/commands/msg.md",
    "adapters/claude-code/hooks/hooks.json",
    "adapters/claude-code/hooks/user_prompt_expansion.py",
    "adapters/codex/hooks/hooks.json",
    "adapters/codex/hooks/user_prompt_submit.py",
    "adapters/opencode/package.json",
    "adapters/opencode/tui.js",
    "adapters/pi/index.ts",
    "bin/msg",
    "herdr-plugin.toml",
    "install.sh",
    "scripts/compose-pane.sh",
    "scripts/compose.sh",
    "scripts/harness_command.py",
    "scripts/install_payload.py",
    "scripts/msg_names.py",
    "scripts/opencode_plugin_config.py",
    "scripts/send.sh",
    "scripts/whoami.sh",
    "skills/msg/SKILL.md",
)


def validate(root: Path) -> None:
    missing = [path for path in REQUIRED_PATHS if not (root / path).is_file()]
    if missing:
        raise ValueError(f"payload is missing required files: {', '.join(missing)}")


def ignored(_directory: str, names):
    return {
        name
        for name in names
        if name in {".git", ".pi-subagents", "__pycache__"}
        or name.endswith((".pyc", ".pyo"))
    }


def install(source: Path, destination: Path) -> Path:
    source = source.resolve(strict=True)
    destination = destination.expanduser()
    if destination.is_symlink():
        raise ValueError(f"refusing symlink payload destination: {destination}")
    destination = destination.resolve(strict=False)
    validate(source)

    if source == destination:
        if not (destination / MARKER).is_file():
            raise ValueError(f"refusing unowned payload directory: {destination}")
        return destination
    if source in destination.parents:
        raise ValueError(f"payload destination must be outside its source: {destination}")

    if destination.exists() and not (destination / MARKER).is_file():
        raise ValueError(f"refusing unowned payload directory: {destination}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".plugin-stage-", dir=destination.parent))
    backup = destination.parent / f".plugin-backup-{os.getpid()}"
    try:
        shutil.copytree(source, stage, dirs_exist_ok=True, ignore=ignored)
        (stage / MARKER).write_text("managed by herdr-agent-messenger\n")
        validate(stage)

        if backup.exists():
            shutil.rmtree(backup)
        if destination.exists():
            os.replace(destination, backup)
        try:
            os.replace(stage, destination)
        except Exception:
            if backup.exists() and not destination.exists():
                os.replace(backup, destination)
            raise
        if backup.exists():
            shutil.rmtree(backup)
    finally:
        if stage.exists():
            shutil.rmtree(stage)

    return destination.resolve(strict=True)


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: install_payload.py SOURCE DESTINATION", file=sys.stderr)
        return 64
    try:
        destination = install(Path(sys.argv[1]), Path(sys.argv[2]))
    except (OSError, ValueError) as error:
        print(f"install payload: {error}", file=sys.stderr)
        return 1
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
