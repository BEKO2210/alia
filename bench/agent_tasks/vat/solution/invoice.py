from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")
RATES = {"food": Decimal("0.07")}
DEFAULT_RATE = Decimal("0.19")


def invoice_total(items):
    by_rate = {}
    for item in items:
        rate = RATES.get(item.get("category"), DEFAULT_RATE)
        by_rate[rate] = by_rate.get(rate, Decimal("0")) + Decimal(item["price"]) * item["qty"]
    net = sum(by_rate.values(), Decimal("0")).quantize(CENT, ROUND_HALF_UP)
    vat = sum(((n * r).quantize(CENT, ROUND_HALF_UP) for r, n in by_rate.items()), Decimal("0")).quantize(CENT)
    return {"net": net, "vat": vat, "gross": (net + vat).quantize(CENT)}
