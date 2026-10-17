from .pricing import calc_total


class Cart:
    def __init__(self):
        self.prices = []

    def add(self, price):
        self.prices.append(price)

    def total(self, discount=0):
        return calc_total(self.prices, discount)
