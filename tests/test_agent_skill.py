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

    def test_incoming_envelopes_use_the_reply_route(self):
        self.assertIn(
            "Incoming `[agent-msg]` envelopes follow this same workflow",
            self.body_flat,
        )
        self.assertIn("`TO REPLY`", self.body)
        self.assertIn("not failed explicit `/msg` commands", self.body_flat)
        self.assertNotIn("the local Messenger hook is not active", self.body_flat)

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
        minimum_herdr = next(
            line.split('"')[1]
            for line in (ROOT / "herdr-plugin.toml").read_text().splitlines()
            if line.startswith("min_herdr_version = ")
        )
        self.assertEqual(minimum_herdr, "0.7.5")
        base_versions = {
            herdr_version,
            claude["version"].split("+")[0],
            codex["version"].split("+")[0],
            opencode["version"],
        }
        self.assertEqual(base_versions, {"0.2.4"})
        self.assertEqual(codex["skills"], "./skills/")

    def test_codex_hook_is_declared_only_for_codex(self):
        # Claude Code also loads a plugin's default hooks/hooks.json, so the
        # Codex hook must live behind the Codex manifest instead.
        self.assertFalse((ROOT / "hooks" / "hooks.json").exists())
        codex_manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text())
        self.assertEqual(codex_manifest["hooks"], "./adapters/codex/hooks/hooks.json")

        hooks = json.loads((ROOT / codex_manifest["hooks"]).read_text())
        command = hooks["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]

        # Codex sets CLAUDE_PLUGIN_ROOT as well as PLUGIN_ROOT for plugin hooks.
        codex_env = {**os.environ, "PLUGIN_ROOT": str(ROOT), "CLAUDE_PLUGIN_ROOT": str(ROOT)}
        codex_env.pop("HERDR_ENV", None)
        codex = subprocess.run(
            ["sh", "-c", command],
            input=json.dumps({"prompt": "$herdr-agent-messenger:msg whoami"}),
            text=True,
            capture_output=True,
            env=codex_env,
            timeout=5,
        )
        self.assertEqual(codex.returncode, 0, codex.stderr)
        outcome = json.loads(codex.stdout)
        self.assertEqual(outcome["decision"], "block")
        self.assertIn("available only inside herdr", outcome["reason"])

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
