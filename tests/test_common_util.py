"""tools/common/util.py: the one definition of set overlap and of reading JSON lines."""

import itertools
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "common"))
import util  # noqa: E402


class Sets(unittest.TestCase):
    def test_values(self):
        self.assertEqual(util.jaccard({"a", "b"}, {"b", "c"}), 1 / 3)
        self.assertEqual(util.jaccard({"a"}, {"a"}), 1.0)
        self.assertEqual(util.jaccard({"a"}, {"b"}), 0.0)

    def test_two_empty_sets_are_identical(self):
        self.assertEqual(util.jaccard([], []), 1.0)
        self.assertEqual(util.distance([], []), 0.0)

    def test_one_empty_set_shares_nothing(self):
        self.assertEqual(util.jaccard([], ["a"]), 0.0)
        self.assertEqual(util.distance(["a"], []), 1.0)

    def test_a_list_with_repeats_is_a_set(self):
        self.assertEqual(util.jaccard(["a", "a", "b"], ["b", "b"]), 0.5)

    def test_it_is_a_distance_on_small_universes(self):
        """symmetric, zero exactly on equal sets, and the triangle inequality (checked on every triple of subsets of a 4-element universe; Jaccard distance is a metric)"""
        universe = "abcd"
        subsets = [frozenset(c) for r in range(5) for c in itertools.combinations(universe, r)]
        for a, b in itertools.product(subsets, repeat=2):
            self.assertEqual(util.distance(a, b), util.distance(b, a))
            self.assertEqual(util.distance(a, b) == 0, a == b)
        for a, b, c in itertools.product(subsets, repeat=3):
            self.assertLessEqual(util.distance(a, c), util.distance(a, b) + util.distance(b, c) + 1e-12)


class Jsonl(unittest.TestCase):
    def test_blank_lines_are_skipped_and_unicode_kept(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.jsonl"
            p.write_text('{"a": 1}\n\n  \n{"b": "é"}\n', encoding="utf-8")
            self.assertEqual(util.read_jsonl(p), [{"a": 1}, {"b": "é"}])
            self.assertEqual(util.read_jsonl(str(p)), [{"a": 1}, {"b": "é"}])

    def test_a_malformed_line_is_an_error_not_a_skip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.jsonl"
            p.write_text('{"a": 1}\n{oops\n', encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):
                util.read_jsonl(p)


if __name__ == "__main__":
    unittest.main()
