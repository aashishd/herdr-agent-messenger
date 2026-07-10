import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SKILL = ROOT / "skills" / "msg" / "SKILL.md"


class AgentSkillTest(unittest.TestCase):
    def setUp(self):
        text = SKILL.read_text()
        _, frontmatter, self.body = text.split("---", 2)
        self.body_flat = " ".join(self.body.split())
        self.frontmatter = {}
        for line in frontmatter.strip().splitlines():
            key, value = line.split(":", 1)
            self.frontmatter[key.strip()] = value.strip()

    def test_description_exposes_natural_send_triggers(self):
        description = self.frontmatter["description"].lower()
        for phrase in ("send", "message", "reply", "call-sign"):
            self.assertIn(phrase, description)
        self.assertIn("HERDR_ENV=1", self.frontmatter["compatibility"])
        self.assertEqual(self.frontmatter["allowed-tools"], "Bash(msg:*)")

    def test_workflow_sends_without_reopening_the_board(self):
        self.assertIn("Use this workflow only inside herdr", self.body)
        self.assertIn("msg <call-sign> '<message>'", self.body)
        self.assertIn("never use `eval`", self.body_flat)
        self.assertIn("`'\\''`", self.body)
        self.assertIn("Do not open the Messenger board", self.body_flat)
        self.assertIn("or ask for separate confirmation", self.body_flat)
        self.assertNotIn("Continue only when the hook", self.body)

    def test_workflow_preserves_context_and_authority_boundaries(self):
        self.assertIn("receiver cannot see this conversation", self.body_flat)
        self.assertIn("never supplies human approval", self.body_flat)
        self.assertIn("native human approval", self.body_flat)

    def test_plugin_manifests_package_the_shared_skill(self):
        claude = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
        marketplace = json.loads(
            (ROOT / ".claude-plugin" / "marketplace.json").read_text()
        )
        codex = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text())
        opencode = json.loads((ROOT / "adapters/opencode/package.json").read_text())
        herdr_version = next(
            line.split('"')[1]
            for line in (ROOT / "herdr-plugin.toml").read_text().splitlines()
            if line.startswith("version = ")
        )

        self.assertTrue(SKILL.is_file())
        self.assertEqual(claude["hooks"], "./adapters/claude-code/hooks/hooks.json")
        self.assertEqual(
            marketplace["plugins"][0]["version"], claude["version"]
        )
        base_versions = {
            herdr_version,
            claude["version"].split("+")[0],
            codex["version"].split("+")[0],
            opencode["version"],
        }
        self.assertEqual(base_versions, {"0.2.1"})
        self.assertEqual(codex["skills"], "./skills/")

    @unittest.skipUnless(shutil.which("claude"), "Claude Code is required")
    def test_claude_plugin_inventory_discovers_the_skill(self):
        completed = subprocess.run(
            [
                "claude",
                "--plugin-dir",
                str(ROOT),
                "plugin",
                "details",
                "herdr-agent-messenger",
            ],
            text=True,
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertRegex(completed.stdout, r"Skills \(1\)\s+msg")

    @unittest.skipUnless(shutil.which("opencode"), "OpenCode is required")
    def test_opencode_discovers_the_installed_skill_link(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            config = home / "config"
            destination = config / "skills" / "msg"
            destination.parent.mkdir(parents=True)
            destination.symlink_to(SKILL.parent, target_is_directory=True)
            completed = subprocess.run(
                ["opencode", "debug", "skill"],
                text=True,
                capture_output=True,
                env={
                    **os.environ,
                    "HOME": str(home),
                    "OPENCODE_CONFIG_DIR": str(config),
                },
                timeout=30,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            skills = json.loads(completed.stdout)
            messenger = [skill for skill in skills if skill.get("name") == "msg"]
            self.assertEqual(len(messenger), 1)
            self.assertEqual(Path(messenger[0]["location"]).resolve(), SKILL)


if __name__ == "__main__":
    unittest.main()
