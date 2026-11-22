"""tools/promote/ext_partition.py: the extension entries of each constant go to the layer that holds the constant, and nothing is dropped without a word."""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "promote"))
import ext_partition as E  # noqa: E402

FOUNDATION, ALPHA = "TengaiData.Foundation", "TengaiData.Topic.Alpha"


def layers_dir(root: Path) -> Path:
    d = root / "layers"
    d.mkdir()
    layers = [
        {"module": FOUNDATION, "constants_file": f"{FOUNDATION}.constants.jsonl"},
        {"module": ALPHA, "constants_file": f"{ALPHA}.constants.jsonl"},
    ]
    (d / "layers.json").write_text(json.dumps({"layers": layers}))
    # the foundation holds a class with its constructor and recursor (one unit), an instance and a numbered name; alpha holds a structure and its projection
    (d / f"{FOUNDATION}.constants.jsonl").write_text(
        "".join(json.dumps(c) + "\n" for c in (["Add"], ["Add", "mk"], ["Add", "rec"], ["instAddNat"], ["foo", 7, "bar"]))
    )
    (d / f"{ALPHA}.constants.jsonl").write_text("".join(json.dumps(c) + "\n" for c in (["Pt"], ["Pt", "mk"], ["Pt", "x"])))
    return d


def row(name: list, **kinds) -> str:
    return json.dumps({"n": name, **kinds}, separators=(",", ":")) + "\n"


ROWS = [
    row(["Add"], **{"class": True}),
    row(["Add", "mk"], bi=[[["a"], "default"]]),  # a constructor: not the first name of a unit, it still has a row
    row(["Pt"], st={"fields": [], "parents": []}),
    row(["instAddNat"], inst={"prio": 1000, "kind": "global"}, red="instanceReducible"),
    row(["Pt", "x"], proj={"ctor": ["Pt", "mk"], "np": 0, "i": 0, "cls": False}),
    row(["foo", 7, "bar"], red="reducible"),
]


class Partition(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.owner, self.modules = E.owners(layers_dir(self.root))

    def tearDown(self):
        self._tmp.cleanup()

    def test_each_row_goes_to_the_layer_of_its_constant_even_a_constructor_or_a_numbered_name(self):
        rows, report = E.partition(ROWS, self.owner)
        self.assertEqual(rows[FOUNDATION], [ROWS[0], ROWS[1], ROWS[3], ROWS[5]])
        self.assertEqual(rows[ALPHA], [ROWS[2], ROWS[4]])
        self.assertEqual((report["rows"], report["placed"]), (6, 6))

    def test_the_kinds_are_counted_per_layer_and_in_all(self):
        _, report = E.partition(ROWS, self.owner)
        self.assertEqual(report["layers"][FOUNDATION]["kinds"], {"bi": 1, "class": 1, "inst": 1, "red": 2})
        self.assertEqual(report["layers"][ALPHA]["kinds"], {"proj": 1, "st": 1})
        self.assertEqual(report["kinds"], {"bi": 1, "class": 1, "inst": 1, "proj": 1, "red": 2, "st": 1})

    def test_scoped_instances_are_counted_apart_because_the_replay_registers_them_as_global(self):
        rows = [
            row(["instAddNat"], inst={"prio": 1000, "kind": "scoped"}),
            row(["Add", "mk"], inst={"prio": 1000, "kind": "global"}),
            row(["foo", 7, "bar"], red="reducible"),
        ]
        _, report = E.partition(rows, self.owner)
        self.assertEqual(report["kinds"]["inst"], 2)
        self.assertEqual(report["kinds"]["inst_scoped"], 1)
        self.assertEqual(report["layers"][FOUNDATION]["kinds"]["inst_scoped"], 1)
        _, none = E.partition([ROWS[0]], self.owner)
        self.assertNotIn("inst_scoped", none["kinds"])

    def test_a_row_of_a_constant_no_layer_holds_is_an_error_not_a_loss(self):
        with self.assertRaises(SystemExit) as c:
            E.partition([ROWS[0], row(["Nowhere", "x"], red="reducible")], self.owner)
        self.assertIn("Nowhere.x", str(c.exception))
        self.assertIn("no layer holds", str(c.exception))

    def test_a_line_that_is_not_a_row_is_an_error(self):
        for bad in ("not json\n", json.dumps({"no_name": 1}) + "\n", json.dumps(["a", "b"]) + "\n"):
            with self.assertRaises(SystemExit, msg=bad):
                E.partition([bad], self.owner)

    def test_blank_lines_are_skipped_and_a_last_line_without_a_newline_is_kept_whole(self):
        rows, report = E.partition(["\n", ROWS[0].rstrip("\n")], self.owner)
        self.assertEqual(rows[FOUNDATION], [ROWS[0]])
        self.assertEqual(report["rows"], 1)

    def test_an_empty_file_places_nothing(self):
        rows, report = E.partition([], self.owner)
        self.assertEqual((rows, report["rows"], report["kinds"]), ({}, 0, {}))


class Command(unittest.TestCase):
    def test_files_in_and_out(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            ld = layers_dir(root)
            (root / "ext.jsonl").write_text("".join(ROWS), encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(E.main([str(root / "ext.jsonl"), "--layers", str(ld), "--out", str(root / "ext")]), 0)
            self.assertEqual((root / "ext" / f"{FOUNDATION}.ext.jsonl").read_text(), "".join([ROWS[0], ROWS[1], ROWS[3], ROWS[5]]))
            self.assertEqual((root / "ext" / f"{ALPHA}.ext.jsonl").read_text(), "".join([ROWS[2], ROWS[4]]))
            report = json.loads((root / "ext" / "ext-partition.json").read_text())
        self.assertEqual(report["placed"], 6)
        self.assertIn("6 rows, 6 placed in 2 of 2 layers", out.getvalue())

    def test_a_layer_without_a_row_gets_no_file(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            ld = layers_dir(root)
            (root / "ext.jsonl").write_text(ROWS[0], encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                E.main([str(root / "ext.jsonl"), "--layers", str(ld), "--out", str(root / "ext")])
            self.assertTrue((root / "ext" / f"{FOUNDATION}.ext.jsonl").exists())
            self.assertFalse((root / "ext" / f"{ALPHA}.ext.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
