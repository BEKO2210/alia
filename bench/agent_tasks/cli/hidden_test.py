import json, os, subprocess, sys, tempfile, unittest


def run(*args):
    return subprocess.run([sys.executable, "wc.py", *args], capture_output=True, text=True)


class Hidden(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.a = os.path.join(self.d, "a.txt"); open(self.a, "w").write("one two\nthree\n")
        self.b = os.path.join(self.d, "b.txt"); open(self.b, "w").write("x\n")

    def test_json_two(self):
        r = run("--json", self.a, self.b)
        self.assertEqual(r.returncode, 0)
        data = json.loads(r.stdout)
        self.assertEqual([o["file"] for o in data], [self.a, self.b, "total"])
        self.assertEqual(data[0], {"file": self.a, "lines": 2, "words": 3, "chars": 14})
        self.assertEqual(data[2]["words"], 4)

    def test_json_single_no_total(self):
        data = json.loads(run(self.a, "--json").stdout)
        self.assertEqual(len(data), 1)

    def test_missing_file(self):
        r = run("--json", self.a, os.path.join(self.d, "nope.txt"), self.b)
        self.assertEqual(r.returncode, 1)
        data = json.loads(r.stdout)
        self.assertEqual([o["file"] for o in data], [self.a, self.b, "total"])
        self.assertEqual(data[-1]["lines"], 3)
        self.assertIn("nope.txt", r.stderr)

    def test_plain_unchanged(self):
        r = run(self.a)
        self.assertEqual(r.stdout, f"{2:7} {3:7} {14:7} {self.a}\n")
