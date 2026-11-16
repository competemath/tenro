import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "calibration"))
import label  # noqa: E402

P = label.load_params(Path(__file__).resolve().parents[1] / "calibration" / "protocol.toml")


def rec(name, lib, closure, id="s1", **kw):
    return {"id": id, "name": name, "lib": lib, "closure": closure, "statement_closure": [], "modules": {}, **kw}


def many(prefix, n):
    return [f"{prefix}.c{i}" for i in range(n)]


class LabelTest(unittest.TestCase):
    def test_same_lib_is_alias(self):
        r = label.label_pair(rec("A.t", "L", many("x", 9)), rec("B.t", "L", many("y", 9)), P)
        self.assertEqual((r["label"], r["rule"]), ("alias", "same-chain"))

    def test_uses_other_is_alias(self):
        a = rec("A.t", "L1", many("x", 9) + ["B.t"])
        r = label.label_pair(a, rec("B.t", "L2", many("y", 9)), P)
        self.assertEqual(r["rule"], "same-chain")

    def test_disjoint_different_libs_independent_and_reviewed(self):
        g = label.label_group([rec("A.t", "L1", many("x", 9)), rec("B.t", "L2", many("y", 9))], P)
        self.assertEqual(g["label"], "independent")
        self.assertTrue(g["review"])

    def test_below_substance_is_similar(self):
        r = label.label_pair(rec("A.t", "L1", many("x", 2)), rec("B.t", "L2", many("y", 9)), P)
        self.assertEqual((r["label"], r["rule"]), ("similar", "substance"))

    def test_shared_proof_alias(self):
        shared = many("s", 8)
        r = label.label_pair(rec("A.t", "L1", shared + ["a1"]), rec("B.t", "L2", shared + ["b1"]), P)
        self.assertEqual((r["label"], r["rule"]), ("alias", "shared-proof"))

    def test_forced_layer_and_axioms_dropped(self):
        a = rec("A.t", "L1", many("x", 9) + ["Nat.succ", "propext"], modules={"Nat.succ": "Init.Prelude"})
        self.assertEqual(label._outside(a, P["forced_layer_modules"]), set(many("x", 9)))

    def test_between_is_similar_and_group_strongest(self):
        shared = many("s", 3)
        a, b = rec("A.t", "L1", shared + many("a", 7)), rec("B.t", "L2", shared + many("b", 7))
        self.assertEqual(label.label_pair(a, b, P)["label"], "similar")
        c = rec("C.t", "L3", many("z", 9))
        self.assertEqual(label.label_group([a, b, c], P)["label"], "independent")

    def test_groups_need_two_and_are_deterministic(self):
        recs = [rec("A.t", "L1", many("x", 9), id="g"), rec("B.t", "L2", many("y", 9), id="g"), rec("C.t", "L1", many("x", 9), id="h")]
        out = label.label_all(recs, P)
        self.assertEqual([g["id"] for g in out], ["g"])
        self.assertEqual(out, label.label_all(list(reversed(recs)), P))


class Rules2(unittest.TestCase):
    def test_a_collection_is_not_one_chain(self):
        a, b = rec("A.t", "Compfiles", many("x", 9)), rec("B.t", "Compfiles", many("y", 9))
        self.assertEqual(label.label_pair(a, b, P)["rule"], "independent")  # Compfiles is a collection: compared by closures
        c, d = rec("C.t", "Other", many("x", 9)), rec("D.t", "Other", many("y", 9))
        self.assertEqual(label.label_pair(c, d, P)["rule"], "same-chain")  # an ordinary library is one chain
        e, f = rec("E.t", "Compfiles", many("x", 9) + ["F.t"]), rec("F.t", "Compfiles", many("y", 9))
        self.assertEqual(label.label_pair(e, f, P)["rule"], "same-chain")  # one uses the other: a chain whatever the library

    def test_the_statement_closure_does_not_swallow_the_footprint(self):
        big = {"statement_closure": many("x", 9), "statement_constants": ["x0"]}
        a, b = rec("A.t", "L1", many("x", 9), **big), rec("B.t", "L2", many("x", 9), **big)
        r = label.label_pair(a, b, P)
        self.assertEqual(
            (r["label"], r["rule"]), ("alias", "shared-proof")
        )  # eight shared constants left, identical: a copy, not "substance"


if __name__ == "__main__":
    unittest.main()
