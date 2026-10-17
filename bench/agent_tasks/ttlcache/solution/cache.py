import time
from collections import OrderedDict


class LRUCache:
    def __init__(self, capacity, ttl=None, clock=time.monotonic):
        self.capacity = capacity
        self.ttl = ttl
        self.clock = clock
        self._data = OrderedDict()

    def _purge(self):
        if self.ttl is None:
            return
        now = self.clock()
        for key in [k for k, (_, t) in self._data.items() if now - t >= self.ttl]:
            del self._data[key]

    def get(self, key, default=None):
        self._purge()
        if key not in self._data:
            return default
        self._data.move_to_end(key)
        return self._data[key][0]

    def put(self, key, value):
        self._purge()
        self._data[key] = (value, self.clock())
        self._data.move_to_end(key)
        if len(self._data) > self.capacity:
            self._data.popitem(last=False)

    def __contains__(self, key):
        self._purge()
        return key in self._data

    def __len__(self):
        self._purge()
        return len(self._data)
