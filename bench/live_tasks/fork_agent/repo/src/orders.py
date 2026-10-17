from dataclasses import dataclass, field


@dataclass
class Line:
    sku: str
    qty: int
    unit_cents: int


@dataclass
class Order:
    lines: list[Line] = field(default_factory=list)

    def add(self, sku: str, qty: int, unit_cents: int) -> None:
        self.lines.append(Line(sku, qty, unit_cents))

    def subtotal(self) -> int:
        return sum(line.qty * line.unit_cents for line in self.lines)
