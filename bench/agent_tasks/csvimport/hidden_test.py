import os, tempfile, unittest
from decimal import Decimal
from customers import import_customers

CSV = (
    "\ufeffkundennr;name;email;umsatz\n"
    "1; Anna Muster ;anna@example.de;1.234,50\n"
    "\n"
    "2;Bernd;bernd(at)example.de;10,00\n"
    "1;Doppelt;d@example.de;5\n"
    "x;Text;t@example.de;1\n"
    "3;Carla;carla@example.com;\n"
    "4;Zu;viele;spalten;hier\n"
    "-5;Neg;n@example.de;1\n"
    "6;Dora;dora@localhost;1\n"
)


class Hidden(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(CSV)

    def test_rows(self):
        kunden, fehler = import_customers(self.path)
        self.assertEqual([k["kundennr"] for k in kunden], [1, 3])
        self.assertEqual(kunden[0], {"kundennr": 1, "name": "Anna Muster", "email": "anna@example.de", "umsatz": Decimal("1234.50")})
        self.assertEqual(kunden[1]["umsatz"], Decimal("0"))

    def test_errors(self):
        _, fehler = import_customers(self.path)
        self.assertEqual([f.split(":")[0] for f in fehler],
                         ["Zeile 4", "Zeile 5", "Zeile 6", "Zeile 8", "Zeile 9", "Zeile 10"])
