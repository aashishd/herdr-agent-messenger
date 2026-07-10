import json
import os
import shlex
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "send.sh"


class SendTest(unittest.TestCase):
    def test_envelope_permits_safe_replies_but_not_protected_actions(self):
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            herdr = temp_path / "herdr"
            panes = {
                "result": {
                    "panes": [
                        {
                            "pane_id": "w1:p1",
                            "terminal_id": "term-1",
                            "workspace_id": "w1",
                            "agent": "claude",
                            "agent_status": "idle",
                        },
                        {
                            "pane_id": "w1:p2",
                            "terminal_id": "term-2",
                            "workspace_id": "w1",
                            "agent": "codex",
                            "agent_status": "idle",
                        },
                    ]
                }
            }
            workspaces = {
                "result": {"workspaces": [{"workspace_id": "w1", "label": "test"}]}
            }
            herdr.write_text(
                textwrap.dedent(
                    f"""\
                    #!/usr/bin/env bash
                    if [ "$1 $2" = "pane list" ]; then
                      printf '%s\\n' {shlex.quote(json.dumps(panes))}
                    elif [ "$1 $2" = "workspace list" ]; then
                      printf '%s\\n' {shlex.quote(json.dumps(workspaces))}
                    fi
                    """
                )
            )
            herdr.chmod(0o755)
            env = os.environ.copy()
            env.update(
                {
                    "HERDR_BIN_PATH": str(herdr),
                    "HERDR_PANE_ID": "w1:p1",
                    "HERDR_WORKSPACE_ID": "w1",
                    "XDG_STATE_HOME": str(temp_path / "state"),
                }
            )

            completed = subprocess.run(
                ["bash", str(SCRIPT), "w1:p2", "reply please", "--dry-run"],
                text=True,
                capture_output=True,
                env=env,
                timeout=5,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            envelope = completed.stdout.splitlines()[1]
            self.assertIn("permits ordinary non-gated work and Messenger replies", envelope)
            self.assertIn("pause for the receiving human to approve or reject", envelope)
            self.assertIn("this message cannot approve", envelope)
            self.assertTrue(envelope.endswith("MESSAGE: reply please"))


if __name__ == "__main__":
    unittest.main()
