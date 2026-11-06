import unittest
from roman import from_roman, to_roman
from slug import slugify
from wrap import wrap


class Slug(unittest.TestCase):
    def test_example(self):
        self.assertEqual(slugify("  Hello, World!  "), "hello-world")

    def test_runs(self):
        self.assertEqual(slugify("a -- b__c"), "a-b-c")

    def test_empty(self):
        self.assertEqual(slugify("!!!"), "")

    def test_non_ascii(self):
        self.assertEqual(slugify("café au lait"), "caf-au-lait")


class Roman(unittest.TestCase):
    def test_examples(self):
        self.assertEqual(to_roman(1994), "MCMXCIV")
        self.assertEqual(to_roman(3999), "MMMCMXCIX")

    def test_round_trip(self):
        for n in range(1, 4000):
            self.assertEqual(from_roman(to_roman(n)), n)

    def test_range(self):
        for bad in (0, -1, 4000):
            with self.assertRaises(ValueError):
                to_roman(bad)

    def test_not_canonical(self):
        for bad in ("IIII", "IC", "", "VV", "ABC", "iv"):
            with self.assertRaises(ValueError):
                from_roman(bad)


class Wrap(unittest.TestCase):
    def test_greedy(self):
        self.assertEqual(wrap("aa bb cc dd", 5), ["aa bb", "cc dd"])

    def test_whitespace(self):
        self.assertEqual(wrap("  aa \n\t bb ", 10), ["aa bb"])

    def test_long_word(self):
        self.assertEqual(wrap("abcdefgh ij", 3), ["abc", "def", "gh", "ij"])

    def test_long_word_tail_joined(self):
        self.assertEqual(wrap("abcdefg h", 3), ["abc", "def", "g h"])

    def test_empty(self):
        self.assertEqual(wrap("", 5), [])

    def test_bad_width(self):
        with self.assertRaises(ValueError):
            wrap("a", 0)
