import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "perf"))
import perf_profile as prof  # noqa: E402


class ProfileTest(unittest.TestCase):
    def test_summarise_median_p95_and_first(self):
        r = prof.summarise([5.0, 1.0, 3.0, 2.0, 4.0])
        self.assertEqual((r["runs"], r["first_s"], r["median_s"], r["p95_s"]), (5, 5.0, 3.0, 5.0))

    def test_slope_is_least_squares(self):
        self.assertAlmostEqual(prof.slope([(0, 1.0), (100, 2.0), (200, 3.0)]), 0.01)
        self.assertAlmostEqual(prof.slope([(0, 1.0), (10, 1.0)]), 0.0)
        with self.assertRaises(ValueError):
            prof.slope([(5, 1.0), (5, 2.0)])

    def test_load_is_net_of_the_baseline_and_never_negative(self):
        calls = []

        def fake(cmd, cwd):
            calls.append(Path(cmd[-1]).read_text().strip())
            return 2.0 if "Tengai" in calls[-1] else 0.5

        r = prof.load("Tengai", Path("."), 3, run=fake)
        self.assertEqual((r["module_median_s"], r["baseline_median_s"], r["net_median_s"]), (2.0, 0.5, 1.5))
        self.assertEqual(calls, ["import Tengai"] * 3 + ["import Init"] * 3)
        self.assertEqual(prof.load("Init", Path("."), 1, run=lambda c, d: 1.0)["net_median_s"], 0.0)

    def test_synthetic_library_has_n_modules_and_a_root_that_imports_them(self):
        with tempfile.TemporaryDirectory() as d:
            prof.write_library(Path(d), "Syn3", 3)
            self.assertEqual(sorted(p.name for p in (Path(d) / "Syn3").iterdir()), ["M0.lean", "M1.lean", "M2.lean"])
            self.assertEqual((Path(d) / "Syn3.lean").read_text().splitlines(), ["import Syn3.M0", "import Syn3.M1", "import Syn3.M2"])
            prof.write_library(Path(d), "Syn0", 0)
            self.assertNotIn("import", (Path(d) / "Syn0.lean").read_text())


if __name__ == "__main__":
    unittest.main()
