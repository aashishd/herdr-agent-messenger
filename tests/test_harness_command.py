import importlib.util
import os
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "harness_command.py"
SPEC = importlib.util.spec_from_file_location("harness_command", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def completed(stdout="", stderr="", returncode=0):
    return CompletedProcess([], returncode, stdout=stdout, stderr=stderr)


class HarnessCommandTest(unittest.TestCase):
    def test_outside_herdr_is_local_unavailable_result(self):
        with patch.dict(os.environ, {}, clear=True):
            outcome = MODULE.classify("")
        self.assertEqual(outcome["kind"], "unavailable")

    def test_case_insensitive_sole_whoami_is_identity_lookup(self):
        with (
            patch.dict(os.environ, {"HERDR_ENV": "1"}, clear=True),
            patch.object(MODULE, "run_script", return_value=completed("quiet-heron\n")) as run,
        ):
            outcome = MODULE.classify("  WhOaMi  ")
        run.assert_called_once_with("whoami.sh")
        self.assertEqual(outcome["display"], "Your call-sign: quiet-heron")

    def test_whoami_with_extra_text_remains_drafting_intent(self):
        detail = "DRAFT-REQUEST\ntarget: calm-otter\nintent: whoami please"
        with (
            patch.dict(os.environ, {"HERDR_ENV": "1"}, clear=True),
            patch.object(MODULE, "run_script", return_value=completed(detail)) as run,
        ):
            outcome = MODULE.classify("whoami please")
        run.assert_called_once_with("compose.sh", "whoami please")
        self.assertEqual(outcome["kind"], "draft")
        self.assertIn(detail, outcome["context"])

    def test_cancellation_has_no_display_or_context(self):
        with (
            patch.dict(os.environ, {"HERDR_ENV": "1"}, clear=True),
            patch.object(MODULE, "run_script", return_value=completed("CANCELLED\n")),
        ):
            outcome = MODULE.classify("")
        self.assertEqual(outcome["kind"], "cancelled")
        self.assertEqual(outcome["display"], "")
        self.assertEqual(outcome["context"], "")

    def test_board_failures_are_distinct_from_cancellation(self):
        cases = {
            "NO-TARGETS": "no-targets",
            "TIMEOUT": "timeout",
            "BOARD-FAILURE": "failure",
            "NOT-SENT\nerror: busy": "failure",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw), patch.dict(
                os.environ, {"HERDR_ENV": "1"}, clear=True
            ), patch.object(MODULE, "run_script", return_value=completed(raw)):
                self.assertEqual(MODULE.classify("")["kind"], expected)


if __name__ == "__main__":
    unittest.main()
