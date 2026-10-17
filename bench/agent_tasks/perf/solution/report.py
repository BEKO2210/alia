def merge_events(streams):
    best = {}
    for stream in streams:
        for event in stream:
            current = best.get(event["id"])
            if current is None or event["ts"] < current["ts"]:
                best[event["id"]] = event
    return sorted(best.values(), key=lambda e: (e["ts"], e["id"]))
