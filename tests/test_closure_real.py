"""The closure extractor on the REAL lean4export output of tools/closure/fixture (Lean core only). Skipped unless CLOSURE_FIXTURE_EXPORT names the file: CI
builds lean4export at the commit Tengoku pins, exports the fixture, and runs this. What it holds the extractor to is stated in Fixture.lean."""

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "closure"))
import closure as cl  # noqa: E402

EXPORT = os.environ.get("CLOSURE_FIXTURE_EXPORT")


@unittest.skipUnless(EXPORT, "CLOSURE_FIXTURE_EXPORT is not set (CI exports the fixture)")
class Real(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ex = cl.Export()
        cls.ex.read(Path(EXPORT))

    def rec(self, name):
        return cl.records(self.ex, [f"Fx.{name}"], {})[0]

    def closure(self, name):
        return set(self.rec(name)["closure"])

    def test_the_format_is_the_one_the_parser_reads(self):
        self.assertGreater(len(self.ex.kind), 1000)
        self.assertIn("Fx.swap_a", self.ex.names_to_index())

    def test_the_closure_passes_through_a_definition(self):
        c = self.closure("double_eq")
        self.assertIn("Fx.double", c)
        self.assertIn("Nat.add", c, "the body of double is reached through the definition")

    def test_a_definition_is_reached_by_the_statement(self):
        r = self.rec("uses_double")
        self.assertIn("Fx.double", r["statement_closure"])

    def test_an_unused_have_does_not_enter_the_closure(self):
        self.assertNotIn("Classical.em", self.closure("swap_c"))
        self.assertNotIn("Classical.em", self.closure("swap_e"))
        self.assertNotIn("Or.inl", self.closure("swap_e"))

    def test_padding_leaves_the_closure_as_it_was(self):
        self.assertEqual(self.closure("swap_c"), self.closure("swap_a"))
        self.assertEqual(self.closure("swap_e"), self.closure("swap_a"))

    def test_a_used_have_is_still_a_proof_of_the_same_statement(self):
        self.assertEqual(self.rec("swap_d")["id"], self.rec("swap_a")["id"])
        self.assertEqual(self.rec("swap_b")["id"], self.rec("swap_a")["id"])

    def test_different_routes_have_different_closures(self):
        # swap_a projects (And.left/right); swap_b destructs with a match (And.casesOn / rec): the footprints differ
        self.assertNotEqual(self.closure("swap_a"), self.closure("swap_b"))

    def test_the_control_proof_that_applies_the_lemma_keeps_it(self):
        self.assertIn("Classical.em", self.closure("em_used"))


if __name__ == "__main__":
    unittest.main()
