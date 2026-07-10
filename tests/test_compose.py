import json
import os
import shlex
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "compose.sh"


class ComposeTest(unittest.TestCase):
    def test_board_splits_the_invoking_pane(self):
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            log = temp_path / "herdr.log"
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
                    printf '%s\\n' "$*" >> {str(log)!r}
                    if [ "$1 $2" = "pane list" ]; then
                      printf '%s\\n' {shlex.quote(json.dumps(panes))}
                    elif [ "$1 $2" = "workspace list" ]; then
                      printf '%s\\n' {shlex.quote(json.dumps(workspaces))}
                    elif [ "$1 $2" = "pane split" ]; then
                      for value in "$@"; do
                        case "$value" in
                          MSG_WORKDIR=*) work="${{value#MSG_WORKDIR=}}" ;;
                        esac
                      done
                      printf 'cancelled\\n' > "$work/outcome"
                      touch "$work/done"
                      printf '%s\\n' '{{"result":{{"pane":{{"pane_id":"w1:p3"}}}}}}'
                    fi
                    """
                )
            )
            herdr.chmod(0o755)
            env = os.environ.copy()
            env.update(
                {
                    "HERDR_BIN_PATH": str(herdr),
                    "HERDR_ENV": "1",
                    "HERDR_PANE_ID": "w1:p1",
                    "XDG_STATE_HOME": str(temp_path / "state"),
                }
            )

            completed = subprocess.run(
                ["bash", str(SCRIPT)],
                text=True,
                capture_output=True,
                env=env,
                timeout=5,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout.strip(), "CANCELLED")
            calls = log.read_text().splitlines()
            split = next(line for line in calls if line.startswith("pane split "))
            self.assertIn("pane split w1:p1 --direction down --ratio 0.35", split)
            self.assertIn("MSG_WORKDIR=", split)
            self.assertIn("MSG_BOARD_SCRIPT=", split)
            self.assertTrue(any(line.startswith("pane run w1:p3 ") for line in calls))
            self.assertIn("pane close w1:p3", calls)
            self.assertFalse(any(line.startswith("plugin pane open") for line in calls))


if __name__ == "__main__":
    unittest.main()
