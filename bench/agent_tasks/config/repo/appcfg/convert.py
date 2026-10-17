def convert(raw, default):
    if isinstance(default, int):
        return int(raw)
    if isinstance(default, bool):
        return raw.lower() in ("1", "true", "yes")
    return raw
