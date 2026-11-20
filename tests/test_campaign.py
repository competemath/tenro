import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "campaign"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "readiness"))
import campaign as C  # noqa: E402
import report as RP  # noqa: E402

H = "a" * 64
ARM = {"model": "m", "turn_cap": 30, "sample_budget": 16}


def spec(n=4, **over):
    s = {
        "id": "c1",
        "protocol": H,
        "split": H,
        "n": n,
        "strata": ["post-cutoff", "dependency-ablation", "cross-domain"],
        "psi": 0.2,
        "baseline": "base",
        "hypothesis": "hyp",
        "arms": {"base": dict(ARM), "hyp": dict(ARM)},
        "primary": {"kind": "superiority", "expected_gain": 0.05},
        "secondary": {"tokens": {"margin": 0.1}, "wall_s": {"margin": 0.1}},
    }
    s.update(over)
    return s


def run(task, arm, outcome, seed=1, model="m", split=H, cost=1.0):
    r = {
        "key": {
            "core_tree": "b" * 40,
            "hypothesis": "baseline" if arm == "base" else "h",
            "harness": H,
            "model": model,
            "seed": seed,
            "split": split,
        },
        "task": {"id": task, "stratum": "post-cutoff"},
        "arm": {"name": arm, "turn_cap": 30, "sample_budget": 16},
        "outcome": outcome,
        "checks": {
            "tamper": "pass",
            "kernel": "pass" if outcome == "solved" else "n/a",
            "axioms": "pass" if outcome == "solved" else "n/a",
        },
    }
    if outcome == "solved" and cost is not None:
        r["cost"] = {"tokens": 1000 * cost, "wall_s": 60 * cost}
    return r


def paired(b, c, both, neither, hyp_cost=1.0):
    """runs where the hypothesis alone solves b problems, the baseline alone c, both `both`, neither `neither`"""
    out, i = [], 0
    for kind, count in (("b", b), ("c", c), ("both", both), ("neither", neither)):
        for _ in range(count):
            i += 1
            t = f"p{i}"
            base = "solved" if kind in ("c", "both") else "unsolved"
            hyp = "solved" if kind in ("b", "both") else "unsolved"
            out += [run(t, "base", base, cost=1 + 0.01 * i), run(t, "hyp", hyp, cost=hyp_cost * (1 + 0.01 * i))]
    return out


class Register(unittest.TestCase):
    def test_a_complete_registration_passes(self):
        self.assertEqual(C.check_spec(spec(), H), [])

    def test_a_stale_protocol_hash_is_refused(self):
        self.assertTrue(any("stale" in p for p in C.check_spec(spec(), "c" * 64)))

    def test_arms_must_agree_on_model_turn_cap_and_budget(self):
        s = spec()
        s["arms"]["hyp"]["turn_cap"] = 31
        self.assertTrue(any("same model" in p for p in C.check_spec(s)))

    def test_all_three_strata_are_required(self):
        self.assertTrue(any("strata" in p for p in C.check_spec(spec(strata=["post-cutoff", "cross-domain"]))))

    def test_baseline_and_hypothesis_must_differ_and_exist(self):
        self.assertTrue(any("different" in p for p in C.check_spec(spec(hypothesis="base"))))
        self.assertTrue(any("not in arms" in p for p in C.check_spec(spec(hypothesis="nope"))))

    def test_a_claim_without_a_size_is_refused(self):
        self.assertTrue(any("primary" in p for p in C.check_spec(spec(primary={"kind": "superiority"}))))
        self.assertTrue(any("primary" in p for p in C.check_spec(spec(primary={"kind": "superiority", "expected_gain": 0.5}))))

    def test_underpowered_is_declared_from_the_size_table(self):
        need = C.needed_n(spec())
        self.assertEqual(need, 837)  # eval/protocol.md: psi 0.20, gain 0.05
        self.assertTrue(C.power_status(spec(n=836))["underpowered"])
        self.assertFalse(C.power_status(spec(n=837))["underpowered"])

    def test_the_readiness_input_is_what_gate5_reads(self):
        ci = C.readiness_input(spec())
        rep = RP.gate5(ci and {"campaign": ci})
        self.assertTrue(all(c["status"] == "pass" for c in rep[:2]), rep)

    def test_split_hash_ignores_order_blanks_and_duplicates(self):
        self.assertEqual(C.split_hash(["b", "a", "", "a "]), C.split_hash(["a", "b"]))
        self.assertNotEqual(C.split_hash(["a", "b"]), C.split_hash(["a", "c"]))


