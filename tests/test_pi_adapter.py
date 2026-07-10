import json
import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
ADAPTER = ROOT / "adapters" / "pi" / "index.ts"


class PiAdapterTest(unittest.TestCase):
    def test_symlinked_extension_resolves_the_real_plugin_root(self):
        with tempfile.TemporaryDirectory() as temp:
            extension = Path(temp) / ".pi" / "agent" / "extensions" / "messenger.ts"
            extension.parent.mkdir(parents=True)
            extension.symlink_to(ADAPTER)
            program = textwrap.dedent(
                f"""\
                import extension from {extension.as_uri()!r};
                let command;
                let resources;
                let script;
                const pi = {{
                  on(name, handler) {{ if (name === 'resources_discover') resources = handler; }},
                  registerCommand(_name, definition) {{ command = definition; }},
                  async exec(_program, args) {{
                    script = args[0];
                    return {{ code: 0, stdout: '{{"kind":"cancelled","display":"","context":"","detail":""}}', stderr: '' }};
                  }},
                  sendUserMessage() {{}},
                }};
                extension(pi);
                await command.handler('', {{ ui: {{ notify() {{}} }} }});
                console.log(JSON.stringify({{ script, skillPaths: resources().skillPaths }}));
                """
            )
            env = os.environ.copy()
            env["HERDR_ENV"] = "1"
            completed = subprocess.run(
                ["node", "--preserve-symlinks", "--input-type=module", "-e", program],
                text=True,
                capture_output=True,
                env=env,
                timeout=10,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            discovered = json.loads(completed.stdout)
            self.assertEqual(
                Path(discovered["script"]).resolve(),
                ROOT / "scripts" / "harness_command.py",
            )
            self.assertEqual(
                [Path(path).resolve() for path in discovered["skillPaths"]],
                [ROOT / "skills" / "msg" / "SKILL.md"],
            )

    def test_extension_exposes_nothing_outside_herdr(self):
        program = textwrap.dedent(
            f"""\
            import extension from {ADAPTER.as_uri()!r};
            let events = 0;
            let commands = 0;
            extension({{
              on() {{ events += 1; }},
              registerCommand() {{ commands += 1; }},
            }});
            console.log(JSON.stringify({{ events, commands }}));
            """
        )
        env = os.environ.copy()
        env.pop("HERDR_ENV", None)
        completed = subprocess.run(
            ["node", "--input-type=module", "-e", program],
            text=True,
            capture_output=True,
            env=env,
            timeout=10,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout), {"events": 0, "commands": 0})


if __name__ == "__main__":
    unittest.main()
