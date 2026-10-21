"""Graded after the run. The model never sees these. Each test is one point."""
import unittest

from tally import duration, money, ranges


class HiddenMoney(unittest.TestCase):
    def test_thirds(self):
        self.assertEqual(money.split(100, [1, 1, 1]), [34, 33, 33])

    def test_sum_exact(self):
        for total in (1, 7, 99, 1000, 12345):
            for w in ([1, 2, 3], [5, 5, 1], [0.3, 0.3, 0.4], [7]):
                self.assertEqual(sum(money.split(total, w)), total, (total, w))

    def test_largest_remainder(self):
        self.assertEqual(money.split(10, [1, 2, 3, 4]), [1, 2, 3, 4])
        self.assertEqual(money.split(5, [1, 1, 3]), [1, 1, 3])
        self.assertEqual(money.split(7, [2, 3]), [3, 4])

    def test_ties_go_first(self):
        self.assertEqual(money.split(2, [1, 1, 1]), [1, 1, 0])

    def test_zero_weight(self):
        self.assertEqual(money.split(10, [0, 1, 1]), [0, 5, 5])

    def test_negative(self):
        self.assertEqual(money.split(-100, [1, 1, 1]), [-34, -33, -33])

    def test_bad_weights(self):
        for w in ([], [0, 0], [1, -1]):
            with self.assertRaises(ValueError):
                money.split(10, w)


class HiddenRanges(unittest.TestCase):
    def test_touching(self):
        self.assertEqual(ranges.merge([(1, 3), (3, 6)]), [(1, 6)])

    def test_unsorted(self):
        self.assertEqual(ranges.merge([(8, 9), (1, 3), (2, 4)]), [(1, 4), (8, 9)])

    def test_contained_and_empty(self):
        self.assertEqual(ranges.merge([(5, 5), (1, 10), (2, 3)]), [(1, 10)])

    def test_free_unsorted_overhang(self):
        self.assertEqual(ranges.free_slots([(16, 20), (7, 10), (12, 13)], 9, 17),
                         [(10, 12), (13, 16)])

    def test_free_min_length(self):
        self.assertEqual(ranges.free_slots([(10, 11), (12, 15)], 9, 16, min_length=2),
                         [])


class HiddenDuration(unittest.TestCase):
    def test_parts(self):
        self.assertEqual(duration.parse("2d 4h"), 2 * 86400 + 4 * 3600)
        self.assertEqual(duration.parse(" 45s "), 45)

    def test_case(self):
        self.assertEqual(duration.parse("1H 5M"), 3900)

    def test_rejects(self):
        for bad in ("", "  ", "1h junk", "junk1h", "1x", "30m1h", "1h1h", "h", "1.5h", "1h-2m"):
            with self.assertRaises(ValueError, msg=bad):
                duration.parse(bad)

    def test_round_trip(self):
        for s in (0, 1, 59, 60, 3600, 5400, 86400, 90061):
            self.assertEqual(duration.parse(duration.format_seconds(s)), s)


class HiddenUntouched(unittest.TestCase):
    def test_format_cents(self):
        self.assertEqual(money.format_cents(-5), "-$0.05")
        self.assertEqual(money.format_cents(100000), "$1000.00")


if __name__ == "__main__":
    unittest.main()
