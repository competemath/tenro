import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "scramble"))
import scramble as S  # noqa: E402

KEY = b"owner-held key"
LIB = ["Mathlib.Algebra.Group.mul_comm_self", "Nat.my_lemma", "Foo.bar"]
PROB = ["Problem.sum_of_squares"]
CORE = ["Nat.succ_le", "Nat.add_comm"]
RESERVED = {"theorem", "by", "simp", "exact", "open", "namespace", "end"}


def mapping():
    return S.build_map(LIB, PROB, CORE, RESERVED, KEY)


class MapTest(unittest.TestCase):
    def test_components_and_what_is_kept(self):
        m = mapping()
        for kept in ("Nat", "succ_le", "add_comm", "theorem", "simp"):
            self.assertNotIn(kept, m)  # core components and reserved tokens
        for scrambled in ("Mathlib", "mul_comm_self", "my_lemma", "Foo", "bar", "Problem", "sum_of_squares"):
            self.assertIn(scrambled, m)
        self.assertTrue(all(v.startswith("x") and len(v) == 17 for v in m.values()))

    def test_reproducible_from_the_key_and_different_for_another(self):
        self.assertEqual(mapping(), mapping())
        self.assertNotEqual(mapping(), S.build_map(LIB, PROB, CORE, RESERVED, b"another key"))

    def test_collisions_are_refused(self):
        key = b"k"
        taken = S.fresh(key, "bar")
        with self.assertRaises(ValueError):
            S.build_map(["Foo.bar", f"Other.{taken}"], [], [], set(), key)


class RewriteTest(unittest.TestCase):
    def test_identifiers_are_mapped_componentwise_and_consistently(self):
        m = mapping()
        src = "theorem Problem.sum_of_squares (n : Nat) : Nat.add_comm n 1 = Foo.bar := by\n  exact Mathlib.Algebra.Group.mul_comm_self n\n"
        out = S.rewrite(src, m)
        for original in ("Problem", "sum_of_squares", "Foo", "bar", "Mathlib", "mul_comm_self"):
            self.assertNotIn(original, out)
        for kept in ("theorem", "Nat.add_comm", "by", "exact", "(n : Nat)"):
            self.assertIn(kept, out)
        self.assertIn(f"{m['Foo']}.{m['bar']}", out)
        # the same component, written alone (after `open Foo`), gets the same fresh name
        self.assertIn(f"exact {m['bar']}", S.rewrite("open Foo\nexact bar n", m).replace("exact  ", "exact "))

    def test_comments_docstrings_and_nested_comments_are_dropped_with_their_lines(self):
        m = mapping()
        src = "/-- the theorem about Foo.bar -/\ntheorem t : Foo.bar := by simp -- uses my_lemma\n/- outer /- inner bar -/ still comment -/\nexact bar\n"
        out = S.rewrite(src, m)
        for word in ("the theorem about", "uses", "inner", "still comment"):
            self.assertNotIn(word, out)
        self.assertEqual(out.count("\n"), src.count("\n"))
        self.assertIn(f"exact {m['bar']}", out)

    def test_strings_are_left_alone_and_numbers_and_projections_survive(self):
        m = mapping()
        out = S.rewrite('#eval "Foo.bar says \\"bar\\""\n#check (x.1 + 2.5)', m)
        self.assertIn('"Foo.bar says \\"bar\\""', out)
        self.assertIn("(x.1 + 2.5)", out)

    def test_primes_and_guillemets(self):
        m = S.build_map(["A.foo'", "A.«odd name»"], [], [], set(), KEY)
        out = S.rewrite("exact A.foo' (A.«odd name»)", m)
        self.assertNotIn("foo", out)
        self.assertNotIn("odd", out)

    def test_cli_rewrites_files_in_place(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "map.json").write_text(json.dumps(mapping()))
            (d / "A.lean").write_text("theorem Foo.bar : True := trivial\n")
            self.assertEqual(S.main(["rewrite", "--map", str(d / "map.json"), str(d / "A.lean")]), 0)
            self.assertNotIn("bar", (d / "A.lean").read_text())
            self.assertEqual(S.main([]), 2)


if __name__ == "__main__":
    unittest.main()
