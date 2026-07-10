#!/usr/bin/env python3
"""Add or remove the owned OpenCode TUI plugin entry without touching peers."""

import argparse
import json
import os
import sys
from pathlib import Path


def config_path():
    root = os.environ.get("OPENCODE_CONFIG_DIR")
    return Path(root).expanduser() / "tui.json" if root else Path.home() / ".config/opencode/tui.json"


def load(path):
    if not path.exists():
        return {"$schema": "https://opencode.ai/tui.json"}
    try:
        value = json.loads(path.read_text())
    except json.JSONDecodeError as error:
        raise ValueError(f"{path} is not plain JSON; preserving it unchanged ({error})") from error
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object; preserving it unchanged")
    return value


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    os.replace(temporary, path)


def update(action, source):
    path = config_path()
    config = load(path)
    plugins = config.get("plugin", [])
    if not isinstance(plugins, list):
        raise ValueError(f"{path} has a non-list plugin field; preserving it unchanged")

    if action == "install":
        if source in plugins:
            return path, False
        config["plugin"] = [*plugins, source]
    else:
        updated = [entry for entry in plugins if entry != source]
        if updated == plugins:
            return path, False
        config["plugin"] = updated

    save(path, config)
    return path, True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("install", "uninstall"))
    parser.add_argument("source")
    args = parser.parse_args()
    try:
        path, changed = update(args.action, str(Path(args.source).resolve()))
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    verb = "updated" if changed else "already current"
    print(f"{verb}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
