import fcntl
import os
import pty
import select
import signal
import stat
import struct
import subprocess
import tempfile
import termios
import time
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "compose-pane.sh"


class BoardProcess:
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory()
        self.work = Path(self.temp.name)
        (self.work / "list").write_text(
            "pane-2\tquiet-heron · workspace · claude · idle · pane-2\n"
        )
        (self.work / "self").write_text("calm-otter · workspace\n")
        self.master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 120, 0, 0))
        env = os.environ.copy()
        env.update({"MSG_WORKDIR": str(self.work), "TERM": "xterm-256color"})

        def attach_terminal():
            os.setsid()
            fcntl.ioctl(slave, termios.TIOCSCTTY, 0)

        self.process = subprocess.Popen(
            ["bash", str(SCRIPT)],
            stdin=slave,
            stdout=slave,
            stderr=slave,
            env=env,
            close_fds=True,
            preexec_fn=attach_terminal,
        )
        os.close(slave)
        self.output = b""
        time.sleep(0.25)
        self.read()

    def read(self):
        deadline = time.monotonic() + 0.2
        while time.monotonic() < deadline:
            ready, _, _ = select.select([self.master], [], [], 0.05)
            if not ready:
                break
            try:
                self.output += os.read(self.master, 65536)
            except OSError:
                break
        return self.output

    def send(self, data, delay=0.2):
        os.write(self.master, data)
        time.sleep(delay)
        self.read()

    def close(self):
        if self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=2)
        os.close(self.master)
        self.temp.cleanup()


class ComposePaneTest(unittest.TestCase):
    def setUp(self):
        self.board = BoardProcess()
        if self.board.process.poll() is not None and b"operation not permitted" in self.board.output:
            self.board.close()
            self.skipTest("fzf cannot acquire a terminal in this sandbox")

    def tearDown(self):
        self.board.close()

    def assert_running(self):
        self.assertIsNone(self.board.process.poll())

    def assert_cancelled(self):
        self.board.process.wait(timeout=3)
        self.assertEqual((self.board.work / "outcome").read_text().strip(), "cancelled")

    def test_target_stage_requires_two_escapes(self):
        self.board.send(b"\x1b")
        self.assert_running()
        self.assertIn(b"Press Escape again to cancel", self.board.output)
        self.board.send(b"\x1b")
        self.assert_cancelled()

    def test_interaction_resets_target_stage_confirmation(self):
        self.board.send(b"\x1b")
        self.board.send(b"s")
        self.board.send(b"\x1b")
        self.assert_running()
        self.board.send(b"\x1b")
        self.assert_cancelled()

    def test_message_stage_requires_two_escapes(self):
        self.board.send(b"\r", delay=0.35)
        self.assertTrue((self.board.work / "target").exists())
        self.board.send(b"\x1b")
        self.assert_running()
        self.assertIn(b"Press Escape again to cancel", self.board.output)
        self.board.send(b"\x1b")
        self.assert_cancelled()

    def test_empty_message_stays_open(self):
        self.board.send(b"\r", delay=0.35)
        self.board.send(b"\r", delay=0.35)
        self.assert_running()
        self.assertIn(b"Message required", self.board.output)
        self.board.send(b"\x1b")
        self.board.send(b"\x1b")
        self.assert_cancelled()


class ComposePaneDraftRequestTest(unittest.TestCase):
    def test_tab_submits_instructions_as_a_draft_request(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work = root / "work"
            fake_bin = root / "bin"
            work.mkdir()
            fake_bin.mkdir()
            (work / "list").write_text(
                "pane-2\tquiet-heron · workspace · claude · idle · pane-2\n"
            )
            (work / "self").write_text("calm-otter · workspace\n")

            fake_fzf = fake_bin / "fzf"
            fake_fzf.write_text(
                """#!/usr/bin/env bash
set -euo pipefail
count_file="$MSG_WORKDIR/fake-fzf-count"
count="$(cat "$count_file" 2>/dev/null || printf 0)"
count=$((count + 1))
printf '%s\n' "$count" > "$count_file"
if [ "$count" -eq 1 ]; then
  sed -n 1p "$MSG_WORKDIR/list"
  exit 0
fi
printf '%s\n' "$@" > "$MSG_WORKDIR/message-args"
saw_tab=0
while [ "$#" -gt 0 ]; do
  [ "$1" = "--expect" ] && exit 88
  if [ "$1" = "--bind" ]; then
    shift
    case "$1" in
      tab:*accept-or-print-query*) saw_tab=1 ;;
    esac
  fi
  shift
done
[ "$saw_tab" -eq 1 ] || exit 89
touch "$MSG_WORKDIR/draft-request"
printf '%s\n' 'Summarize status and ask for blockers'
"""
            )
            fake_fzf.chmod(fake_fzf.stat().st_mode | stat.S_IXUSR)
            env = os.environ.copy()
            env.update(
                {
                    "MSG_WORKDIR": str(work),
                    "PATH": f"{fake_bin}:{env['PATH']}",
                }
            )

            completed = subprocess.run(
                ["bash", str(SCRIPT)],
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.stdout, "")
            self.assertEqual((work / "outcome").read_text().strip(), "submitted")
            self.assertEqual((work / "mode").read_text().strip(), "draft")
            self.assertEqual(
                (work / "text").read_text().strip(),
                "Summarize status and ask for blockers",
            )
            args = (work / "message-args").read_text()
            self.assertIn("ENTER: send your text exactly as typed", args)
            self.assertIn(
                "TAB: give your agent instructions to write and send the message",
                args,
            )


if __name__ == "__main__":
    unittest.main()
