import csv
from decimal import Decimal, InvalidOperation


def _umsatz(raw):
    raw = raw.strip()
    if not raw:
        return Decimal("0")
    return Decimal(raw.replace(".", "").replace(",", "."))


def import_customers(path):
    kunden, fehler, seen = [], [], set()
    with open(path, encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle, delimiter=";"))
    for number, row in enumerate(rows[1:], start=2):
        if not row or all(not c.strip() for c in row):
            continue
        if len(row) != 4:
            fehler.append(f"Zeile {number}: falsche Spaltenanzahl"); continue
        nr, name, email, umsatz = (c.strip() for c in row)
        if not nr.isdigit() or int(nr) <= 0:
            fehler.append(f"Zeile {number}: ungültige kundennr"); continue
        if int(nr) in seen:
            fehler.append(f"Zeile {number}: kundennr doppelt"); continue
        if email.count("@") != 1 or "." not in email.split("@")[1]:
            fehler.append(f"Zeile {number}: ungültige email"); continue
        try:
            value = _umsatz(umsatz)
        except InvalidOperation:
            fehler.append(f"Zeile {number}: ungültiger umsatz"); continue
        seen.add(int(nr))
        kunden.append({"kundennr": int(nr), "name": name, "email": email, "umsatz": value})
    return kunden, fehler
