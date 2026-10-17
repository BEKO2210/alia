def calc_total(prices, discount=0):
    total = sum(prices)
    return round(total * (1 - discount), 2)
