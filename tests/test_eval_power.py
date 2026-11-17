import random
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
import power  # noqa: E402


class Power(unittest.TestCase):
    def test_known_values(self):
        self.assertEqual(power.n_superiority(0.03, 0.20), 2331)
        self.assertEqual(power.n_noninferiority(0.02, 0.20), 4282)
        self.assertGreater(power.n_superiority(0.02, 0.20), power.n_superiority(0.03, 0.20))
        with self.assertRaises(ValueError):
            power.n_superiority(0.3, 0.2)  # a gain cannot exceed the discordant fraction
        with self.assertRaises(ValueError):
            power.n_noninferiority(0.5, 0.2)

    def test_mcnemar_exact(self):
        self.assertEqual(power.mcnemar_exact(5, 5), 1.0)
        self.assertEqual(power.mcnemar_exact(0, 0), 1.0)
        self.assertAlmostEqual(power.mcnemar_exact(0, 8), 2 / 256)
        self.assertAlmostEqual(power.mcnemar_exact(30, 10), 0.00222143, places=7)
        self.assertEqual(power.mcnemar_exact(3, 9), power.mcnemar_exact(9, 3))

    def test_the_formula_reaches_its_power_in_simulation(self):
        # delta 0.05, psi 0.20: 837 problems; simulate the paired experiment and test with the exact test
        n, p10, p01 = power.n_superiority(0.05, 0.20), 0.125, 0.075
        rng, hits, sims = random.Random(20261116), 0, 300
        for _ in range(sims):
            b = c = 0
            for _ in range(n):
                u = rng.random()
                b += u < p10
                c += p10 <= u < p10 + p01
            hits += power.mcnemar_exact(b, c) < 0.05
        self.assertGreaterEqual(hits / sims, 0.85)  # nominal 0.90; the normal approximation is slightly off at this size

    def test_the_protocol_prints_the_table_this_file_computes(self):
        self.assertIn(power.table(), (ROOT / "eval" / "protocol.md").read_text(encoding="utf-8"))

    def test_the_protocol_prints_the_resolvable_table(self):
        self.assertIn(power.resolvable_table(), (ROOT / "eval" / "protocol.md").read_text(encoding="utf-8"))

    def test_resolvable_is_the_inverse_of_the_sample_size(self):
        for psi in power.PSIS:
            for n in power.SIZES:
                g = power.min_gain(n, psi)
                if g is not None:
                    self.assertLessEqual(power.n_superiority(g, psi), n, (n, psi))
                    # a gain one step (0.001) finer is NOT detectable
                    if g - 0.001 > 0:
                        self.assertGreater(power.n_superiority(g - 0.001, psi), n, (n, psi))
                m = power.min_margin(n, psi)
                self.assertLessEqual(power.n_noninferiority(m, psi), n)
                if m - 0.001 > 0:
                    self.assertGreater(power.n_noninferiority(m - 0.001, psi), n)

    def test_more_problems_resolve_finer_effects(self):
        for psi in power.PSIS:
            gains = [power.min_gain(n, psi) for n in power.SIZES]
            margins = [power.min_margin(n, psi) for n in power.SIZES]
            self.assertEqual(gains, sorted(gains, reverse=True))
            self.assertEqual(margins, sorted(margins, reverse=True))

    def test_the_cli(self):
        out = subprocess.run(
            [sys.executable, str(ROOT / "eval" / "power.py"), "n", "--delta", "0.03", "--psi", "0.2"],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(out.stdout.strip(), "2331")


if __name__ == "__main__":
    unittest.main()
