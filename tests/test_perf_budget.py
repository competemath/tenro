import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "perf"))
import check_budget as cb  # noqa: E402

B = {"load": {"cap_net_median_s": 0.25}, "scale": {"cap_ms_per_module": 0.3}}


class BudgetTest(unittest.TestCase):
    def test_the_committed_budget_parses_and_has_every_cap(self):
        b = cb.read_toml(Path(__file__).resolve().parents[1] / "perf-budget.toml")
        for table, key in cb.CAPS:
            self.assertGreater(b[table][key], 0)

    def test_check(self):
        self.assertEqual(cb.check(B, {"net_median_s": 0.1}, {"ms_per_module": 0.1}), [])
        self.assertEqual(cb.check(B, {"net_median_s": 0.25}, {"ms_per_module": 0.3}), [])  # at the cap is within it
        self.assertEqual(len(cb.check(B, {"net_median_s": 0.3}, {"ms_per_module": 0.1})), 1)
        self.assertEqual(len(cb.check(B, {"net_median_s": 0.3}, {"ms_per_module": 0.4})), 2)

    def test_ratchet_only_lowers(self):
        lower = {"load": {"cap_net_median_s": 0.1}, "scale": {"cap_ms_per_module": 0.3}}
        higher = {"load": {"cap_net_median_s": 0.5}, "scale": {"cap_ms_per_module": 0.3}}
        self.assertEqual(cb.ratchet(lower, B), [])
        self.assertEqual(cb.ratchet(B, B), [])
        self.assertEqual(len(cb.ratchet(higher, B)), 1)
        self.assertEqual(cb.ratchet(higher, {}), [])  # no base budget yet: nothing to compare with


if __name__ == "__main__":
    unittest.main()
