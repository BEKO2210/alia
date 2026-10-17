def invoice_total(items):
    total = 0.0
    for item in items:
        total += float(item["price"]) * item["qty"]
    return {"net": round(total, 2)}
