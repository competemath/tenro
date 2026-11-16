import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "harness"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "readiness"))
import gather as G  # noqa: E402
import records as R  # noqa: E402
import report as RP  # noqa: E402

H = "a" * 64


def run(task="p1", arm="tengai", outcome="solved", model="m", cap=30, budget=16, **over):
    r = {
        "key": {"core_tree": "b" * 40, "hypothesis": "baseline", "harness": H, "model": model, "seed": 1, "split": H},
        "task": {"id": task, "stratum": "post-cutoff"},
        "arm": {"name": arm, "turn_cap": cap, "sample_budget": budget},
        "outcome": outcome,
        "checks": {"tamper": "pass", "kernel": "pass", "axioms": "pass"},
    }
    r.update(over)
    return r


class Records(unittest.TestCase):
    def test_a_complete_run_passes(self):
        self.assertEqual(
            R.validate([run(), run(task="p2", outcome="unsolved", checks={"tamper": "pass", "kernel": "n/a", "axioms": "n/a"})]), []
        )

    def test_each_defect_is_named(self):
        bad = run(outcome="solved", checks={"tamper": "fail", "kernel": "pass", "axioms": "pass"})
        text = "\n".join(R.validate([bad]))
        self.assertIn("solved run needs", text)
        self.assertIn("tamper check is not solved", text)
        self.assertIn("key.core_tree", "\n".join(R.validate([run(key={**run()["key"], "core_tree": "xyz"})])))
        self.assertIn("exactly", "\n".join(R.validate([run(key={"core_tree": "b" * 40})])))
        weird = run()
        weird["task"] = {"id": "p", "stratum": "weird"}
        self.assertIn("stratum", "\n".join(R.validate([weird])))
        self.assertIn("twice", "\n".join(R.validate([run(), run()])))
        self.assertIn("outcome", "\n".join(R.validate([run(outcome="maybe")])))

    def test_summary_counts_infra_errors_and_two_sided_validity(self):
        runs = [run(task="p1"), run(task="p2", outcome="infra_error", checks={}), run(task="p3", outcome="unsolved", checks={})]
        validity = [
            {"task": "p1", "accepts_reference": True, "rejects_mutant": True},
            {"task": "p2", "accepts_reference": True, "rejects_mutant": False},
        ]  # p3 has no validity record
        s = R.summarise(runs, validity)
        self.assertEqual(s["harness"], {"runs": 3, "infra_errors": 1})
        self.assertEqual(s["validity"], {"tasks": 3, "two_sided_valid": 1})

    def test_parity_reports_arms_that_differ(self):
        runs = [run(arm="tengai"), run(arm="mathlib", task="p2", cap=50)]
        s = R.summarise(runs)
        self.assertEqual(s["parity"]["differing_from_the_first"], ["mathlib"])
        self.assertEqual(R.summarise([run(arm="a"), run(arm="b", task="p2")])["parity"]["differing_from_the_first"], [])

    def test_the_files_feed_the_readiness_report(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "runs.jsonl").write_text("".join(json.dumps(r) + "\n" for r in [run(task=f"p{i}") for i in range(100)]))
            (d / "task-validity.jsonl").write_text(
                "".join(json.dumps({"task": f"p{i}", "accepts_reference": True, "rejects_mutant": True}) + "\n" for i in range(100))
            )
            self.assertEqual(R.main(["validate", str(d / "runs.jsonl")]), 0)
            self.assertEqual(R.main(["summarise", str(d / "runs.jsonl"), "--out", str(d / "m")]), 0)
            rep = RP.report(G.gather(d / "m"))
            crit = {c["criterion"]: c["status"] for c in rep["gates"][3]["criteria"]}
            self.assertEqual(crit["harness infrastructure error rate"], "pass")
            self.assertEqual(crit["two-sided validity across eval tasks"], "pass")
            self.assertEqual(R.main([]), 2)


if __name__ == "__main__":
    unittest.main()
