def merge_events(streams):
    """Merge several event lists into one.

    Each event is a dict with "id", "ts" (int) and "source". The result contains each id once
    (the occurrence with the smallest ts wins; on equal ts the one from the earlier stream wins),
    sorted by ts, then by id.
    """
    result = []
    for stream in streams:
        for event in stream:
            existing = [e for e in result if e["id"] == event["id"]]
            if existing:
                if event["ts"] < existing[0]["ts"]:
                    result.remove(existing[0])
                    result.append(event)
            else:
                result.append(event)
    result.sort(key=lambda e: (e["ts"], e["id"]))
    return result
