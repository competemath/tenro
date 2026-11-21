"""tools/export/compare_exports.py: a statements export agrees with the full export on every declaration it holds (synthetic exports in the format of lean4export 3.1)."""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "export"))
sys.path.insert(0, str(ROOT / "tests"))
import compare_exports as C  # noqa: E402
from test_closure import Builder  # noqa: E402


def full_export() -> Builder:
    """T and base are axioms, D is a definition that unfolds to base; the proof of A1 uses the lemma `lem` (which uses `deep`) and `base`"""
    b = Builder()
    b.decl("axiom", "T", b.sort())
    t = b.const("T")
    b.decl("axiom", "base", t)
    b.decl("axiom", "deep", t)
    b.decl("def", "D", t, b.const("base"))
    b.decl("thm", "lem", t, b.const("deep"))
    b.decl("thm", "A1", b.const("D"), b.app(b.const("lem"), b.const("base")))
    return b


def statements_export() -> Builder:
    """what `--statements` writes for the same environment: A1 an axiom of its type, and neither `lem` nor `deep` (only a proof used them); the terms are numbered differently"""
    b = Builder()
    b.decl("axiom", "T", b.sort())
    t = b.const("T")
    b.decl("axiom", "base", t)
    b.decl("def", "D", t, b.const("base"))
    b.decl("axiom", "A1", b.const("D"))
    return b


def compared(full: Builder, stmt: Builder) -> dict:
    with tempfile.TemporaryDirectory() as d:
        p, q = Path(d) / "full.ndjson", Path(d) / "stmt.ndjson"
        full.write(p)
        stmt.write(q)
        return C.compare(C.read(p), C.read(q))


class Agreement(unittest.TestCase):
    def test_a_theorem_that_stands_as_an_axiom_of_its_type_and_the_dropped_proofs_pass_whatever_the_numbering(self):
        r = compared(full_export(), statements_export())
        self.assertTrue(r["passed"], r["problems"])
        self.assertEqual(r["theorems_as_axioms"], 1)  # A1
        self.assertEqual(r["unchanged"], 3)  # T, base, D
        self.assertEqual(r["dropped_with_the_proofs"], 2)  # lem and deep
        self.assertGreater(r["full"]["terms"], r["statements"]["terms"])
        self.assertEqual(r["full"]["kinds"], {"axiom": 3, "def": 1, "thm": 2})
        self.assertEqual(r["statements"]["kinds"], {"axiom": 3, "def": 1})

    def test_the_two_exports_number_their_terms_differently(self):
        a, b = C.Reader(), C.Reader()
        with tempfile.TemporaryDirectory() as d:
            p, q = Path(d) / "a.ndjson", Path(d) / "b.ndjson"
            full_export().write(p)
            statements_export().write(q)
            a.read(p)
            b.read(q)
        self.assertNotEqual(len(a.terms), len(b.terms))
        self.assertEqual(a.decls["D"], b.decls["D"])  # one declaration, one digest

    def test_a_theorem_whose_type_changed_is_refused(self):
        s = statements_export()
        s.lines = [ln for ln in s.lines if not ("axiom" in ln and s.names["A1"] == ln["axiom"]["name"])]
        s.decl("axiom", "A1", s.const("base"))  # the type of A1 is `base`, not `D`
        r = compared(full_export(), s)
        self.assertFalse(r["passed"])
        self.assertEqual(r["problems"]["changed"], ["A1"])

    def test_a_theorem_kept_with_its_proof_is_the_full_exports_theorem_and_is_counted(self):
        s = statements_export()
        s.decl("axiom", "deep", s.const("T"))  # what its proof mentions stays a stub
        s.decl("thm", "lem", s.const("T"), s.const("deep"))  # kept: the full export's lem, term for term
        r = compared(full_export(), s)
        self.assertTrue(r["passed"], r["problems"])
        self.assertEqual(r["theorems_kept"], 1)
        self.assertEqual(r["theorems_as_axioms"], 1)  # A1

    def test_a_theorem_kept_with_another_proof_is_a_change(self):
        s = statements_export()
        s.decl("thm", "lem", s.const("T"), s.const("base"))  # the full export's lem is proved by `deep`
        r = compared(full_export(), s)
        self.assertFalse(r["passed"])
        self.assertEqual(r["problems"]["changed"], ["lem"])
        self.assertEqual(r["theorems_kept"], 0)

    def test_a_declaration_the_full_export_lacks_is_refused(self):
        s = statements_export()
        s.decl("axiom", "extra", s.const("T"))
        r = compared(full_export(), s)
        self.assertEqual(r["problems"]["only_in_statements"], ["extra"])
        self.assertFalse(r["passed"])

    def test_a_definition_whose_value_changed_is_refused(self):
        s = Builder()
        s.decl("axiom", "T", s.sort())
        t = s.const("T")
        s.decl("axiom", "base", t)
        s.decl("def", "D", t, s.const("T"))  # D unfolds to T here, to base in the full export
        s.decl("axiom", "A1", s.const("D"))
        r = compared(full_export(), s)
        self.assertEqual(r["problems"]["changed"], ["D"])

    def test_an_axiom_that_is_a_theorem_in_neither_must_be_equal_too(self):
        s = statements_export()
        s.lines = [ln for ln in s.lines if not ("axiom" in ln and s.names["base"] == ln["axiom"]["name"])]
        s.decl("def", "base", s.const("T"), s.const("T"))  # an axiom of the full export became a definition
        r = compared(full_export(), s)
        self.assertIn("base", r["problems"]["changed"])


