import itertools
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "campaign"))
import secondary as S  # noqa: E402


def brute(diffs):
    """P(W+ <= obs) and P(W+ >= obs) by enumerating every sign pattern of the mid-ranks (the definition the DP must equal)"""
    nz = [d for d in diffs if d != 0]
    order = sorted(abs(d) for d in nz)
    rank = {v: (order.index(v) + 1 + len(order) - order[::-1].index(v)) / 2 for v in set(order)}
    obs = sum(rank[abs(d)] for d in nz if d > 0)
    sums = [
        sum(r for r, keep in zip((rank[abs(d)] for d in nz), signs, strict=True) if keep)
        for signs in itertools.product([0, 1], repeat=len(nz))
    ]
    return (
        sum(1 for x in sums if x <= obs + 1e-9) / len(sums),
        sum(1 for x in sums if x >= obs - 1e-9) / len(sums),
    )


class SignedRank(unittest.TestCase):
    def test_exact_distribution_equals_enumeration_with_ties_and_zeros(self):
        for diffs in ([1, 2, 3], [-1, 2, 3, -4], [1, 1, -2, 3, 3, 3], [0, 0.5, -0.5, 2, 2], [-1, -2, -3, -4, 5], [1, -1, 2, -2, 3]):
            r = S.signed_rank(diffs)
            lo, up = brute(diffs)
            self.assertAlmostEqual(r["p_lower"], lo, msg=str(diffs))
            self.assertAlmostEqual(r["p_upper"], up, msg=str(diffs))

    def test_all_positive_is_the_smallest_upper_tail(self):
        r = S.signed_rank([1, 2, 3, 4, 5])
        self.assertAlmostEqual(r["p_upper"], 1 / 32)
        self.assertAlmostEqual(r["p_two"], 1 / 16)

    def test_no_difference_is_not_significant(self):
        self.assertEqual(S.signed_rank([0, 0, 0])["p_two"], 1.0)
        self.assertEqual(S.signed_rank([])["p_two"], 1.0)

    def test_normal_approximation_agrees_with_the_exact_test_near_the_switch(self):
        diffs = [(-1) ** i * (i + 1) * 0.37 for i in range(21)]  # 21 pairs: approximation
        approx = S.signed_rank(diffs)
        S.EXACT_MAX_N, saved = 30, S.EXACT_MAX_N
        try:
            exact = S.signed_rank(diffs)
        finally:
            S.EXACT_MAX_N = saved
        self.assertLess(abs(approx["p_two"] - exact["p_two"]), 0.05)


class Axis(unittest.TestCase):
    base = {f"t{i}": 100.0 + i for i in range(30)}

    def test_halving_the_cost_is_significantly_better_and_non_inferior(self):
        hyp = {t: c * 0.5 for t, c in self.base.items()}
        a = S.axis(self.base, hyp, 0.1)
        self.assertTrue(a["better"] and a["noninferior"])
        self.assertAlmostEqual(a["median_ratio"], 0.5)

    def test_doubling_the_cost_is_not_non_inferior_within_ten_percent(self):
        hyp = {t: c * 2 for t, c in self.base.items()}
        a = S.axis(self.base, hyp, 0.1)
        self.assertFalse(a["better"] or a["noninferior"])

    def test_five_percent_more_is_non_inferior_within_ten_percent_but_not_better(self):
        hyp = {t: c * 1.05 for t, c in self.base.items()}
        a = S.axis(self.base, hyp, 0.1)
        self.assertTrue(a["noninferior"])
        self.assertFalse(a["better"])

    def test_only_problems_solved_by_both_count_and_none_means_nothing_is_shown(self):
        hyp = {"t0": 1.0, "zz": 5.0}
        self.assertEqual(S.axis(self.base, hyp, 0.1)["n_pairs"], 1)
        none = S.axis(self.base, {"zz": 1.0}, 0.1)
        self.assertEqual(none["n_pairs"], 0)
        self.assertFalse(none["better"] or none["noninferior"])
        self.assertTrue(math.isfinite(S.axis(self.base, self.base, 0.1)["noninferior_p"]))


if __name__ == "__main__":
    unittest.main()
