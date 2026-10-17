def import_customers(path):
    """Liest eine Kunden-CSV (UTF-8, evtl. mit BOM, Trennzeichen ";") mit Kopfzeile
    `kundennr;name;email;umsatz`.

    Rückgabe: (kunden, fehler)
    - kunden: Liste von dicts {"kundennr": int, "name": str, "email": str, "umsatz": Decimal}
      in Dateireihenfolge. Leerzeichen um Felder werden entfernt.
    - umsatz ist im deutschen Format: "1.234,50" -> Decimal("1234.50"); leer -> Decimal("0").
    - fehler: Liste von Strings "Zeile N: <grund>" (N = Zeilennummer in der Datei, Kopfzeile = 1)
      für ungültige Zeilen, die übersprungen werden:
        * kundennr keine positive ganze Zahl
        * kundennr doppelt (die erste gewinnt, spätere sind Fehler)
        * email ohne genau ein "@" oder ohne Punkt nach dem "@"
        * falsche Spaltenanzahl
    - Komplett leere Zeilen werden ignoriert (kein Fehler).
    """
    raise NotImplementedError