class Analyse(unittest.TestCase):
    def test_discordant_pairs_are_counted_the_right_way_round(self):
        r = C.analyse(spec(n=40, primary={"kind": "superiority", "expected_gain": 0.1}), paired(b=10, c=1, both=9, neither=20))
        self.assertEqual((r["b"], r["c"], r["n_paired"]), (10, 1, 40))
        self.assertAlmostEqual(r["D"], 9 / 40)
        self.assertEqual(r["verdict"], "superior")
        self.assertTrue(r["underpowered"] and not r["promotable"])

    def test_a_hypothesis_that_loses_is_not_demonstrated(self):
        r = C.analyse(spec(n=40, primary={"kind": "superiority", "expected_gain": 0.1}), paired(b=1, c=10, both=9, neither=20))
        self.assertEqual(r["verdict"], "not-demonstrated")

    def test_the_result_is_read_once_when_complete(self):
        r = C.analyse(spec(n=41), paired(b=10, c=1, both=9, neither=20))
        self.assertEqual(r["verdict"], "incomplete")
        self.assertNotIn("b", r)

    def test_more_than_one_percent_without_a_result_is_invalid(self):
        runs = paired(b=0, c=0, both=0, neither=98) + [
            run("e1", "base", "infra_error"),
            run("e1", "hyp", "infra_error"),
            run("e2", "base", "infra_error"),
        ]
        self.assertEqual(C.analyse(spec(n=98), runs)["verdict"], "invalid")

    def test_an_infra_error_attempt_does_not_hide_a_later_solve(self):
        runs = paired(b=0, c=0, both=0, neither=1) + [run("p1", "base", "infra_error", seed=2), run("p1", "hyp", "solved", seed=2)]
        r = C.analyse(spec(n=1, primary={"kind": "superiority", "expected_gain": 0.1}), runs)
        self.assertEqual((r["b"], r["c"]), (1, 0))

    def test_runs_of_another_split_or_model_are_ignored(self):
        runs = paired(b=3, c=0, both=0, neither=1) + [
            run("zz", "base", "solved", split="d" * 64),
            run("zz", "hyp", "solved", model="other"),
        ]
        r = C.analyse(spec(n=4), runs)
        self.assertEqual(r["n_paired"], 4)

    def test_non_inferiority_uses_the_margin(self):
        s = spec(n=200, primary={"kind": "noninferiority", "margin": 0.05})
        # 20 discordant pairs split 9 / 11: D = -0.01, well inside a 0.05 margin
        ok = C.analyse(s, paired(b=9, c=11, both=100, neither=80))
        self.assertIn(ok["verdict"], ("non-inferior", "not-demonstrated"))
        self.assertLess(ok["noninferiority_p"], 0.05)
        # 0 against 30: D = -0.15, far outside it
        bad = C.analyse(s, paired(b=0, c=30, both=100, neither=70))
        self.assertEqual(bad["verdict"], "not-demonstrated")
        self.assertGreater(bad["noninferiority_p"], 0.05)

    def test_bad_input_is_reported_not_computed(self):
        runs = paired(b=1, c=0, both=0, neither=1)
        runs[1] = copy.deepcopy(runs[1])  # the hypothesis arm's solved run
        runs[1]["checks"]["kernel"] = "fail"
        r = C.analyse(spec(n=2), runs)
        self.assertEqual(r["verdict"], "invalid-input")

    def test_secondary_margins_are_required_in_the_registration(self):
        s = spec()
        del s["secondary"]["wall_s"]
        self.assertTrue(any("wall_s" in p for p in C.check_spec(s)))

    def test_a_solved_run_without_a_cost_is_refused(self):
        runs = paired(b=10, c=1, both=9, neither=20)
        runs[1] = run("p1", "hyp", "solved", cost=None)
        r = C.analyse(spec(n=40, primary={"kind": "superiority", "expected_gain": 0.1}), runs)
        self.assertEqual(r["verdict"], "invalid-input")
        self.assertTrue(any("cost.tokens" in p for p in r["problems"]))

    def test_superior_and_cheaper_is_net_pareto_and_promotable_when_powered(self):
        s = spec(n=40, primary={"kind": "superiority", "expected_gain": 0.1}, psi=0.3)
        r = C.analyse(s, paired(b=12, c=0, both=10, neither=18, hyp_cost=0.5))
        self.assertEqual(r["verdict"], "superior")
        self.assertTrue(r["secondary"]["tokens"]["better"] and r["secondary"]["tokens"]["noninferior"])
        self.assertTrue(r["net_pareto"])
        self.assertEqual(r["promotable"], not r["underpowered"])
        self.assertTrue(C.analyse({**s, "n": 40}, paired(b=12, c=0, both=10, neither=18, hyp_cost=0.5))["net_pareto"])

    def test_superior_but_far_more_expensive_is_not_net_pareto(self):
        s = spec(n=40, primary={"kind": "superiority", "expected_gain": 0.1}, psi=0.3)
        r = C.analyse(s, paired(b=12, c=0, both=10, neither=18, hyp_cost=2.0))
        self.assertEqual(r["verdict"], "superior")
        self.assertFalse(r["secondary"]["tokens"]["noninferior"])
        self.assertFalse(r["net_pareto"])

    def test_non_inferior_needs_a_better_axis_to_be_net_pareto(self):
        s = spec(n=200, primary={"kind": "noninferiority", "margin": 0.1}, psi=0.1)
        same = C.analyse(s, paired(b=9, c=11, both=100, neither=80, hyp_cost=1.0))
        self.assertEqual(same["verdict"], "non-inferior")
        self.assertFalse(same["net_pareto"])
        cheaper = C.analyse(s, paired(b=9, c=11, both=100, neither=80, hyp_cost=0.5))
        self.assertTrue(cheaper["net_pareto"])

    def test_the_cli_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "s.json").write_text(json.dumps(spec(n=40, primary={"kind": "superiority", "expected_gain": 0.1})))
            (p / "r.jsonl").write_text("\n".join(json.dumps(x) for x in paired(b=10, c=1, both=9, neither=20)) + "\n")
            self.assertEqual(C.main(["analyse", str(p / "s.json"), str(p / "r.jsonl")]), 0)
            (p / "ids.txt").write_text("a\nb\n")
            self.assertEqual(C.main(["split-hash", str(p / "ids.txt")]), 0)


if __name__ == "__main__":
    unittest.main()
