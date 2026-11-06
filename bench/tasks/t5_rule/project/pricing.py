from money import PricingError, round_half_even


def add_tax(price_cents, rate):
    """Return the price in cents with tax at rate added.
    Owner: billing"""
    if rate < 0:
        raise PricingError("rate must not be negative")
    return round_half_even(price_cents * (1 + rate))
