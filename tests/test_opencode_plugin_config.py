import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "opencode_plugin_config.py"
SPEC = importlib.util.spec_from_file_location("opencode_plugin_config", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class OpenCodePluginConfigTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config_dir = Path(self.temp.name)
        self.environment = patch.dict(
            os.environ, {"OPENCODE_CONFIG_DIR": str(self.config_dir)}, clear=True
        )
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.temp.cleanup()

    def test_install_and_uninstall_preserve_peer_values(self):
        path = self.config_dir / "tui.json"
        path.write_text(json.dumps({"theme": "smoke", "plugin": ["peer.js"]}))

        _, changed = MODULE.update("install", "/tmp/messenger.js")
        self.assertTrue(changed)
        self.assertEqual(
            json.loads(path.read_text()),
            {"theme": "smoke", "plugin": ["peer.js", "/tmp/messenger.js"]},
        )

        _, changed = MODULE.update("uninstall", "/tmp/messenger.js")
        self.assertTrue(changed)
        self.assertEqual(
            json.loads(path.read_text()), {"theme": "smoke", "plugin": ["peer.js"]}
        )

    def test_install_is_idempotent(self):
        MODULE.update("install", "/tmp/messenger.js")
        _, changed = MODULE.update("install", "/tmp/messenger.js")
        self.assertFalse(changed)

    def test_non_json_config_is_preserved(self):
        path = self.config_dir / "tui.json"
        original = '{\n  // keep this comment\n  "plugin": []\n}\n'
        path.write_text(original)
        with self.assertRaises(ValueError):
            MODULE.update("install", "/tmp/messenger.js")
        self.assertEqual(path.read_text(), original)


if __name__ == "__main__":
    unittest.main()
