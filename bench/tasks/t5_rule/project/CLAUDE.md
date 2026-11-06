# Pricing service

Project rules. These apply to every change.

- Round money only with `round_half_even` from `money.py`. Never use the built-in `round`.
- Invalid input raises `PricingError` from `money.py`, never `ValueError`.
- Every function in `pricing.py` has a docstring whose last line is `Owner: billing`.
- Every change adds one line, starting `- `, under `## Unreleased` in `CHANGES.md`, naming the function changed.
