def euros(cents: int) -> str:
    return f"{cents // 100},{cents % 100:02d} EUR"


def total_line(label: str, cents: int) -> str:
    return f"{label:<20}{euros(cents):>14}"
