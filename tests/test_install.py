import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
INSTALLER = ROOT / "install.sh"


class InstallTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.home = self.base / "home"
        self.tools = self.base / "tools"
        self.bin_dir = self.base / "local-bin"
        self.config_dir = self.home / ".config" / "opencode"
        self.skill_destination = self.config_dir / "skills" / "msg"
        self.install_state = (
            self.home / ".local/state/herdr-agent-messenger/install"
        )
        self.skill_owner = self.install_state / "opencode-skill-source"
        self.payload = (
            self.home / ".local/share/herdr-agent-messenger/plugin"
        )
        self.tool_log = self.base / "tools.log"
        self.home.mkdir()
        self.tools.mkdir()
        self.config_dir.mkdir(parents=True)
        (self.config_dir / "tui.json").write_text(json.dumps({"plugin": []}))
        self.add_tool("opencode")
        (self.tools / "python3").symlink_to(sys.executable)
        self.environment = {
            **os.environ,
            "HOME": str(self.home),
            "MSG_BIN_DIR": str(self.bin_dir),
            "PATH": f"{self.tools}:/usr/bin:/bin",
            "TOOL_LOG": str(self.tool_log),
        }

    def tearDown(self):
        self.temp.cleanup()

    def add_tool(self, name, body="exit 0\n"):
        tool = self.tools / name
        tool.write_text(f"#!/bin/sh\n{body}")
        tool.chmod(0o755)
        return tool

    def add_harness_tools(self):
        body = r'''printf '%s|%s\n' "$(basename "$0")" "$*" >> "$TOOL_LOG"
if [ "$(basename "$0")" = "claude" ]; then
  case "$*" in
    "plugin marketplace list --json"|"plugin list --json") printf '[]\n' ;;
  esac
elif [ "$(basename "$0")" = "codex" ]; then
  case "$*" in
    "plugin marketplace list --json") printf '{"marketplaces": []}\n' ;;
    "plugin list --json") printf '{"installed": []}\n' ;;
  esac
fi
exit 0
'''
        for name in ("claude", "codex", "opencode", "pi"):
            self.add_tool(name, body)
        (self.home / ".claude").mkdir(exist_ok=True)
        (self.home / ".codex").mkdir(exist_ok=True)
        (self.home / ".pi/agent").mkdir(parents=True, exist_ok=True)

    def run_installer(self, *arguments, installer=INSTALLER):
        return subprocess.run(
            ["bash", str(installer), *arguments],
            text=True,
            capture_output=True,
            env=self.environment,
            timeout=30,
        )

    def payload_path(self, relative):
        return self.payload.resolve() / relative

    def create_legacy_wiring(self):
        old_root = (
            self.home
            / ".config/herdr/plugins/.tmp-install-12345-67890/checkout"
        ).resolve()
        links = {
            self.bin_dir / "msg": old_root / "bin/msg",
            self.home / ".claude/commands/msg.md": (
                old_root / "adapters/claude-code/commands/msg.md"
            ),
            self.home / ".pi/agent/extensions/herdr-agent-messenger.ts": (
                old_root / "adapters/pi/index.ts"
            ),
            self.skill_destination: old_root / "skills/msg",
        }
        for destination, source in links.items():
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.symlink_to(
                source,
                target_is_directory=destination == self.skill_destination,
            )
        self.install_state.mkdir(parents=True)
        self.skill_owner.write_text(f"{old_root / 'skills/msg'}\n")
        for name in (
            "claude-marketplace",
            "claude-plugin",
            "codex-marketplace",
            "codex-plugin",
        ):
            (self.install_state / name).touch()
        (self.config_dir / "tui.json").write_text(
            json.dumps(
                {"plugin": [str(old_root / "adapters/opencode/tui.js")]}
            )
        )
        return old_root, links

    def test_opencode_skill_install_update_and_uninstall_are_owned(self):
        installed = self.run_installer()
        self.assertEqual(installed.returncode, 0, installed.stderr)
        self.assertTrue(self.skill_destination.is_symlink())
        self.assertEqual(
            self.skill_destination.resolve(), self.payload_path("skills/msg")
        )
        self.assertEqual(
            self.skill_owner.read_text().strip(),
            str(self.payload_path("skills/msg")),
        )

        config = json.loads((self.config_dir / "tui.json").read_text())
        self.assertEqual(
            config["plugin"],
            [str(self.payload_path("adapters/opencode/tui.js"))],
        )

        obsolete = self.payload / "obsolete-from-previous-version"
        obsolete.write_text("remove me\n")
        repeated = self.run_installer()
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertTrue(self.skill_destination.is_symlink())
        self.assertFalse(obsolete.exists())

        uninstalled = self.run_installer(
            "--uninstall", installer=self.payload / "install.sh"
        )
        self.assertEqual(uninstalled.returncode, 0, uninstalled.stderr)
        self.assertFalse(self.skill_destination.exists())
        self.assertFalse(self.skill_owner.exists())
        self.assertFalse(self.payload.exists())
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
        user_skill = self.base / "user-skill"
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

    def test_legacy_staging_links_and_registrations_are_migrated(self):
        old_root, links = self.create_legacy_wiring()
        self.add_harness_tools()

        installed = self.run_installer()
        self.assertEqual(installed.returncode, 0, installed.stderr)
        for destination in links:
            self.assertTrue(destination.is_symlink())
            self.assertTrue(destination.exists())
            self.assertNotIn(str(old_root), os.readlink(destination))

        config = json.loads((self.config_dir / "tui.json").read_text())
        self.assertEqual(
            config["plugin"],
            [str(self.payload_path("adapters/opencode/tui.js"))],
        )
        log = self.tool_log.read_text()
        self.assertIn("claude|plugin uninstall", log)
        self.assertIn("claude|plugin marketplace remove", log)
        self.assertIn("codex|plugin remove", log)
        self.assertIn("codex|plugin marketplace remove", log)

    def test_legacy_staging_wiring_can_be_uninstalled_directly(self):
        _old_root, links = self.create_legacy_wiring()
        self.add_harness_tools()

        uninstalled = self.run_installer("--uninstall")
        self.assertEqual(uninstalled.returncode, 0, uninstalled.stderr)
        for destination in links:
            self.assertFalse(destination.is_symlink(), destination)
        config = json.loads((self.config_dir / "tui.json").read_text())
        self.assertEqual(config["plugin"], [])

    def test_custom_xdg_payload_uninstalls_without_original_environment(self):
        custom_data = self.base / "xdg-data"
        custom_state = self.base / "xdg-state"
        custom_payload = custom_data / "herdr-agent-messenger/plugin"
        self.environment["XDG_DATA_HOME"] = str(custom_data)
        self.environment["XDG_STATE_HOME"] = str(custom_state)
        self.add_harness_tools()

        installed = self.run_installer()
        self.assertEqual(installed.returncode, 0, installed.stderr)
        self.assertTrue(custom_payload.is_dir())
        self.environment.pop("XDG_DATA_HOME")
        self.environment.pop("XDG_STATE_HOME")
        self.tool_log.unlink()

        uninstalled = self.run_installer(
            "--uninstall", installer=custom_payload / "install.sh"
        )
        self.assertEqual(uninstalled.returncode, 0, uninstalled.stderr)
        self.assertFalse(custom_payload.exists())
        self.assertFalse((self.bin_dir / "msg").exists())
        log = self.tool_log.read_text()
        self.assertIn("claude|plugin uninstall", log)
        self.assertIn("claude|plugin marketplace remove", log)
        self.assertIn("codex|plugin remove", log)
        self.assertIn("codex|plugin marketplace remove", log)

    def test_fresh_install_survives_staging_checkout_deletion(self):
        self.add_harness_tools()
        staging = self.base / "staging/checkout"
        shutil.copytree(
            ROOT,
            staging,
            ignore=shutil.ignore_patterns(".git", ".pi-subagents", "__pycache__"),
        )

        installed = self.run_installer(installer=staging / "install.sh")
        self.assertEqual(installed.returncode, 0, installed.stderr)
        shutil.rmtree(staging.parent)

        self.assertTrue((self.payload / "scripts/install_payload.py").is_file())
        links = (
            self.bin_dir / "msg",
            self.home / ".claude/commands/msg.md",
            self.home / ".pi/agent/extensions/herdr-agent-messenger.ts",
            self.skill_destination,
        )
        for link in links:
            self.assertTrue(link.is_symlink(), link)
            self.assertTrue(link.exists(), link)
            self.assertIn(str(self.payload.resolve()), str(link.resolve()))

        config = json.loads((self.config_dir / "tui.json").read_text())
        self.assertEqual(
            config["plugin"],
            [str(self.payload_path("adapters/opencode/tui.js"))],
        )
        log = self.tool_log.read_text()
        self.assertNotIn(str(staging), log)
        self.assertIn(
            f"claude|plugin marketplace add {self.payload.resolve()}/ --scope user",
            log,
        )
        self.assertIn(
            f"codex|plugin marketplace add {self.payload.resolve()} --json",
            log,
        )

        self.tool_log.unlink()
        repeated = self.run_installer(installer=self.payload / "install.sh")
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        log = self.tool_log.read_text()
        self.assertIn("claude|plugin update", log)
        self.assertIn("codex|plugin add", log)
        self.assertNotIn("plugin marketplace remove", log)

    def test_unowned_payload_directory_is_preserved(self):
        self.payload.mkdir(parents=True)
        user_file = self.payload / "user-file"
        user_file.write_text("keep\n")

        installed = self.run_installer()
        self.assertNotEqual(installed.returncode, 0)
        self.assertIn("refusing unowned payload directory", installed.stderr)
        self.assertEqual(user_file.read_text(), "keep\n")

    def test_symlink_payload_destination_is_preserved(self):
        user_directory = self.base / "user-payload"
        user_directory.mkdir()
        self.payload.parent.mkdir(parents=True)
        self.payload.symlink_to(user_directory, target_is_directory=True)

        installed = self.run_installer()
        self.assertNotEqual(installed.returncode, 0)
        self.assertIn("refusing symlink payload destination", installed.stderr)
        self.assertTrue(self.payload.is_symlink())
        self.assertEqual(self.payload.resolve(), user_directory.resolve())


if __name__ == "__main__":
    unittest.main()
