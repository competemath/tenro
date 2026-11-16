import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "harness"))
import tamper as T  # noqa: E402


class Tamper(unittest.TestCase):
    def test_every_mutant_is_detected_and_no_legitimate_proof_is_refused(self):
        r = T.selftest()
        self.assertEqual(r["undetected_names"], [])
        self.assertEqual(r["false_alarms"], 0)
        self.assertGreaterEqual(r["cases"], 20)

    def test_each_mutant_individually(self):
        for name, text in T.MUTANTS.items():
            self.assertTrue(T.check(T.ORIGINAL, text), name)

    def test_each_legitimate_proof_individually(self):
        for i, proof in enumerate(T.LEGITIMATE):
            self.assertEqual(T.check(T.ORIGINAL, T.ORIGINAL + proof), [], i)

    def test_the_first_differing_byte_is_named(self):
        bad = T.ORIGINAL.replace("0 < n", "1 < n") + "\n omega\n"
        msg = T.check(T.ORIGINAL, bad)[0]
        self.assertIn("first difference at byte", msg)

    def test_the_original_must_have_one_sentinel(self):
        self.assertEqual(T.check("no sentinel here", "x"), ["the original has no single sentinel line"])
        self.assertEqual(len(T.check(T.ORIGINAL + "\n" + T.SENTINEL, "x")), 1)

    def test_cli(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "o.lean").write_text(T.ORIGINAL, newline="")
            (d / "ok.lean").write_text(T.ORIGINAL + T.LEGITIMATE[0], newline="")
            (d / "bad.lean").write_text(T.ORIGINAL + "\n  sorry\n", newline="")
            self.assertEqual(T.main(["check", str(d / "o.lean"), str(d / "ok.lean")]), 0)
            self.assertEqual(T.main(["check", str(d / "o.lean"), str(d / "bad.lean")]), 1)
            self.assertEqual(T.main(["selftest", "--out", str(d / "t.json")]), 0)
            self.assertIn('"undetected": 0', (d / "t.json").read_text())
            self.assertEqual(T.main([]), 2)


if __name__ == "__main__":
    unittest.main()
