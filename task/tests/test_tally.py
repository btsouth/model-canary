import unittest

from tally import duration, money, ranges


class MoneyTest(unittest.TestCase):
    def test_even(self):
        self.assertEqual(money.split(90, [1, 1, 1]), [30, 30, 30])

    def test_thirds(self):
        self.assertEqual(money.split(100, [1, 1, 1]), [34, 33, 33])

    def test_format(self):
        self.assertEqual(money.format_cents(1234), "$12.34")


class RangesTest(unittest.TestCase):
    def test_overlap(self):
        self.assertEqual(ranges.merge([(1, 5), (3, 8)]), [(1, 8)])

    def test_touching(self):
        self.assertEqual(ranges.merge([(1, 3), (3, 6)]), [(1, 6)])

    def test_free(self):
        self.assertEqual(ranges.free_slots([(10, 12)], 9, 17), [(9, 10), (12, 17)])


class DurationTest(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(duration.parse("1h30m"), 5400)

    def test_rejects_junk(self):
        with self.assertRaises(ValueError):
            duration.parse("1h junk")

    def test_round_trip(self):
        self.assertEqual(duration.format_seconds(5400), "1h30m")


if __name__ == "__main__":
    unittest.main()
