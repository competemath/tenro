import json
import math
import random
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "lens"))
import lens as L  # noqa: E402


def lens(v0, v1, fwd, res=None):
    return L.make(v0, v1, fwd, res)


class Basics(unittest.TestCase):
    def test_unmentioned_ids_are_unchanged_and_identities_are_dropped(self):
        x = lens("v1", "v2", {"a": ["b"], "c": ["c"]})
        self.assertEqual(x["forward"], {"a": ["b"]})
        self.assertEqual(L.apply(x, "z"), ["z"])

    def test_inverse_lifts_back_one_to_one_and_split(self):
        x = lens("v1", "v2", {"a": ["a1", "a2"], "b": ["b1"]}, {"a": "recombine-hash"})
        back = L.inverse(x)
        self.assertEqual((L.lift(back, "a1"), L.lift(back, "a2"), L.lift(back, "b1"), L.lift(back, "z")), ("a", "a", "b", "z"))

    def test_two_statements_becoming_one_is_refused(self):
        with self.assertRaises(L.LensError):
            L.inverse(lens("v1", "v2", {"a": ["n"], "b": ["n"]}))

    def test_compose(self):
        f, g = lens("v1", "v2", {"a": ["b"], "x": ["x1", "x2"]}), lens("v2", "v3", {"b": ["c"], "x1": ["p"], "q": ["r"]})
        h = L.compose(f, g)
        self.assertEqual((h["from"], h["to"]), ("v1", "v3"))
        self.assertEqual(L.apply(h, "a"), ["c"])
        self.assertEqual(sorted(L.apply(h, "x")), ["p", "x2"])
        self.assertEqual(L.apply(h, "q"), ["r"])  # untouched by f, changed by g
        with self.assertRaises(L.LensError):
            L.compose(g, f)


def random_lens(rng, i, universe):
    ids = rng.sample(universe, 3)
    return lens(f"v{i}", f"v{i + 1}", {ids[0]: [f"{ids[0]}'"], ids[1]: [f"{ids[1]}_a", f"{ids[1]}_b"]})


class ChainTest(unittest.TestCase):
    def build(self, n, seed=1):
        rng = random.Random(seed)
        universe = [f"s{k}" for k in range(8)]
        return [random_lens(rng, i, universe) for i in range(n)]

    def test_skip_lenses_equal_the_naive_composition(self):
        ls = self.build(37)
        chain = L.Chain(ls)
        for i, j in [(0, 37), (3, 20), (5, 6), (10, 11), (0, 1), (7, 36)]:
            naive = ls[i]
            for x in ls[i + 1 : j]:
                naive = L.compose(naive, x)
            got = chain.between(i, j)
            self.assertEqual({k: sorted(v) for k, v in got["forward"].items()}, {k: sorted(v) for k, v in naive["forward"].items()}, (i, j))

    def test_a_range_costs_log_n_compositions_once_the_blocks_are_built(self):
        n = 256
        chain = L.Chain(self.build(n))
        chain.between(0, n)  # builds the aligned blocks, about n compositions, once
        self.assertLessEqual(chain.build_compositions, n)
        rng = random.Random(7)
        worst = 0
        for _ in range(60):
            i = rng.randrange(0, n - 1)
            j = rng.randrange(i + 1, n + 1)
            before = chain.query_compositions
            chain.between(i, j)
            worst = max(worst, chain.query_compositions - before)
            self.assertLessEqual(chain.query_compositions - before, 2 * math.ceil(math.log2(n)))
        self.assertGreater(worst, 0)

    def test_skip_blocks_of_a_chain_that_is_not_a_power_of_two(self):
        chain = L.Chain(self.build(37))
        self.assertEqual((chain.between(0, 37)["from"], chain.between(0, 37)["to"]), ("v0", "v37"))
        self.assertEqual((chain.between(5, 6)["from"], chain.between(5, 6)["to"]), ("v5", "v6"))

    def test_a_broken_chain_and_bad_ranges(self):
        with self.assertRaises(L.LensError):
            L.Chain([lens("v1", "v2", {}), lens("v3", "v4", {})])
        with self.assertRaises(L.LensError):
            L.Chain([lens("v1", "v2", {})]).between(0, 2)


class Acceptance(unittest.TestCase):
    def test_round_trip_accepts_the_right_ids_and_names_every_rejection(self):
        x = lens("v1", "v2", {"id_a": ["id_a2"]})
        old = {"A.t": "id_a", "B.t": "id_b", "C.t": "id_c"}
        new = {"A.t": "id_a2", "B.t": "id_b", "C.t": "id_other", "D.t": "id_d"}
        r = L.check_migration([("A.t", "A.t"), ("B.t", "B.t"), ("C.t", "C.t"), ("Z.t", "D.t"), ("B.t", "Gone.t")], old, new, x)
        self.assertEqual((r["denominator"], r["accepted"]), (5, 2))
        whys = {(d["old"], d["new"]): d["why"] for d in r["rejected"]}
        self.assertIn("lifts back to id_other", whys[("C.t", "C.t")])
        self.assertIn("no id", whys[("Z.t", "D.t")])
        self.assertIn("not migrated", whys[("B.t", "Gone.t")])
        self.assertEqual(r["rate"], 0.4)

    def test_a_silent_weakening_is_rejected(self):
        # the migrated theorem states something else (a different id) that the lens does not account for
        r = L.check_migration([("A.t", "A.t")], {"A.t": "id_a"}, {"A.t": "id_weaker"}, lens("v1", "v2", {}))
        self.assertEqual(r["accepted"], 0)

    def test_the_cli(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "old.tsv").write_text("A.t\tid_a\n")
            (d / "new.tsv").write_text("A.t\tid_a2\n")
            (d / "lens.json").write_text(json.dumps(lens("v1", "v2", {"id_a": ["id_a2"]})))
            self.assertEqual(L.main(["check", "--old", str(d / "old.tsv"), "--new", str(d / "new.tsv"), "--lens", str(d / "lens.json")]), 0)
            (d / "new.tsv").write_text("A.t\tid_wrong\n")
            self.assertEqual(L.main(["check", "--old", str(d / "old.tsv"), "--new", str(d / "new.tsv"), "--lens", str(d / "lens.json")]), 1)


if __name__ == "__main__":
    unittest.main()
