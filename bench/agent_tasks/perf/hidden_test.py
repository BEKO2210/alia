import random, time, unittest
from report import merge_events


def slow(streams):
    result = []
    for stream in streams:
        for event in stream:
            existing = [e for e in result if e["id"] == event["id"]]
            if existing:
                if event["ts"] < existing[0]["ts"]:
                    result.remove(existing[0]); result.append(event)
            else:
                result.append(event)
    result.sort(key=lambda e: (e["ts"], e["id"]))
    return result


def gen(n, ids, seed):
    r = random.Random(seed)
    return [[{"id": f"e{r.randrange(ids)}", "ts": r.randrange(50), "source": f"s{s}:{i}"} for i in range(n)] for s in range(3)]


class Hidden(unittest.TestCase):
    def test_same_as_reference(self):
        for seed in range(30):
            streams = gen(60, 40, seed)
            self.assertEqual(merge_events(streams), slow(streams))

    def test_fast(self):
        streams = gen(100000, 150000, 1)
        t = time.perf_counter(); merge_events(streams)
        self.assertLess(time.perf_counter() - t, 3.0)
