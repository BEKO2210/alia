import json
import os

from .convert import convert
from .defaults import DEFAULTS


def load_config(path=None, env=None):
    env = os.environ if env is None else env
    config = dict(DEFAULTS)
    for key, default in DEFAULTS.items():
        name = "APP_" + key.upper()
        if name in env:
            config[key] = convert(env[name], default)
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            config.update(json.load(handle))
    return config
