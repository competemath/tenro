"""tools/promote/ext_compare.py: the extension entries of the snapshot against Tengoku's, as the same tool reads them on both sides."""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "promote"))
import ext_compare as E  # noqa: E402


def row(name: list, **kinds) -> dict:
    return {"n": name, **kinds}


def table(*rows: dict) -> dict:
    return {tuple(r["n"]): r for r in rows}


INST = {"prio": 1000, "kind": "global"}
SCOPED = {"prio": 100, "kind": "scoped"}
BI = [[["a"], "default"], [["inst"], "instImplicit"]]

SOURCE = table(
    row(["instAdd"], inst=INST, red="instanceReducible"),
    row(["Pt"], st={"fields": [], "parents": []}, **{"class": True}),
    row(["Pt", "x"], proj={"ctor": ["Pt", "mk"], "np": 0, "i": 0, "cls": False}),
    row(["f"], bi=BI, red="reducible"),
    row(["g", 7], bi=BI),
)


class Compare(unittest.TestCase):
    def test_a_snapshot_that_carries_what_tengoku_carries_has_no_problem(self):
        r = E.compare(SOURCE, dict(SOURCE), "global")
        self.assertTrue(r["ok"])
        self.assertEqual(
            (r["totals"]["same"], r["totals"]["differs"], r["totals"]["lost"], r["totals"]["extra"], r["totals"]["deviation"]),
            (8, 0, 0, 0, 0),
        )
        self.assertEqual(r["kinds"]["inst"], {"same": 1})
        self.assertEqual((r["source_rows"], r["snapshot_rows"]), (5, 5))

    def test_a_lost_entry_is_a_problem_per_kind(self):
        snap = dict(SOURCE)
        snap[("instAdd",)] = row(["instAdd"], red="instanceReducible")  # the instance did not make it
        snap[("Pt", "x")] = row(["Pt", "x"])  # nor the projection (a row with nothing: as if absent)
        r = E.compare(SOURCE, snap, "global")
        self.assertFalse(r["ok"])
        self.assertEqual(r["kinds"]["inst"]["lost"], 1)
        self.assertEqual(r["kinds"]["proj"]["lost"], 1)
        self.assertEqual({e["name"] for e in r["examples"]["lost"]}, {"instAdd", "Pt.x"})

    def test_an_entry_the_snapshot_invented_is_a_problem(self):
        snap = dict(SOURCE)
        snap[("h",)] = row(["h"], red="irreducible")
        r = E.compare(SOURCE, snap, "global")
        self.assertFalse(r["ok"])
        self.assertEqual((r["totals"]["extra"], r["examples"]["extra"][0]["name"]), (1, "h"))

    def test_an_entry_that_says_another_thing_is_a_difference(self):
        snap = dict(SOURCE)
        snap[("f",)] = row(
            ["f"], bi=[[["a"], "implicit"], [["inst"], "instImplicit"]], red="reducible"
        )  # the binder annotation was not restored
        snap[("instAdd",)] = row(["instAdd"], inst={"prio": 500, "kind": "global"}, red="instanceReducible")  # another priority
        r = E.compare(SOURCE, snap, "global")
        self.assertFalse(r["ok"])
        self.assertEqual((r["kinds"]["bi"]["differs"], r["kinds"]["inst"]["differs"]), (1, 1))

    def test_scoped_instances_of_tengoku_in_a_global_snapshot_are_deviations_not_differences(self):
        source = table(row(["Classical", "propDecidable"], inst=SCOPED), row(["instAdd"], inst=INST))
        snap = table(row(["Classical", "propDecidable"], inst={"prio": 100, "kind": "global"}), row(["instAdd"], inst=INST))
        r = E.compare(source, snap, "global")
        self.assertTrue(r["ok"])
        self.assertEqual(r["totals"]["deviation"], 1)
        self.assertEqual(r["deviations"], {"scoped_became_global": 1})
        self.assertEqual(r["examples"]["deviation"][0]["name"], "Classical.propDecidable")

    def test_in_a_scoped_snapshot_the_global_instances_are_the_deviations(self):
        source = table(row(["Classical", "propDecidable"], inst=SCOPED), row(["instAdd"], inst=INST))
        snap = table(
            row(["Classical", "propDecidable"], inst={"prio": 100, "kind": "scoped"}),
            row(["instAdd"], inst={"prio": 1000, "kind": "scoped"}),
        )
        r = E.compare(source, snap, "scoped")
        self.assertTrue(r["ok"])
        self.assertEqual(r["deviations"], {"global_became_scoped": 1})

    def test_a_snapshot_that_registers_the_instances_the_other_way_than_it_says_is_a_difference(self):
        # `--instances global` but the snapshot holds a scoped instance: the replay did not do what the run says it did
        r = E.compare(table(row(["instAdd"], inst=INST)), table(row(["instAdd"], inst={"prio": 1000, "kind": "scoped"})), "global")
        self.assertFalse(r["ok"])
        self.assertEqual(r["kinds"]["inst"]["differs"], 1)

    def test_the_examples_are_limited_and_the_counts_are_not(self):
        n = E.EXAMPLES + 20
        source = table(*[row(["c", i], red="reducible") for i in range(n)])
        r = E.compare(source, {}, "global")
        self.assertEqual(r["totals"]["lost"], n)
        self.assertEqual(len(r["examples"]["lost"]), E.EXAMPLES)

    def test_every_example_says_what_each_side_holds_whatever_its_kind(self):
        # the first run of a whole tree (snapshot-2): 9 differences and 5 losses that were listed by name only, and a binder annotation or a reducibility that differs cannot be judged from a name
        source = table(row(["f"], bi=BI, red="reducible"), row(["g"], bi=BI), row(["only", "src"], red="reducible"))
        snap = table(
            row(["f"], bi=[[["a"], "implicit"], [["inst"], "instImplicit"]], red="reducible"),
            row(["g"], bi=BI),
            row(["only", "snap"], red="irreducible"),
        )
        r = E.compare(source, snap, "global")
        (differs,), (lost,), (extra,) = r["examples"]["differs"], r["examples"]["lost"], r["examples"]["extra"]
        self.assertEqual((differs["name"], differs["kind"]), ("f", "bi"))
        self.assertEqual(differs["detail"], {"source": BI, "snapshot": [[["a"], "implicit"], [["inst"], "instImplicit"]]})
        self.assertEqual((lost["name"], lost["detail"]), ("only.src", {"source": "reducible"}))
        self.assertEqual((extra["name"], extra["detail"]), ("only.snap", {"snapshot": "irreducible"}))

    def test_two_empty_tables_compare_equal_and_a_mode_that_is_not_one_is_refused(self):
        self.assertTrue(E.compare({}, {}, "global")["ok"])
        with self.assertRaises(SystemExit):
            E.compare({}, {}, "both")


