#!/usr/bin/env python3
"""Handle Claude Code's /msg expansion before it reaches the model."""

import json
import os
import subprocess
import sys
from pathlib import Path


def stop(display=""):
    output = {"continue": False, "suppressOutput": True}
    if display:
        output["stopReason"] = display
    return output


def main():
    event = json.load(sys.stdin)
    if event.get("command_name") != "msg":
        return

    root = Path(os.environ["CLAUDE_PLUGIN_ROOT"])
    completed = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "harness_command.py"),
            "--arguments",
            event.get("command_args", ""),
        ],
        text=True,
        capture_output=True,
        env=os.environ,
    )
    if completed.returncode != 0:
        print(json.dumps(stop(completed.stderr.strip() or "Messenger failed.")))
        return

    outcome = json.loads(completed.stdout)
    if outcome["kind"] == "draft":
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "UserPromptExpansion",
                        "additionalContext": outcome["context"],
                    }
                }
            )
        )
        return

    print(json.dumps(stop(outcome["display"])))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps(stop(f"Messenger failed: {error}")))
