"""tools/promote/stmt_closure.py: the closure of a sample under the regimes of a base of statements (synthetic exports in the format of lean4export 3.1)."""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "promote"))
sys.path.insert(0, str(ROOT / "tests"))
import layers as L  # noqa: E402
import stmt_closure as S  # noqa: E402
from test_closure import Builder  # noqa: E402


def proofs_and_opaques() -> Builder:
    """A1 states something about D; D unfolds to the opaque O, which is implemented by `hidden`; the PROOF of A1 uses the lemma `lem` (which uses `deep`) and `base`"""
    b = Builder()
    b.decl("axiom", "T", b.sort())
    t = b.const("T")
    for n in ("base", "deep", "hidden"):
        b.decl("axiom", n, t)
    b.decl("opaque", "O", t, b.const("hidden"))
    b.decl("def", "D", t, b.const("O"))
    b.decl("thm", "lem", t, b.const("deep"))
    b.decl("thm", "A1", b.const("D"), b.app(b.const("lem"), b.const("base")))
    return b


def two_topics_sharing_a_lemma() -> Builder:
    """both topics' proofs use `shared_lem`, neither statement does"""
    b = Builder()
    b.decl("axiom", "T", b.sort())
    t = b.const("T")
    b.decl("axiom", "base", t)
    b.decl("thm", "shared_lem", t, b.const("base"))
    b.decl("thm", "A1", t, b.const("shared_lem"))
    b.decl("thm", "B1", t, b.const("shared_lem"))
    return b


def measured(b: Builder, topics: dict, universe: set | None = None) -> dict:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "e.ndjson"
        b.write(p)
        ex = L.Full()
        ex.read(p)
        return S.measure(ex, topics, universe)


class Regimes(unittest.TestCase):
    def test_the_proofs_of_theorems_and_what_only_they_use_drop_out_of_the_closure(self):
        r = measured(proofs_and_opaques(), {"x": ["A1"]})
        self.assertEqual({k: v["totals"]["units"] for k, v in r.items()}, {"full": 8, "theorems": 5, "theorems+opaque": 4})
        self.assertEqual({k: v["totals"]["constants"] for k, v in r.items()}, {"full": 8, "theorems": 5, "theorems+opaque": 4})

    def test_the_terms_are_those_below_the_declarations_that_are_kept(self):
        r = measured(proofs_and_opaques(), {"x": ["A1"]})
        # full: A1 4 (its type, and the application with its two constants), D 2, O 2, hidden 1, T 1, lem 2, base 1, deep 1
        # theorems: A1 1 (the value is gone), lem, base and deep are not reached; opaque: O 1 and hidden is not reached
        self.assertEqual({k: v["totals"]["terms"] for k, v in r.items()}, {"full": 14, "theorems": 7, "theorems+opaque": 5})

    def test_the_kinds_are_those_of_the_source_so_a_stubbed_theorem_is_still_counted_as_a_theorem(self):
        r = measured(proofs_and_opaques(), {"x": ["A1"]})
        self.assertEqual(r["full"]["totals"]["kinds"], {"axiom": 4, "def": 1, "opaque": 1, "thm": 2})
        self.assertEqual(r["theorems"]["totals"]["kinds"], {"axiom": 2, "def": 1, "opaque": 1, "thm": 1})
        self.assertEqual(r["theorems+opaque"]["totals"]["kinds"], {"axiom": 1, "def": 1, "opaque": 1, "thm": 1})

    def test_a_lemma_that_only_the_proofs_of_two_topics_share_is_in_the_foundation_only_when_proofs_are_kept(self):
        r = measured(two_topics_sharing_a_lemma(), {"alpha": ["A1"], "beta": ["B1"]})
        self.assertEqual(r["full"]["foundation"], {"units": 3, "constants": 3, "terms": 4})  # T, base, shared_lem
        self.assertEqual(r["theorems"]["foundation"]["units"], 1)  # T alone: the statements share nothing else
        self.assertEqual(r["full"]["sessions"]["units_max"], 4)  # the topic's own theorem and the three of the foundation
        self.assertEqual(r["theorems"]["sessions"]["units_max"], 2)

    def test_one_topic_has_no_foundation(self):
        r = measured(proofs_and_opaques(), {"x": ["A1"]})
        self.assertIsNone(r["full"]["foundation"])
        self.assertEqual(r["full"]["sessions"], {"topics": 1, "units_median": 8, "units_max": 8, "terms_median": 14, "terms_max": 14})

    def test_the_universe_leaves_out_what_the_core_holds_in_every_regime(self):
        added = {("A1",), ("D",), ("O",), ("hidden",), ("lem",), ("base",), ("deep",)}  # T is the core's
        r = measured(proofs_and_opaques(), {"x": ["A1"]}, added)
        self.assertEqual({k: v["totals"]["units"] for k, v in r.items()}, {"full": 7, "theorems": 4, "theorems+opaque": 3})

    def test_measuring_twice_gives_the_same_figures(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "e.ndjson"
            proofs_and_opaques().write(p)
            ex = L.Full()
            ex.read(p)
            self.assertEqual(S.measure(ex, {"x": ["A1"]}, None), S.measure(ex, {"x": ["A1"]}, None))

    def test_the_plan_of_layers_itself_is_the_full_regime(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "e.ndjson"
            proofs_and_opaques().write(p)
            ex = L.Full()
            ex.read(p)
            plan = L.plan(ex, {"x": ["A1"]}, None)
        self.assertEqual(plan["totals"]["units"], 8)
        self.assertEqual(plan["totals"]["terms"], 14)  # the planner counts the terms too: layers.json says how large each layer is


class Report(unittest.TestCase):
    def run_cli(self, b: Builder, topics: dict, *extra: str) -> tuple[str, dict]:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            b.write(root / "e.ndjson")
            (root / "topics.json").write_text(json.dumps(topics), encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = S.main([str(root / "e.ndjson"), "--topics", str(root / "topics.json"), "--out", str(root / "r.json"), *extra])
            self.assertEqual(code, 0)
            return out.getvalue(), json.loads((root / "r.json").read_text(encoding="utf-8"))

    def test_the_table_sets_every_regime_against_the_full_one(self):
        text, report = self.run_cli(proofs_and_opaques(), {"x": ["A1"]})
        self.assertEqual(list(report), ["full", "theorems", "theorems+opaque"])
        self.assertIn("| full | 8 (100 %) | 8 (100 %) | 14 (100 %) |", text)
        self.assertIn("| theorems | 5 (62 %) | 5 (62 %) | 7 (50 %) |", text)
        self.assertIn("| theorems+opaque | 4 (50 %) | 4 (50 %) | 5 (36 %) |", text)
        self.assertIn("units by the kind of their first constant", text)

    def test_added_names_restrict_the_count(self):
        with tempfile.TemporaryDirectory() as d:
            added = Path(d) / "added.jsonl"
            added.write_text("".join(json.dumps([n]) + "\n" for n in ("A1", "D", "O", "hidden", "lem", "base", "deep")), encoding="utf-8")
            _, report = self.run_cli(proofs_and_opaques(), {"x": ["A1"]}, "--added", str(added))
        self.assertEqual(report["full"]["totals"]["units"], 7)


if __name__ == "__main__":
    unittest.main()
