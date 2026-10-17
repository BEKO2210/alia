def parse_duration(text):
    """Parse a subset of ISO 8601 durations.

    Format: "P" [n "W"] [n "D"] ["T" [n "H"] [n "M"] [n "S"]]
    - n is a non-negative integer; only the seconds part may have a fraction like "1.5S",
      which is rounded down to whole seconds.
    - Weeks may be combined with days.
    - Units must appear in the order shown, each at most once.
    - "T" must be followed by at least one time unit. "P" alone or "PT" is invalid.
    - Lower-case input is invalid. No signs, no spaces.
    Examples: "PT1H30M" -> 5400, "P1W2D" -> 777600, "PT0.9S" -> 0, "P1DT1S" -> 86401.
    """
    raise NotImplementedError
