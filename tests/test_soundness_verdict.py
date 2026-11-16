import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "soundness"))
import verdict as v  # noqa: E402

SCOPE = ("Tengai.", "Tenro.")


class AxiomsTest(unittest.TestCase):
    def test_a_passing_report_with_no_banned_user_passes(self):
        self.assertEqual(v.check_axioms({"passed": True, "resting_on_other_axioms": {}}, SCOPE)["status"], "pass")

    def test_a_failed_report_fails_and_says_why(self):
        r = v.check_axioms({"passed": False, "failures": ["the export declares the axiom foo"]}, SCOPE)
        self.assertEqual(r["status"], "fail")
        self.assertIn("foo", r["details"][0])

    def test_ofReduceBool_in_scope_fails_outside_scope_does_not(self):
        rep = {"passed": True, "resting_on_other_axioms": {"Lean.ofReduceBool": ["Tengai.Gauss.sum", "Mathlib.X.y"]}}
        self.assertEqual(v.check_axioms(rep, SCOPE)["status"], "fail")
        rep = {"passed": True, "resting_on_other_axioms": {"Lean.ofReduceBool": ["Mathlib.X.y"]}}
        self.assertEqual(v.check_axioms(rep, SCOPE)["status"], "pass")

    def test_sorry_in_scope_fails_even_if_the_report_passed(self):
        rep = {"passed": True, "resting_on_other_axioms": {"sorryAx": ["Tenro.A.t"]}}
        self.assertEqual(v.check_axioms(rep, SCOPE)["status"], "fail")


class OtherChecksTest(unittest.TestCase):
    def test_vacuity_needs_an_acknowledgement_per_theorem(self):
        text = "VACUOUS A.t Mod omega\n  hyps\nVACUOUS B.u Mod simp_all\nsummary"
        self.assertEqual(v.check_vacuity(text, {"A.t", "B.u"})["status"], "pass")
        r = v.check_vacuity(text, {"A.t"})
        self.assertEqual((r["status"], len(r["details"])), ("fail", 1))
        self.assertEqual(v.check_vacuity("summary: none", set())["status"], "pass")

    def test_probe_findings(self):
        self.assertEqual(v.check_findings({"findings": []})["status"], "pass")
        self.assertEqual(v.check_findings({"findings": ["A.t holds without hypothesis h"]})["status"], "fail")
        self.assertEqual(v.check_findings({"nothing": 1})["status"], "fail")


class DecideTest(unittest.TestCase):
    PASS = {"status": "pass", "details": []}

    def test_a_missing_required_check_fails_the_verdict(self):
        out = v.decide({"axioms": self.PASS}, ("axioms", "vacuity"))
        self.assertFalse(out["passed"])
        self.assertEqual(out["checks"]["vacuity"]["status"], "missing")

    def test_all_required_present_and_passing(self):
        out = v.decide({"axioms": self.PASS, "vacuity": self.PASS}, ("axioms", "vacuity"))
        self.assertTrue(out["passed"])

    def test_an_extra_failing_check_fails_even_if_not_required(self):
        out = v.decide({"axioms": self.PASS, "extra": {"status": "fail", "details": ["x"]}}, ("axioms",))
        self.assertFalse(out["passed"])

    def test_main_exit_status_follows_the_verdict(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "axioms.json"
            f.write_text(json.dumps({"passed": True}))
            self.assertEqual(v.main(["--axiom-report", str(f), "--require", "axioms"]), 0)
            self.assertEqual(v.main(["--axiom-report", str(f)]), 1)  # the default requirements are not all there


if __name__ == "__main__":
    unittest.main()
