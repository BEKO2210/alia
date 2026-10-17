import warnings


def compute_total(prices, discount=0):
    total = sum(prices)
    return round(total * (1 - discount), 2)


def calc_total(prices, discount=0):
    warnings.warn("calc_total is deprecated, use compute_total", DeprecationWarning, stacklevel=2)
    return compute_total(prices, discount)
