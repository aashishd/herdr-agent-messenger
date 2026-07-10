import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
INSTALLER = ROOT / "install.sh"
SKILL_SOURCE = ROOT / "skills" / "msg"


class InstallTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name) / "home"
        self.tools = Path(self.temp.name) / "tools"
        self.bin_dir = Path(self.temp.name) / "local-bin"
        self.config_dir = self.home / ".config" / "opencode"
        self.skill_destination = self.config_dir / "skills" / "msg"
        self.skill_owner = (
            self.home
            / ".local/state/herdr-agent-messenger/install/opencode-skill-source"
        )
        self.home.mkdir()
        self.tools.mkdir()
        self.config_dir.mkdir(parents=True)
        (self.config_dir / "tui.json").write_text(json.dumps({"plugin": []}))
        opencode = self.tools / "opencode"
        opencode.write_text("#!/bin/sh\nexit 0\n")
        opencode.chmod(0o755)
        (self.tools / "python3").symlink_to(sys.executable)
        self.environment = {
            **os.environ,
            "HOME": str(self.home),
            "MSG_BIN_DIR": str(self.bin_dir),
            "PATH": f"{self.tools}:/usr/bin:/bin",
        }

    def tearDown(self):
        self.temp.cleanup()

    def run_installer(self, *arguments):
        return subprocess.run(
            ["bash", str(INSTALLER), *arguments],
            text=True,
            capture_output=True,
            env=self.environment,
            timeout=30,
        )

    def test_opencode_skill_install_and_uninstall_are_owned(self):
        installed = self.run_installer()
        self.assertEqual(installed.returncode, 0, installed.stderr)
        self.assertTrue(self.skill_destination.is_symlink())
        self.assertEqual(self.skill_destination.resolve(), SKILL_SOURCE)
        self.assertEqual(self.skill_owner.read_text().strip(), str(SKILL_SOURCE))

        config = json.loads((self.config_dir / "tui.json").read_text())
        self.assertEqual(
            config["plugin"], [str((ROOT / "adapters/opencode/tui.js").resolve())]
        )

        repeated = self.run_installer()
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertTrue(self.skill_destination.is_symlink())

        uninstalled = self.run_installer("--uninstall")
        self.assertEqual(uninstalled.returncode, 0, uninstalled.stderr)
        self.assertFalse(self.skill_destination.exists())
        self.assertFalse(self.skill_owner.exists())
        config = json.loads((self.config_dir / "tui.json").read_text())
        self.assertEqual(config["plugin"], [])

    def test_existing_user_skill_directory_is_preserved(self):
        self.skill_destination.mkdir(parents=True)
        user_skill = self.skill_destination / "SKILL.md"
        user_skill.write_text("user-owned\n")

        installed = self.run_installer()
        self.assertEqual(installed.returncode, 0, installed.stderr)
        self.assertFalse(self.skill_destination.is_symlink())
        self.assertEqual(user_skill.read_text(), "user-owned\n")

        uninstalled = self.run_installer("--uninstall")
        self.assertEqual(uninstalled.returncode, 0, uninstalled.stderr)
        self.assertEqual(user_skill.read_text(), "user-owned\n")

    def test_existing_user_skill_symlink_is_preserved(self):
        user_skill = Path(self.temp.name) / "user-skill"
        user_skill.mkdir()
        self.skill_destination.parent.mkdir(parents=True)
        self.skill_destination.symlink_to(user_skill, target_is_directory=True)

        installed = self.run_installer()
        self.assertEqual(installed.returncode, 0, installed.stderr)
        self.assertEqual(self.skill_destination.resolve(), user_skill.resolve())

        uninstalled = self.run_installer("--uninstall")
        self.assertEqual(uninstalled.returncode, 0, uninstalled.stderr)
        self.assertTrue(self.skill_destination.is_symlink())
        self.assertEqual(self.skill_destination.resolve(), user_skill.resolve())

    def test_recorded_skill_link_is_refreshed_after_checkout_moves(self):
        old_source = Path(self.temp.name) / "old-checkout" / "skills" / "msg"
        old_source.mkdir(parents=True)
        self.skill_destination.parent.mkdir(parents=True)
        self.skill_destination.symlink_to(old_source, target_is_directory=True)
        self.skill_owner.parent.mkdir(parents=True)
        self.skill_owner.write_text(f"{old_source}\n")

        installed = self.run_installer()
        self.assertEqual(installed.returncode, 0, installed.stderr)
        self.assertEqual(self.skill_destination.resolve(), SKILL_SOURCE)
        self.assertEqual(self.skill_owner.read_text().strip(), str(SKILL_SOURCE))


if __name__ == "__main__":
    unittest.main()