class CoreConstants(unittest.TestCase):
    # the first rehearsal (3 libraries, 75,546 entries): ONE entry differed, `instSMulOfMul`, the anonymous instance of Init.Prelude: priority 910 in Lean core, 1100 in Tengoku (a library re-registered it)
    CORE_SRC = table(row(["instSMulOfMul"], inst={"prio": 1100, "kind": "global"}, red="instanceReducible"), row(["f"], red="reducible"))
    CORE_SNAP = table(row(["instSMulOfMul"], inst={"prio": 910, "kind": "global"}, red="instanceReducible"), row(["f"], red="reducible"))

    def test_a_difference_on_a_constant_lean_core_holds_is_reported_apart_and_not_judged(self):
        r = E.compare(self.CORE_SRC, self.CORE_SNAP, "global", added={("f",)})
        self.assertTrue(r["ok"])
        self.assertEqual(r["totals"]["differs"], 0)
        self.assertEqual(
            r["core"], {"constants": 1, "same": 1, "differs": 1, "lost": 0, "extra": 0, "deviation": 0}
        )  # the reducibility of the core constant agrees, its instance does not
        e = r["examples"]["core"][0]
        self.assertEqual((e["name"], e["kind"], e["how"]), ("instSMulOfMul", "inst", "differs"))
        self.assertEqual((e["detail"]["source"]["prio"], e["detail"]["snapshot"]["prio"]), (1100, 910))

    def test_the_same_difference_on_a_constant_the_replay_added_is_a_problem(self):
        r = E.compare(self.CORE_SRC, self.CORE_SNAP, "global", added={("f",), ("instSMulOfMul",)})
        self.assertFalse(r["ok"])
        self.assertEqual((r["totals"]["differs"], r["core"]["constants"]), (1, 0))

    def test_without_the_added_names_every_constant_counts_and_there_is_no_core_section(self):
        r = E.compare(self.CORE_SRC, self.CORE_SNAP, "global")
        self.assertFalse(r["ok"])
        self.assertIsNone(r["core"])

    def test_a_lost_entry_of_a_core_constant_is_counted_apart_too(self):
        r = E.compare(self.CORE_SRC, table(row(["f"], red="reducible")), "global", added={("f",)})
        self.assertTrue(r["ok"])
        self.assertEqual((r["core"]["lost"], r["core"]["same"]), (2, 0))

    def test_an_instance_deviation_of_a_core_constant_is_not_a_deviation_of_the_snapshot(self):
        src = table(row(["Classical", "propDecidable"], inst={"prio": 10, "kind": "scoped"}))
        snap = table(row(["Classical", "propDecidable"], inst={"prio": 10, "kind": "global"}))
        r = E.compare(src, snap, "global", added=set())
        self.assertEqual((r["totals"]["deviation"], r["deviations"], r["core"]["deviation"]), (0, {}, 1))


