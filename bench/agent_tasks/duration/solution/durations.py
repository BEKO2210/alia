import re

_RE = re.compile(r"P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?")


def parse_duration(text):
    m = _RE.fullmatch(text or "")
    if not m or text in ("P", "PT") or text.endswith("T") or not any(m.groups()):
        raise ValueError(text)
    if "T" in text and not any(m.groups()[2:]):
        raise ValueError(text)
    w, d, h, mi, s = m.groups()
    return int(w or 0) * 604800 + int(d or 0) * 86400 + int(h or 0) * 3600 + int(mi or 0) * 60 + int(float(s or 0))
