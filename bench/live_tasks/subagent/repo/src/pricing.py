def apply_discount(cents: int, percent: float) -> int:
    if percent < 0 or percent > 100:
        raise ValueError("discount out of range")
    return round(cents * (100 - percent) / 100)


def bulk_percent(qty: int) -> float:
    return 10.0 if qty >= 50 else 5.0 if qty >= 10 else 0.0
