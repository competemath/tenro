import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "lens"))
import reseed  # noqa: E402


def row(name, stmt, module="M"):
    return {"name": name, "statement": stmt, "module": module}


class Classify(unittest.TestCase):
    def test_each_old_theorem_lands_in_exactly_one_class_and_the_counts_add_up(self):
        old = [
            row("a", "theorem a (n : Nat) : n = n"),
            row("b", "theorem b (n : Nat) : n + 0 = n", "M1"),
            row("c", "theorem c (n : Nat) : n ≤ n"),
            row("d", "theorem d (n : Nat) : 0 ≤ n"),
            row("e", "theorem e : True"),
        ]
        new = [
            row("a", "theorem a (n : Nat)  :\n  n = n"),  # whitespace only: unchanged
            row("b", "theorem b (n : Nat) : n + 0 = n", "M2"),  # moved
            row("c", "theorem c (n : Nat) : n < n + 1"),  # restated
            row("d2", "theorem d2 (n : Nat) : 0 ≤ n", "M3"),  # renamed
            row("z", "theorem z : 1 = 1"),  # added
        ]
        s, changes = reseed.classify(old, new)
        self.assertEqual((s["unchanged"], s["moved"], s["restated"], s["renamed"], s["removed"], s["added"]), (1, 1, 1, 1, 1, 1))
        self.assertEqual(s["unchanged"] + s["moved"] + s["restated"] + s["renamed"] + s["removed"], s["old"])
        self.assertEqual(s["survival"], 0.8)
        self.assertEqual(s["fidelity"], 0.75)
        by = {c["old"]: c for c in changes}
        self.assertEqual(by["d"]["new"], "d2")
        self.assertEqual(by["e"]["new"], None)
        self.assertNotIn("a", by)

    def test_an_ambiguous_rename_is_a_removal_and_an_addition_never_a_guess(self):
        old = [row("p", "theorem p : True"), row("q", "theorem q : True")]
        new = [row("r", "theorem r : True"), row("s", "theorem s : True")]
        s, changes = reseed.classify(old, new)
        self.assertEqual((s["renamed"], s["removed"], s["added"]), (0, 2, 2))
        self.assertEqual({c["change"] for c in changes}, {"removed"})

    def test_two_olds_one_new_is_also_not_a_rename(self):
        old = [row("p", "theorem p : True"), row("q", "theorem q : True")]
        new = [row("r", "theorem r : True")]
        s, _ = reseed.classify(old, new)
        self.assertEqual((s["renamed"], s["removed"]), (0, 2))

    def test_identical_manifests_change_nothing(self):
        rows = [row(f"t{i}", f"theorem t{i} : {i} = {i}") for i in range(20)]
        s, changes = reseed.classify(rows, list(rows))
        self.assertEqual((s["unchanged"], s["survival"], s["fidelity"], s["added"]), (20, 1.0, 1.0, 0))
        self.assertEqual(changes, [])

    def test_a_name_listed_twice_is_an_error(self):
        with self.assertRaises(ValueError):
            reseed.classify([row("a", "theorem a : True"), row("a", "theorem a : True")], [])

    def test_the_statement_id_ignores_the_name_and_the_layout_only(self):
        self.assertEqual(reseed.statement_id("theorem x (n : Nat) : n = n"), reseed.statement_id("theorem  y  (n : Nat)\n : n = n"))
        self.assertNotEqual(reseed.statement_id("theorem x : a = b"), reseed.statement_id("theorem x : b = a"))
        self.assertEqual(reseed.statement_id("lemma x : True"), reseed.statement_id("lemma y : True"))
        self.assertNotEqual(reseed.statement_id("lemma x : True"), reseed.statement_id("theorem x : True"))

    def test_the_cli(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "o.jsonl").write_text(json.dumps(row("a", "theorem a : True")) + "\n", encoding="utf-8")
            (d / "n.jsonl").write_text(json.dumps(row("a", "theorem a : True")) + "\n", encoding="utf-8")
            self.assertEqual(reseed.main(["classify", str(d / "o.jsonl"), str(d / "n.jsonl"), "--names-out", str(d / "x.jsonl")]), 0)
            self.assertEqual((d / "x.jsonl").read_text(encoding="utf-8"), "")


if __name__ == "__main__":
    unittest.main()
