import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "campaign"))
import campaign as C  # noqa: E402
import heldout as H  # noqa: E402

CUTOFF = "2026-07-01"


def cand(i, library="a", date=None, own_deps=0, dep_domains=(), hyps=2, size=6, aliases=0, **kw):
    c = {
        "id": f"id{i}",
        "name": f"t{i}",
        "library": library,
        "module": f"M.{library}",
        "date": date,
        "own_deps": own_deps,
        "dep_domains": list(dep_domains),
        "hyps": hyps,
        "size": size,
        "aliases": aliases,
    }
    c.update(kw)
    return c


class Rules(unittest.TestCase):
    def test_trivial_or_aliased_statements_are_never_candidates(self):
        self.assertFalse(H.nontrivial(cand(1, hyps=0)))
        self.assertFalse(H.nontrivial(cand(1, size=4)))
        self.assertFalse(H.nontrivial(cand(1, aliases=1)))
        self.assertFalse(H.nontrivial({"hyps": 3, "size": 9}))
        self.assertTrue(H.nontrivial(cand(1)))

    def test_the_stratum_of_a_theorem(self):
        self.assertEqual(H.stratum_of(cand(1, date="2026-08-01"), CUTOFF), "post-cutoff")
        self.assertEqual(H.stratum_of(cand(1, date="2026-06-30", own_deps=2), CUTOFF), "dependency-ablation")
        self.assertEqual(H.stratum_of(cand(1, dep_domains=["Algebra", "Analysis"]), CUTOFF), "cross-domain")
        self.assertIsNone(H.stratum_of(cand(1, dep_domains=["Algebra"], own_deps=1), CUTOFF))  # one area, one lemma: neither
        self.assertEqual(H.stratum_of(cand(1, own_deps=12), CUTOFF), "dependency-ablation")
        self.assertIsNone(H.stratum_of(cand(1, own_deps=13), CUTOFF))  # too many: not a lemma search
        self.assertIsNone(H.stratum_of(cand(1), CUTOFF))

    def test_a_post_cutoff_theorem_is_post_cutoff_even_if_it_is_also_cross_domain(self):
        self.assertEqual(H.stratum_of(cand(1, date="2026-09-01", dep_domains=["A", "B"]), CUTOFF), "post-cutoff")

    def test_a_theorem_dated_before_the_cutoff_or_undated_is_not_post_cutoff(self):
        self.assertIsNone(H.stratum_of(cand(1, date="2026-06-30"), CUTOFF))
        self.assertIsNone(H.stratum_of(cand(1, date=None), CUTOFF))


class Selection(unittest.TestCase):
    def build(self):
        cs = []
        # 15 post-cutoff theorems, 15 cross-domain (two areas), 15 ablation (three lemmas of their own library), 40 that are none of them
        for k in range(15):
            cs.append(cand(200 + k, "a", date="2026-08-01"))
            cs.append(cand(300 + k, "a", dep_domains=["Algebra", "Analysis"]))
            cs.append(cand(400 + k, "b", own_deps=3))
        for k in range(40):
            cs.append(cand(k, "a"))
        return cs

    def test_each_stratum_is_filled_without_overlap_and_the_counts_are_reported(self):
        r = H.select(self.build(), CUTOFF, 10, "s", 1.0)
        self.assertEqual(r["counts"], {"post-cutoff": 10, "cross-domain": 10, "dependency-ablation": 10})
        everything = [i for s in H.STRATA for i in r["strata"][s]]
        self.assertEqual(len(everything), len(set(everything)))
        self.assertEqual(r["exclude"], sorted(everything))
        self.assertTrue(all(i.startswith("id2") for i in r["strata"]["post-cutoff"]))
        self.assertTrue(all(i.startswith("id3") for i in r["strata"]["cross-domain"]))
        self.assertTrue(all(i.startswith("id4") for i in r["strata"]["dependency-ablation"]))

    def test_the_same_input_and_seed_give_the_same_problems_in_any_order(self):
        cs = self.build()
        a = H.select(cs, CUTOFF, 10, "s", 1.0)
        b = H.select(list(reversed(cs)), CUTOFF, 10, "s", 1.0)
        self.assertEqual(a, b)
        self.assertNotEqual(a["strata"], H.select(cs, CUTOFF, 10, "another seed", 1.0)["strata"])

    def test_no_library_gets_more_than_its_share(self):
        cs = [cand(i, "big", date="2026-08-01") for i in range(50)] + [cand(100 + i, "small", date="2026-08-01") for i in range(50)]
        r = H.select(cs, CUTOFF, 10, "s", 0.5)
        self.assertEqual(r["libraries"]["post-cutoff"], {"big": 5, "small": 5})

    def test_a_stratum_with_too_few_candidates_is_short_and_the_command_says_so(self):
        cs = [cand(i, "a", date="2026-08-01") for i in range(3)]
        r = H.select(cs, CUTOFF, 10, "s", 1.0)
        self.assertEqual((r["counts"]["post-cutoff"], r["available"]["post-cutoff"]), (3, 3))
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "c.jsonl").write_text("\n".join(json.dumps(c) for c in cs) + "\n")
            self.assertEqual(H.main([str(Path(d) / "c.jsonl"), "--cutoff", CUTOFF, "--per-stratum", "10"]), 3)
            self.assertEqual(
                H.main(
                    [
                        str(Path(d) / "c.jsonl"),
                        "--cutoff",
                        CUTOFF,
                        "--per-stratum",
                        "2",
                        "--max-library-share",
                        "1.0",
                        "--out",
                        str(Path(d) / "o.json"),
                    ]
                ),
                3,
            )
            self.assertEqual(json.loads((Path(d) / "o.json").read_text())["counts"]["post-cutoff"], 2)

    def test_the_split_hash_is_the_one_the_registration_needs(self):
        r = H.select(self.build(), CUTOFF, 10, "s", 1.0)
        self.assertEqual(r["split_hash"], C.split_hash(r["exclude"]))
        self.assertEqual(len(r["split_hash"]), 64)

    def test_selected_statements_are_all_in_exclude_so_no_arm_can_see_them(self):
        r = H.select(self.build(), CUTOFF, 10, "s", 1.0)
        for s in H.STRATA:
            self.assertTrue(set(r["strata"][s]) <= set(r["exclude"]))


if __name__ == "__main__":
    unittest.main()
