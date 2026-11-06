import unittest
from money import PricingError
from pricing import apply_discount


class Discount(unittest.TestCase):
    def test_core(self):
        self.assertEqual(apply_discount(1000, 25), 750)
        self.assertEqual(apply_discount(1000, 0), 1000)
        self.assertEqual(apply_discount(1000, 100), 0)
