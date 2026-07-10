#!/usr/bin/env python3
"""Handle Codex Messenger skill invocations before model submission."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path


INVOCATION = re.compile(r"^\$herdr-agent-messenger:msg(?:\s+(.*))?$", re.DOTALL)


def main():
    event = json.load(sys.stdin)
    match = INVOCATION.fullmatch(event.get("prompt", "").strip())
    if not match:
        return

    root = Path(os.environ["PLUGIN_ROOT"])
    completed = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "harness_command.py"),
            "--arguments",
            match.group(1) or "",
        ],
        text=True,
        capture_output=True,
        env=os.environ,
    )
    if completed.returncode != 0:
        reason = completed.stderr.strip() or "Messenger failed."
        print(json.dumps({"decision": "block", "reason": reason}))
        return

    outcome = json.loads(completed.stdout)
    if outcome["kind"] == "draft":
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "UserPromptSubmit",
                        "additionalContext": outcome["context"],
                    }
                }
            )
        )
        return

    if outcome["kind"] == "cancelled":
        print(json.dumps({"continue": False, "suppressOutput": True}))
        return

    print(json.dumps({"decision": "block", "reason": outcome["display"]}))


if __name__ == "__main__":
    main()
