RATES = {"DE": 19, "AT": 20, "FR": 20}


def with_vat(cents: int, country: str) -> int:
    rate = RATES.get(country, 0)
    return cents + round(cents * rate / 100)
