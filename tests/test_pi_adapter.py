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
                const pi = {{
                  registerCommand(_name, definition) {{ command = definition; }},
                  async exec(_program, args) {{
                    console.log(args[0]);
                    return {{ code: 0, stdout: '{{"kind":"cancelled","display":"","context":"","detail":""}}', stderr: '' }};
                  }},
                  sendUserMessage() {{}},
                }};
                extension(pi);
                await command.handler('', {{ ui: {{ notify() {{}} }} }});
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
            self.assertEqual(
                Path(completed.stdout.strip()).resolve(),
                ROOT / "scripts" / "harness_command.py",
            )


if __name__ == "__main__":
    unittest.main()
