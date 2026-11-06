import unittest
from intervals import free_slots


class FreeSlots(unittest.TestCase):
    def test_nested_booking(self):
        self.assertEqual(free_slots([(9, 17), (10, 11)], 8, 18), [(8, 9), (17, 18)])


if __name__ == "__main__":
    unittest.main()
