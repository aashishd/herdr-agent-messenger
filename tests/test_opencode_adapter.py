import json
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
ADAPTER = ROOT / "adapters" / "opencode" / "tui.js"


@unittest.skipUnless(shutil.which("node"), "node is required")
class OpenCodeAdapterTest(unittest.TestCase):
    def test_slash_commands_are_available_during_autocomplete(self):
        script = f"""
          process.env.HERDR_ENV = "1";
          const plugin = (await import({json.dumps(ADAPTER.as_uri())})).default;
          let layer;
          await plugin.tui({{
            keymap: {{ registerLayer(value) {{ layer = value; }} }},
          }});
          console.log(JSON.stringify({{
            mode: layer.mode ?? null,
            slashNames: layer.commands.map((command) => command.slashName),
          }}));
        """
        result = subprocess.run(
            ["node", "--input-type=module", "--eval", script],
            check=True,
            capture_output=True,
            text=True,
        )

        registration = json.loads(result.stdout)
        self.assertIsNone(registration["mode"])
        self.assertEqual(registration["slashNames"], ["msg", "msg-whoami"])


if __name__ == "__main__":
    unittest.main()
