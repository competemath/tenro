import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "index"))
import intent  # noqa: E402

DOCS = [
    ("List.IsPrefix", "The first list is a prefix of the second.\n\n`IsPrefix l₁ l₂` means that there exists some `t`."),
    ("List.IsSuffix", "The first list is a suffix of the second."),
    ("List.Nodup", "The list has no duplicates: it contains every element at most once."),
    ("Nat.add_comm", "Addition of natural numbers is commutative."),
    ("Nat.mul_comm", "Multiplication of natural numbers is commutative."),
    ("Nat.lt_irrefl", "No natural number is less than itself."),
]
IDS = {n: f"id{i}" for i, (n, _) in enumerate(DOCS)}


def built(docs=DOCS, ids=IDS):
    return intent.build(docs, ids)


class Tokens(unittest.TestCase):
    def test_prose_only_code_and_fences_are_dropped(self):
        t = intent.tokens("The lists `List.append a b` are equal.\n```lean\ntheorem foo : x = y\n```\nBoth sides agree.")
        self.assertEqual(t, ["list", "equal", "both", "side", "agree"])

    def test_plural_s_goes_but_not_ss(self):
        self.assertEqual(intent.tokens("lists glass is bus"), ["list", "glass", "bus"])

    def test_unescape(self):
        self.assertEqual(intent.unescape("a\\nb\\tc\\\\d"), "a\nb\tc\\d")


class Build(unittest.TestCase):
    def test_a_statement_is_one_document_whatever_number_of_theorems_state_it(self):
        ids = {**IDS, "List.IsPrefix2": IDS["List.IsPrefix"]}
        b = intent.build([*DOCS, ("List.IsPrefix2", "Prefixes are initial segments.")], ids)
        self.assertEqual(b["stats"]["documents"], len(DOCS))
        self.assertEqual(b["stats"]["docstrings_without_an_id"], 0)

    def test_a_docstring_whose_theorem_has_no_id_is_counted_not_dropped_silently(self):
        b = intent.build([("Ghost", "Nothing here.")], {})
        self.assertEqual((b["stats"]["documents"], b["stats"]["docstrings_without_an_id"]), (0, 1))

    def test_a_docstring_that_is_all_code_indexes_nothing(self):
        b = intent.build([("A", "`x = y`")], {"A": "idA"})
        self.assertEqual(b["stats"]["documents"], 0)

    def test_deterministic_and_byte_identical_twice(self):
        with tempfile.TemporaryDirectory() as d:
            s1 = intent.write(Path(d) / "a", built())
            s2 = intent.write(Path(d) / "b", built(list(reversed(DOCS))))
            self.assertEqual(s1["sha256"], s2["sha256"], "the order of the docstrings must not matter")

    def test_the_index_is_name_blind_no_declared_name_occurs_in_any_output_file(self):
        with tempfile.TemporaryDirectory() as d:
            intent.write(Path(d), built())
            text = "".join(p.read_text(encoding="utf-8") for p in Path(d).iterdir())
            for name, _ in DOCS:
                self.assertNotIn(name, text)
                self.assertNotIn(name.split(".")[-1], text)


class Search(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        self.addCleanup(self._d.cleanup)
        intent.write(Path(self._d.name), built())
        self.idx, self.docs = intent.load(Path(self._d.name))

    def top(self, q, k=3):
        return [i for i, _ in intent.search(self.idx, self.docs, q, k)]

    def test_recall_on_a_labelled_set_with_paraphrases(self):
        cases = {
            "a list is the start of another list": None,  # no `prefix` word: a vocabulary miss is allowed to fail, see the next test
            "prefix of a list": "id0",
            "suffix": "id1",
            "list with no duplicate elements": "id2",
            "commutative addition": "id3",
            "multiplication is commutative": "id4",
            "less than itself": "id5",
        }
        hits = 0
        for q, want in cases.items():
            if want is None:
                continue
            ok = want in self.top(q, 1)
            hits += ok
            self.assertTrue(ok, q)
        self.assertEqual(hits, 6)

    def test_a_query_with_no_known_word_finds_nothing_and_never_crashes(self):
        self.assertEqual(intent.search(self.idx, self.docs, "zzz qqq", 5), [])
        self.assertEqual(intent.search(self.idx, self.docs, "", 5), [])

    def test_scores_are_decreasing_and_ties_are_broken_by_id(self):
        r = intent.search(self.idx, self.docs, "natural number commutative", 6)
        scores = [s for _, s in r]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual({i for i, _ in r[:2]}, {"id3", "id4"})

    def test_an_empty_index_is_empty(self):
        self.assertEqual(intent.search({}, [], "list", 3), [])


class Cli(unittest.TestCase):
    def test_read_docs_and_the_cli_search(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "docs.tsv").write_text(
                "doc\tA\tM\tthm\tThe list is empty.\\nIt has no elements.\nnoise\ndoc\tB\tM\tthm\tZero is a number.\ndoc\tD\tM\tdef\tA definition.\n",
                encoding="utf-8",
            )
            docs, defs = intent.read_docs(d / "docs.tsv")
            self.assertEqual(docs, [("A", "The list is empty.\nIt has no elements."), ("B", "Zero is a number.")])
            self.assertEqual(defs, 1)
            intent.write(d / "out", intent.build(docs, {"A": "idA", "B": "idB"}))
            self.assertEqual(intent.main(["search", str(d / "out"), "empty list", "-k", "1"]), 0)
            stats = json.loads((d / "out" / "intent-stats.json").read_text(encoding="utf-8"))
            self.assertEqual(stats["documents"], 2)


if __name__ == "__main__":
    unittest.main()