class Files(unittest.TestCase):
    def write(self, d: Path, name: str, rows) -> Path:
        p = d / name
        p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        return p

    def test_read_refuses_a_line_that_is_not_a_row_and_a_name_twice(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "bad.jsonl").write_text("not json\n")
            with self.assertRaises(SystemExit):
                E.read(d / "bad.jsonl")
            (d / "noname.jsonl").write_text(json.dumps({"red": "reducible"}) + "\n")
            with self.assertRaises(SystemExit):
                E.read(d / "noname.jsonl")
            self.write(d, "twice.jsonl", [row(["a"], red="reducible"), row(["a"], red="irreducible")])
            with self.assertRaises(SystemExit) as c:
                E.read(d / "twice.jsonl")
            self.assertIn("two rows for a", str(c.exception))

    def test_read_added_reads_names_and_refuses_a_line_that_is_not_one(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "a.jsonl").write_text('["a"]\n\n["b", 3, "c"]\n')
            self.assertEqual(E.read_added(d / "a.jsonl"), {("a",), ("b", 3, "c")})
            (d / "bad.jsonl").write_text("nope\n")
            with self.assertRaises(SystemExit):
                E.read_added(d / "bad.jsonl")

    def test_main_with_the_added_names_says_what_it_found_in_lean_cores_constants_and_shows_the_detail(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            src = self.write(d, "s.jsonl", list(CoreConstants.CORE_SRC.values()))
            snap = self.write(d, "t.jsonl", list(CoreConstants.CORE_SNAP.values()))
            (d / "added.jsonl").write_text('["f"]\n')
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(
                    E.main([str(src), str(snap), "--instances", "global", "--added", str(d / "added.jsonl"), "--out", str(d / "r.json")]), 0
                )
            text = out.getvalue()
            self.assertIn("Lean core's own constants (1, left alone by the replay): 1 entries the same, 1 differ", text)
            self.assertIn("core differs: instSMulOfMul (inst)", text)
            self.assertIn('"prio": 910', text)
            self.assertIn("no problem", text)

    def test_main_writes_the_report_and_its_exit_status_is_the_verdict(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            src = self.write(d, "s.jsonl", list(SOURCE.values()))
            same = self.write(d, "t.jsonl", list(SOURCE.values()))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(E.main([str(src), str(same), "--instances", "global", "--out", str(d / "r.json")]), 0)
            self.assertTrue(json.loads((d / "r.json").read_text())["ok"])
            self.assertIn("5 rows in Tengoku, 5 in the snapshot", out.getvalue())
            lost = self.write(d, "u.jsonl", list(SOURCE.values())[:2])
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(E.main([str(src), str(lost), "--instances", "global", "--out", str(d / "r2.json")]), 1)
            self.assertIn("PROBLEMS", out.getvalue())
            self.assertIn("lost: Pt.x (proj)", out.getvalue())
            self.assertIn(
                '"source": {"cls": false, "ctor": ["Pt", "mk"], "i": 0, "np": 0}', out.getvalue()
            )  # what the source holds is printed with the name


if __name__ == "__main__":
    unittest.main()
