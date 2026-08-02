import json
import os
import shlex
import stat
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


class LiveSendTest(unittest.TestCase):
    def make_environment(self, temp_path, *, fail=False, diagnostics=False):
        herdr = temp_path / "herdr"
        log = temp_path / "herdr-calls.jsonl"
        diagnostic_log = temp_path / "delivery.jsonl"
        herdr.write_text(
            textwrap.dedent(
                """\
                #!/usr/bin/env python3
                import json
                import os
                import sys
                from pathlib import Path

                args = sys.argv[1:]
                with Path(os.environ["FAKE_HERDR_LOG"]).open("a") as output:
                    output.write(json.dumps(args) + "\\n")

                if args == ["pane", "list"]:
                    print(os.environ["FAKE_PANES_JSON"])
                elif args == ["workspace", "list"]:
                    print(os.environ["FAKE_WORKSPACES_JSON"])
                elif args[:2] == ["agent", "get"]:
                    print(os.environ["FAKE_AGENT_IDLE_JSON"])
                elif args[:2] == ["agent", "prompt"]:
                    if os.environ.get("FAKE_PROMPT_FAIL") == "1":
                        print(json.dumps({
                            "error": {
                                "code": "agent_prompt_stalled",
                                "message": "no observed state change",
                            }
                        }))
                        raise SystemExit(1)
                    print(os.environ["FAKE_AGENT_WORKING_JSON"])
                else:
                    print(json.dumps({"error": {"code": "unexpected", "args": args}}))
                    raise SystemExit(1)
                """
            )
        )
        herdr.chmod(0o755)

        panes = {
            "result": {
                "panes": [
                    {
                        "pane_id": "w1:p1",
                        "terminal_id": "term-1",
                        "workspace_id": "w1",
                        "agent": "pi",
                        "agent_status": "idle",
                    },
                    {
                        "pane_id": "w1:p2",
                        "terminal_id": "term-2",
                        "workspace_id": "w1",
                        "agent": "claude",
                        "agent_status": "idle",
                    },
                ]
            }
        }
        workspaces = {
            "result": {"workspaces": [{"workspace_id": "w1", "label": "test"}]}
        }

        def agent_snapshot(status, sequence):
            return {
                "result": {
                    "agent": {
                        "pane_id": "w1:p2",
                        "agent": "claude",
                        "agent_status": status,
                        "state_change_seq": sequence,
                        "agent_session": {
                            "kind": "id",
                            "source": "test",
                            "value": "receiver-session-123",
                        },
                    }
                }
            }

        env = os.environ.copy()
        env.update(
            {
                "HERDR_BIN_PATH": str(herdr),
                "HERDR_PANE_ID": "w1:p1",
                "HERDR_WORKSPACE_ID": "w1",
                "XDG_STATE_HOME": str(temp_path / "state"),
                "FAKE_HERDR_LOG": str(log),
                "FAKE_PANES_JSON": json.dumps(panes),
                "FAKE_WORKSPACES_JSON": json.dumps(workspaces),
                "FAKE_AGENT_IDLE_JSON": json.dumps(agent_snapshot("idle", 10)),
                "FAKE_AGENT_WORKING_JSON": json.dumps(agent_snapshot("working", 11)),
                "FAKE_PROMPT_FAIL": "1" if fail else "0",
            }
        )
        if diagnostics:
            env.update(
                {
                    "MSG_DIAGNOSTICS": "1",
                    "MSG_DIAGNOSTICS_PATH": str(diagnostic_log),
                }
            )
        return env, log, diagnostic_log

    def run_send(self, env, message):
        return subprocess.run(
            ["bash", str(SCRIPT), "w1:p2", message],
            text=True,
            capture_output=True,
            env=env,
            timeout=15,
        )

    def test_live_delivery_uses_agent_prompt_and_observes_any_state_change(self):
        with tempfile.TemporaryDirectory() as temp:
            env, log, _diagnostic_log = self.make_environment(Path(temp))
            completed = self.run_send(env, "status update")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("delivered to", completed.stdout)
            calls = [json.loads(line) for line in log.read_text().splitlines()]
            prompt = next(call for call in calls if call[:2] == ["agent", "prompt"])
            self.assertEqual(prompt[2], "w1:p2")
            self.assertTrue(prompt[3].endswith("MESSAGE: status update"))
            self.assertEqual(
                prompt[4:],
                [
                    "--wait",
                    "--until",
                    "idle",
                    "--until",
                    "working",
                    "--until",
                    "blocked",
                    "--until",
                    "done",
                    "--until",
                    "unknown",
                    "--timeout",
                    "7000",
                ],
            )
            self.assertFalse(any(call[:2] == ["pane", "run"] for call in calls))
            self.assertFalse(any(call[:2] == ["agent", "get"] for call in calls))

    def test_stalled_prompt_is_not_retried_or_reported_as_delivered(self):
        with tempfile.TemporaryDirectory() as temp:
            env, log, _diagnostic_log = self.make_environment(Path(temp), fail=True)
            completed = self.run_send(env, "status update")

            self.assertEqual(completed.returncode, 6)
            self.assertNotIn("delivered to", completed.stdout)
            self.assertIn("delivery submission was not observed", completed.stderr)
            self.assertIn("inspect it before retrying", completed.stderr)
            self.assertIn("agent_prompt_stalled", completed.stderr)
            calls = [json.loads(line) for line in log.read_text().splitlines()]
            prompts = [call for call in calls if call[:2] == ["agent", "prompt"]]
            self.assertEqual(len(prompts), 1)
            self.assertFalse(any(call[:2] == ["agent", "send-keys"] for call in calls))

    def test_opt_in_diagnostics_are_private_and_omit_message_content(self):
        with tempfile.TemporaryDirectory() as temp:
            env, _log, diagnostic_log = self.make_environment(
                Path(temp), diagnostics=True
            )
            diagnostic_log.write_text("")
            diagnostic_log.chmod(0o644)
            secret_body = "highly-sensitive-body"
            completed = self.run_send(env, secret_body)

            self.assertEqual(completed.returncode, 0, completed.stderr)
            raw = diagnostic_log.read_text()
            self.assertNotIn(secret_body, raw)
            record = json.loads(raw)
            self.assertEqual(record["command"], "herdr agent prompt")
            self.assertEqual(record["result"], "observed")
            self.assertEqual(record["target_pane"], "w1:p2")
            self.assertEqual(record["target_harness"], "claude")
            self.assertEqual(record["before"]["status"], "idle")
            self.assertEqual(record["submission"]["status"], "working")
            self.assertEqual(record["after"]["session_identity"], "receiver-session-123")
            self.assertGreater(record["envelope_bytes"], len(secret_body))
            self.assertEqual(stat.S_IMODE(diagnostic_log.stat().st_mode), 0o600)

    def test_diagnostics_reject_an_unsafe_override_without_failing_delivery(self):
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            env, _log, _diagnostic_log = self.make_environment(temp_path)
            unsafe_parent = temp_path / "shared"
            unsafe_parent.mkdir()
            unsafe_parent.chmod(0o777)
            diagnostic_log = unsafe_parent / "delivery.jsonl"
            env.update(
                {
                    "MSG_DIAGNOSTICS": "1",
                    "MSG_DIAGNOSTICS_PATH": str(diagnostic_log),
                }
            )

            completed = self.run_send(env, "body-not-for-diagnostics")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("could not write delivery diagnostics", completed.stderr)
            self.assertFalse(diagnostic_log.exists())

    def test_diagnostics_reject_a_fifo_without_blocking_delivery(self):
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            env, _log, _diagnostic_log = self.make_environment(temp_path)
            private_parent = temp_path / "private"
            private_parent.mkdir(mode=0o700)
            diagnostic_fifo = private_parent / "delivery.jsonl"
            os.mkfifo(diagnostic_fifo, mode=0o600)
            env.update(
                {
                    "MSG_DIAGNOSTICS": "1",
                    "MSG_DIAGNOSTICS_PATH": str(diagnostic_fifo),
                }
            )

            completed = self.run_send(env, "body-not-for-diagnostics")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("could not write delivery diagnostics", completed.stderr)
            self.assertTrue(stat.S_ISFIFO(diagnostic_fifo.stat().st_mode))


if __name__ == "__main__":
    unittest.main()
