import unittest
from appcfg import load_config


class LoaderTest(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual(load_config(env={})["port"], 8080)

    def test_env_port(self):
        self.assertEqual(load_config(env={"APP_PORT": "9000"})["port"], 9000)


if __name__ == "__main__":
    unittest.main()
