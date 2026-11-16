import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "readiness"))
import report as R  # noqa: E402

GOOD = {
    "soundness": {"passed": True},
    "data": {"lemmas": 300, "definitions": 100, "structural_duplicates": 0, "statements": 400},
    "load": {"net_median_s": 0.05}, "scale": {"ms_per_module": 0.1},
    "budget": {"load": {"cap_net_median_s": 0.25}, "scale": {"cap_ms_per_module": 0.3}},
    "mathlib_load_net_median_s": 2.0,
    "retrieval": {"recall_at_10": 0.9, "n": 500},
    "obfuscation": {"pass_rate_plain": 0.40, "pass_rate_scrambled": 0.37, "n": 500},
    "migration": {"denominator": 1000, "accepted": 990, "rate": 0.99, "rejected": []},
    "migration_integrity_violations": 0,
    "tamper": {"cases": 50, "undetected": 0},
    "harness": {"runs": 1000, "infra_errors": 3},
    "validity": {"tasks": 200, "two_sided_valid": 200},
    "campaign": {"strata": ["post-cutoff", "dependency-ablation", "cross-domain"], "arms": {"tengai": {"model": "m", "turn_cap": 30, "sample_budget": 16}, "mathlib": {"model": "m", "turn_cap": 30, "sample_budget": 16}}},
}  # fmt: skip


def statuses(rep):
    return {g["gate"]: g["status"] for g in rep["gates"]}


class Report(unittest.TestCase):
    def test_everything_measured_and_passing_opens_the_ab(self):
        rep = R.report(GOOD)
        self.assertEqual(statuses(rep), {k: "pass" for k in "12345"})
        self.assertTrue(rep["ab_allowed"])

    def test_nothing_measured_keeps_every_gate_open(self):
        rep = R.report({})
        self.assertEqual(statuses(rep), {k: "open" for k in "12345"})
        self.assertFalse(rep["ab_allowed"])

    def test_one_unmeasured_criterion_keeps_its_gate_open_not_passed(self):
        inputs = {**GOOD}
        del inputs["tamper"]
        rep = R.report(inputs)
        self.assertEqual(statuses(rep)["4"], "open")
        self.assertFalse(rep["ab_allowed"])

    def test_each_threshold_fails_at_its_boundary(self):
        cases = {
            "1": {**GOOD, "data": {**GOOD["data"], "lemmas": 401}},  # ratio 4.01
            "1b": {**GOOD, "data": {**GOOD["data"], "structural_duplicates": 1}},
            "1c": {**GOOD, "load": {"net_median_s": 0.3}},
            "2": {**GOOD, "retrieval": {"recall_at_10": 0.84, "n": 500}},
            "2b": {**GOOD, "obfuscation": {"pass_rate_plain": 0.40, "pass_rate_scrambled": 0.35, "n": 500}},  # a drop of 0.05 is not below 0.05
            "3": {**GOOD, "migration": {"denominator": 1000, "accepted": 979, "rate": 0.979, "rejected": []}},
            "3b": {**GOOD, "migration_integrity_violations": 1},
            "4": {**GOOD, "tamper": {"cases": 50, "undetected": 1}},
            "4b": {**GOOD, "harness": {"runs": 100, "infra_errors": 1}},  # exactly 1% is not below 1%
            "4c": {**GOOD, "validity": {"tasks": 200, "two_sided_valid": 199}},
            "5": {**GOOD, "campaign": {**GOOD["campaign"], "strata": ["post-cutoff"]}},
            "5b": {**GOOD, "campaign": {**GOOD["campaign"], "arms": {"tengai": {"model": "m", "turn_cap": 30, "sample_budget": 16}, "mathlib": {"model": "m", "turn_cap": 50, "sample_budget": 16}}}},
        }  # fmt: skip
        for name, inputs in cases.items():
            rep = R.report(inputs)
            self.assertEqual(statuses(rep)[name[0]], "fail", name)
            self.assertFalse(rep["ab_allowed"], name)

    def test_the_mathlib_ratio_is_context_not_a_criterion(self):
        rep = R.report({**GOOD, "mathlib_load_net_median_s": 0.01})  # Mathlib faster: still within the absolute caps
        self.assertEqual(statuses(rep)["1"], "pass")
        crit = rep["gates"][0]["criteria"][-1]
        self.assertIn("context", crit["note"])

    def test_markdown_and_cli_exit_status(self):
        self.assertIn("NOT allowed", R.markdown(R.report({})))
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "in.json"
            f.write_text(json.dumps(GOOD))
            self.assertEqual(R.main([str(f)]), 0)
            f.write_text("{}")
            self.assertEqual(R.main([str(f), "--markdown"]), 1)
            self.assertEqual(R.main([]), 2)


class Gather(unittest.TestCase):
    def test_known_files_become_keys_and_missing_ones_stay_missing(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "readiness"))
        import gather as G

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "load.json").write_text(json.dumps({"net_median_s": 0.01}))
            (d / "scale.json").write_text(json.dumps({"ms_per_module": 0.02}))
            (d / "lens-report.json").write_text(
                json.dumps({"denominator": 10, "accepted": 10, "rate": 1.0, "rejected": [], "integrity_violations": 0})
            )
            (d / "mathlib-load.json").write_text(json.dumps({"net_median_s": 3.0}))
            (d / "budget.toml").write_text("[load]\ncap_net_median_s = 0.25\n[scale]\ncap_ms_per_module = 0.3\n")
            got = G.gather(d, d / "budget.toml")
            self.assertEqual(
                sorted(got), ["budget", "load", "mathlib_load_net_median_s", "migration", "migration_integrity_violations", "scale"]
            )
            self.assertEqual(got["migration_integrity_violations"], 0)
            self.assertNotIn("tamper", got)
            rep = R.report(got)
            self.assertEqual(statuses(rep)["1"], "open")  # the soundness verdict and data stats are not there
            self.assertEqual(statuses(rep)["3"], "pass")
            self.assertEqual(G.main([str(d)]), 0)
            self.assertEqual(G.main([]), 2)


if __name__ == "__main__":
    unittest.main()
