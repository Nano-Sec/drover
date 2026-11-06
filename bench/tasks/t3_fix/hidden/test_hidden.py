import unittest
from intervals import free_slots, merge


class Hidden(unittest.TestCase):
    def test_nested(self):
        self.assertEqual(merge([(1, 10), (2, 3)]), [(1, 10)])

    def test_touching(self):
        self.assertEqual(merge([(1, 3), (3, 5)]), [(1, 5)])

    def test_unsorted(self):
        self.assertEqual(merge([(5, 6), (1, 2)]), [(1, 2), (5, 6)])

    def test_input_unchanged(self):
        data = [(5, 6), (1, 2)]
        merge(data)
        self.assertEqual(data, [(5, 6), (1, 2)])

    def test_input_unchanged_via_free_slots(self):
        data = [(5, 6), (1, 2)]
        free_slots(data, 0, 10)
        self.assertEqual(data, [(5, 6), (1, 2)])

    def test_empty(self):
        self.assertEqual(merge([]), [])
        self.assertEqual(free_slots([], 1, 4), [(1, 4)])

    def test_starts_before_day(self):
        self.assertEqual(free_slots([(1, 9)], 8, 12), [(9, 12)])

    def test_booking_wholly_before_day(self):
        self.assertEqual(free_slots([(1, 2)], 8, 12), [(8, 12)])

    def test_booking_wholly_after_day(self):
        self.assertEqual(free_slots([(20, 22)], 8, 12), [(8, 12)])

    def test_reaches_past_day(self):
        self.assertEqual(free_slots([(10, 30)], 8, 12), [(8, 10)])

    def test_covers_day(self):
        self.assertEqual(free_slots([(1, 30)], 8, 12), [])

    def test_touching_leaves_no_gap(self):
        self.assertEqual(free_slots([(8, 10), (10, 12)], 8, 12), [])
