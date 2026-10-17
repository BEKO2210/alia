from .pricing import compute_total


class Cart:
    def __init__(self):
        self.prices = []

    def add(self, price):
        self.prices.append(price)

    def total(self, discount=0):
        return compute_total(self.prices, discount)
