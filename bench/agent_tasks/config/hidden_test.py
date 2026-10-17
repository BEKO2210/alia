import json, os, tempfile, unittest
from appcfg import load_config


class Hidden(unittest.TestCase):
    def test_env_beats_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "c.json")
            with open(p, "w") as f:
                json.dump({"port": 7000, "name": "file"}, f)
            c = load_config(p, env={"APP_PORT": "9000"})
            self.assertEqual(c["port"], 9000)
            self.assertEqual(c["name"], "file")

    def test_bool(self):
        for raw, want in [("1", True), ("TRUE", True), ("on", True), ("Yes", True), ("0", False), ("off", False)]:
            self.assertIs(load_config(env={"APP_DEBUG": raw})["debug"], want, raw)

    def test_unknown_ignored(self):
        self.assertNotIn("color", load_config(env={"APP_COLOR": "red"}))

    def test_missing_file(self):
        self.assertEqual(load_config("/nonexistent.json", env={})["host"], "127.0.0.1")
