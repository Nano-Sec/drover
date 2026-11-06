from decimal import Decimal, ROUND_HALF_EVEN


class PricingError(Exception):
    pass


def round_half_even(value):
    """Return value as a whole number, ties going to the even neighbour."""
    return int(Decimal(str(value)).quantize(Decimal(1), rounding=ROUND_HALF_EVEN))