def with_binder(kind: str, binder: str, info: str, body: str = "T") -> Builder:
    """T and base are axioms; `P` has the type `(binder : T) -> body`, as a definition or as a theorem (`kind`); the export keeps the first alpha-equivalent term's binder names and info"""
    b = Builder()
    b.decl("axiom", "T", b.sort())
    t = b.const("T")
    b.decl("axiom", "base", t)
    inner = b.const(body)
    pi = b.term(forallE={"name": b.name(binder), "type": t, "body": inner, "binderInfo": info})
    if kind == "axiom":
        b.decl("axiom", "P", pi)
    else:
        b.decl(kind, "P", pi, b.const("base"))
    return b


class BinderNames(unittest.TestCase):
    def test_binder_names_and_binder_info_alone_are_not_a_change(self):
        r = compared(with_binder("def", "x", "default"), with_binder("def", "y", "implicit"))
        self.assertTrue(r["passed"], r["problems"])
        self.assertEqual(r["unchanged"], 3)  # T, base, P
        self.assertEqual(r["binder_names_only"], 1)
        self.assertEqual(r["binder_names_only_examples"], ["P"])

    def test_the_same_binder_is_not_counted(self):
        r = compared(with_binder("def", "x", "default"), with_binder("def", "x", "default"))
        self.assertEqual(r["binder_names_only"], 0)

    def test_another_body_under_the_binder_is_a_change(self):
        r = compared(with_binder("def", "x", "default"), with_binder("def", "x", "default", body="base"))
        self.assertFalse(r["passed"])
        self.assertEqual(r["problems"]["changed"], ["P"])

    def test_a_theorem_with_other_binder_names_stands_as_an_axiom_and_is_counted(self):
        r = compared(with_binder("thm", "x", "default"), with_binder("axiom", "y", "instImplicit"))
        self.assertTrue(r["passed"], r["problems"])
        self.assertEqual(r["theorems_as_axioms"], 1)
        self.assertEqual(r["binder_names_only"], 1)

    def test_a_theorem_whose_type_changed_under_its_binder_is_refused(self):
        r = compared(with_binder("thm", "x", "default"), with_binder("axiom", "x", "default", body="base"))
        self.assertEqual(r["problems"]["changed"], ["P"])


def with_levels(param: str, rec_type_extra: bool = False) -> Builder:
    """a universe-polymorphic axiom `P.{param} : Sort param`, a structure-like inductive with its constructor and recursor"""
    b = Builder()
    u = b.name(param)
    b.lines.append({"il": 1, "param": u})
    s = b.term(sort=1)
    b.lines.append({"axiom": {"name": b.name("P"), "levelParams": [u], "type": s, "isUnsafe": False}})
    nat = b.name("Foo")
    mk, rec = b.name("Foo.mk"), b.name("Foo.rec")
    ty = b.const("P")
    b.lines.append(
        {
            "inductive": {
                "types": [{"name": nat, "levelParams": [], "type": ty, "numParams": 0, "numIndices": 0, "all": [nat], "ctors": [mk]}],
                "ctors": [{"name": mk, "levelParams": [], "type": ty, "induct": nat, "cidx": 0, "numParams": 0, "numFields": 0}],
                "recs": [
                    {
                        "name": rec,
                        "levelParams": [],
                        "type": ty,
                        "all": [nat],
                        "numParams": 0,
                        "numIndices": 0,
                        "numMotives": 1,
                        "numMinors": 2 if rec_type_extra else 1,
                        "rules": [{"ctor": mk, "nfields": 0, "rhs": ty}],
                    }
                ],
            }
        }
    )
    return b


class LevelsAndInductives(unittest.TestCase):
    def test_levels_and_inductive_groups_are_compared_member_by_member(self):
        r = compared(with_levels("u"), with_levels("u"))
        self.assertTrue(r["passed"], r["problems"])
        self.assertEqual(r["unchanged"], 4)  # P, Foo, Foo.mk, Foo.rec
        self.assertEqual(r["full"]["kinds"], {"axiom": 1, "ctor": 1, "inductive": 1, "rec": 1})

    def test_another_universe_parameter_is_a_change(self):
        r = compared(with_levels("u"), with_levels("v"))
        self.assertIn("P", r["problems"]["changed"])

    def test_a_changed_recursor_is_a_change_of_that_member_only(self):
        r = compared(with_levels("u"), with_levels("u", rec_type_extra=True))
        self.assertEqual(r["problems"]["changed"], ["Foo.rec"])


class Command(unittest.TestCase):
    def run_cli(self, full: Builder, stmt: Builder) -> tuple[int, str, dict]:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            full.write(root / "full.ndjson")
            stmt.write(root / "stmt.ndjson")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = C.main([str(root / "full.ndjson"), str(root / "stmt.ndjson"), "--out", str(root / "r.json")])
            return code, out.getvalue(), json.loads((root / "r.json").read_text(encoding="utf-8"))

    def test_exit_zero_and_a_summary_when_they_agree(self):
        code, text, report = self.run_cli(full_export(), statements_export())
        self.assertEqual(code, 0)
        self.assertIn("1 theorems stand as axioms", text)
        self.assertTrue(text.rstrip().endswith("passed"))
        self.assertTrue(report["passed"])

    def test_exit_one_and_the_problem_when_they_differ(self):
        s = statements_export()
        s.decl("thm", "lem", s.const("T"), s.const("base"))
        code, text, _ = self.run_cli(full_export(), s)
        self.assertEqual(code, 1)
        self.assertIn("PROBLEM changed: 1", text)
        self.assertTrue(text.rstrip().endswith("FAILED"))


if __name__ == "__main__":
    unittest.main()
