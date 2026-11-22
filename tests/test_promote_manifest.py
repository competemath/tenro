import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "promote"))
import compare_ids as C  # noqa: E402
import manifest as M  # noqa: E402
import pick as P  # noqa: E402

AX = "'A.t1' depends on axioms: [propext, Classical.choice]\n'B.t2' does not depend on any axioms\n"


def cand(name, lib, hyps=1, size=6):
    return {"name": name, "id": f"id.{name}", "library": lib, "module": f"Tengoku.{lib}.M", "hyps": hyps, "size": size}


class PickCandidates(unittest.TestCase):
    def test_every_library_is_in_the_sample_in_turn(self):
        rows = [cand(f"A.t{i}", "A") for i in range(20)] + [cand(f"B.t{i}", "B") for i in range(3)]
        got = P.pick_candidates(rows, ["A", "B"], 6, "s")
        self.assertEqual(len(got), 6)
        self.assertEqual({r["library"] for r in got}, {"A", "B"})
        self.assertEqual(sum(1 for r in got if r["library"] == "B"), 3)  # B runs out after its three
        self.assertEqual(P.pick_candidates(rows, ["A", "B"], 6, "s"), got)  # seeded

    def test_trivial_and_unknown_library_rows_do_not_qualify(self):
        rows = [cand("A.x", "A", hyps=0), cand("A.y", "A", size=3), cand("C.z", "C"), cand("A.ok", "A"), cand("A.ok", "A")]
        got = P.pick_candidates(rows, ["A"], 10, "s")
        self.assertEqual([r["name"] for r in got], ["A.ok"])

    def test_main_writes_names_modules_and_the_sample(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "c.jsonl").write_text("".join(json.dumps(r) + "\n" for r in [cand("A.t", "A"), cand("B.t", "B")]))
            self.assertEqual(
                P.main(
                    [
                        "--candidates",
                        str(d / "c.jsonl"),
                        "--libraries",
                        "A B",
                        "--n",
                        "5",
                        "--seed",
                        "s",
                        "--names",
                        str(d / "n"),
                        "--modules",
                        str(d / "m"),
                        "--sample",
                        str(d / "s.jsonl"),
                    ]
                ),
                0,
            )
            self.assertEqual(sorted((d / "n").read_text().split()), ["A.t", "B.t"])
            rows = [json.loads(x) for x in (d / "s.jsonl").read_text().splitlines()]
            self.assertEqual(sorted(r["id"] for r in rows), ["id.A.t", "id.B.t"])
            self.assertEqual(set(rows[0]), {"name", "id", "library", "module"})


class CompareJsonl(unittest.TestCase):
    def test_source_ids_from_the_sample(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from test_promote_compare import ISNAD_PY, line

            (d / "isnad.py").write_text(ISNAD_PY)
            (d / "names.txt").write_text("T.a\n")
            probe = line("T.a", "c1")  # the id of this record is what the sample must say
            rec_id = "eq.1h1v.c1"
            (d / "sample.jsonl").write_text(json.dumps({"name": "T.a", "id": rec_id, "library": "L", "module": "M"}) + "\n")
            (d / "rep.tsv").write_text(probe + "\n")
            args = [
                "--isnad-py",
                str(d / "isnad.py"),
                "--names",
                str(d / "names.txt"),
                "--source-jsonl",
                str(d / "sample.jsonl"),
                "--replayed",
                str(d / "rep.tsv"),
            ]
            self.assertEqual(C.main(args), 0)
            (d / "sample.jsonl").write_text(json.dumps({"name": "T.a", "id": "other", "library": "L", "module": "M"}) + "\n")
            self.assertEqual(C.main(args), 1)


class Manifest(unittest.TestCase):
    def files(self, d: Path):
        (d / "sample.jsonl").write_text(
            "".join(
                json.dumps(r) + "\n"
                for r in [
                    {"name": "B.t2", "id": "i2", "library": "B", "module": "m"},
                    {"name": "A.t1", "id": "i1", "library": "A", "module": "m"},
                ]
            )
        )
        (d / "replay-stats.json").write_text(json.dumps({"added": 10, "skipped": 2, "inductives": 1}))
        (d / "import-empty.json").write_text(json.dumps({"median": 0.2}))
        (d / "import-sample.json").write_text(json.dumps({"median": 0.25}))
        (d / "nanoda.out").write_text("Checked 77 declarations with no errors\n")
        (d / "nanoda.status").write_text("ok\n")
        (d / "statement-ids.json").write_text(json.dumps({"names": 2, "equal": 2, "ok": True, "different": []}))
        (d / "axioms.txt").write_text(AX)
        (d / "x.ndjson").write_bytes(b"line\n" * 1000)
        (d / "m.olean").write_bytes(b"\x00" * 5000)

    def test_a_complete_transplant(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self.files(d)
            m = M.build(d, d / "x.ndjson", d / "m.olean", {"tengoku": "abc", "core": "v0.0.9"})
            self.assertEqual(m["libraries"], ["A", "B"])
            self.assertEqual([r["name"] for r in m["theorems"]], ["A.t1", "B.t2"])
            self.assertEqual(m["checks"]["kernel"], "accepted")
            self.assertEqual(m["checks"]["nanoda"], {"status": "ok", "declarations": 77})
            self.assertEqual(m["checks"]["cold_import_s"]["net"], 0.05)
            self.assertEqual(
                m["checks"]["axioms"],
                {"theorems": 2, "all_printed": True, "axioms": ["Classical.choice", "propext"], "standard_only": True},
            )
            self.assertEqual(m["artifact"]["olean"]["bytes"], 5000)
            self.assertLess(m["artifact"]["olean"]["gzip_bytes"], 200)  # zeros compress
            self.assertEqual(len(m["artifact"]["export"]["sha256"]), 64)

    def test_a_check_that_did_not_run_is_null_not_true(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "sample.jsonl").write_text(json.dumps({"name": "A.t1", "id": "i1", "library": "A", "module": "m"}) + "\n")
            m = M.build(d, None, None, {})
            self.assertEqual(m["checks"], {"kernel": None, "nanoda": None, "statement_ids": None, "axioms": None, "cold_import_s": None})
            self.assertEqual(m["artifact"], {"export": None, "olean": None})

    def test_the_new_stats_shape_with_extensions(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "sample.jsonl").write_text(json.dumps({"name": "A.t1", "id": "i1", "library": "A", "module": "m"}) + "\n")
            (d / "replay-stats.json").write_text(
                json.dumps(
                    {
                        "replay": {"added": 7, "skipped": 1, "inductives": 0},
                        "ext": {"instances": 3, "classes": 1, "reducibility": 2, "projections": 4},
                    }
                )
            )
            m = M.build(d, None, None, {})
            self.assertEqual(m["replay"], {"added": 7, "skipped": 1, "inductives": 0})
            self.assertEqual(m["extensions"]["instances"], 3)
            self.assertEqual(m["checks"]["kernel"], "accepted")

    def test_a_forbidden_axiom_is_reported(self):
        r = M.axioms_check("'A.t1' depends on axioms: [propext, sorryAx]\n", ["A.t1"])
        self.assertFalse(r["standard_only"])
        self.assertEqual(r["axioms"], ["propext", "sorryAx"])
        self.assertFalse(M.axioms_check("'A.t1' does not depend on any axioms\n", ["A.t1", "A.t2"])["all_printed"])

    def test_names_with_apostrophes_and_wrapped_output(self):
        text = (
            "'Foo.bar'' depends on axioms: [propext, Classical.choice, Quot.sound]\n"
            "'Azurite.A.very_long_name_that_lean_wraps'\ndepends on axioms: [propext,\n Classical.choice,\n Quot.sound]\n"
            "'Baz.q' does not depend on any axioms\n"
        )
        r = M.axioms_check(text, ["Foo.bar'", "Azurite.A.very_long_name_that_lean_wraps", "Baz.q"])
        self.assertEqual(r["theorems"], 3)
        self.assertTrue(r["all_printed"])
        self.assertTrue(r["standard_only"])
        self.assertEqual(r["axioms"], ["Classical.choice", "Quot.sound", "propext"])

    def test_deterministic_output(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self.files(d)
            args = [
                "--dir",
                str(d),
                "--out",
                str(d / "a.json"),
                "--export",
                str(d / "x.ndjson"),
                "--olean",
                str(d / "m.olean"),
                "--pin",
                "z=1",
                "--pin",
                "a=2",
            ]
            self.assertEqual(M.main(args), 0)
            args[3] = str(d / "b.json")
            self.assertEqual(M.main(args), 0)
            self.assertEqual((d / "a.json").read_text(), (d / "b.json").read_text())


if __name__ == "__main__":
    unittest.main()


class ManifestLayers(unittest.TestCase):
    def files(self, d: Path):
        (d / "layers").mkdir()
        (d / "layered" / "TengaiData" / "Topic").mkdir(parents=True)
        (d / "layered" / "TengaiData" / "Foundation.olean").write_bytes(b"f" * 4000)
        (d / "layered" / "TengaiData" / "Topic" / "A.olean").write_bytes(b"a" * 2000)
        plan = {
            "layers": [
                {"module": "TengaiData.Foundation", "topic": None, "imports": [], "units": 10, "constants": 12, "file": "x"},
                {
                    "module": "TengaiData.Topic.A",
                    "topic": "A",
                    "imports": ["TengaiData.Foundation"],
                    "units": 4,
                    "constants": 5,
                    "file": "y",
                },
            ],
            "topics": {"A": {"theorems": 2, "module": "TengaiData.Topic.A"}},
            "totals": {},
        }
        (d / "layers" / "layers.json").write_text(json.dumps(plan))
        (d / "sample.jsonl").write_text(
            "".join(
                json.dumps(r) + "\n"
                for r in [
                    {"name": "A.t1", "id": "i1", "library": "A", "module": "m"},
                    {"name": "A.t2", "id": None, "library": "A", "module": "m"},
                ]
            )
        )
        (d / "layer-stats.jsonl").write_text(
            json.dumps({"ext": {"instances": 3, "failed": 0}, "replay": {"added": 9, "skipped": 3}})
            + "\n"
            + json.dumps({"ext": {"instances": 1, "failed": 0}, "replay": {"added": 5, "skipped": 0}})
            + "\n"
        )
        (d / "nanoda-layers.status").write_text("ok\n")
        (d / "nanoda-layers.out").write_text("Checked 123 declarations with no errors\n")
        (d / "statement-ids-layers.json").write_text(
            json.dumps({"names": 2, "equal": 1, "ok": True, "no_source_id": 1, "different": [], "drift": []})
        )
        (d / "layers-axioms.txt").write_text("'A.t1' depends on axioms: [propext]\n'A.t2' does not depend on any axioms\n")
        (d / "layers-load.json").write_text(
            json.dumps(
                {
                    "rows": [
                        ["Foundation", 0.4, {"median": 0.3, "net_median": 0.06, "net_min": 0.05}],
                        ["Topic_A", 0.6, {"median": 0.32, "net_median": 0.08, "net_min": 0.07}],
                    ],
                    "empty": {"min": 0.2, "median": 0.24},
                }
            )
        )

    def test_a_promotion_in_layers_is_recorded_layer_by_layer(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self.files(d)
            m = M.build_layers(d, d / "layered", {"tengoku": "abc"})
            self.assertEqual(m["schema"], 2)
            self.assertEqual([x["module"] for x in m["layers"]], ["TengaiData.Foundation", "TengaiData.Topic.A"])
            self.assertEqual([x["theorems"] for x in m["layers"]], [0, 2])
            self.assertEqual([x["olean"]["bytes"] for x in m["layers"]], [4000, 2000])
            self.assertEqual(m["totals"], {"olean_bytes": 6000, "constants_added": 14, "theorems": 2})
            self.assertEqual(m["layers"][0]["extensions"], {"instances": 3, "failed": 0})
            self.assertEqual(m["checks"]["kernel"], "accepted")
            self.assertEqual(m["checks"]["nanoda"], {"status": "ok", "declarations": 123})
            self.assertEqual(m["checks"]["statement_ids"]["no_source_id"], 1)
            self.assertEqual(
                m["checks"]["session_load"]["sets"]["Topic_A"], {"olean_mb": 0.6, "median": 0.32, "net_median": 0.08, "net_min": 0.07}
            )
            self.assertNotIn("cap", m["checks"]["session_load"])  # a promotion measured before the cap was recorded has none
            self.assertTrue(m["checks"]["axioms"]["standard_only"])

    def test_the_extension_entries_are_summed_over_the_layers_that_carried_them_and_an_entry_lean_refused_is_not_ok(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self.files(d)
            m = M.build_layers(d, d / "layered", {"tengoku": "abc"})
            self.assertEqual(
                m["checks"]["extensions"],
                {"layers": 2, "reducibility": 0, "projections": 0, "structures": 0, "classes": 0, "instances": 4, "failed": 0, "ok": True},
            )
            (d / "layer-stats.jsonl").write_text(
                json.dumps({"ext": {"instances": 3, "classes": 2, "failed": 0}, "replay": {"added": 9, "skipped": 3}})
                + "\n"
                + json.dumps({"ext": {"reducibility": 7, "failed": 2}, "replay": {"added": 5, "skipped": 0}})
                + "\n"
            )
            e = M.build_layers(d, d / "layered", {"tengoku": "abc"})["checks"]["extensions"]
            self.assertEqual((e["instances"], e["classes"], e["reducibility"], e["failed"], e["ok"]), (3, 2, 7, 2, False))
            (d / "layer-stats.jsonl").write_text(
                json.dumps({"ext": None, "replay": {"added": 9}}) + "\n" + json.dumps({"ext": None, "replay": {"added": 5}}) + "\n"
            )
            self.assertIsNone(
                M.build_layers(d, d / "layered", {"tengoku": "abc"})["checks"]["extensions"]
            )  # no layer carried any: null, not zero

    def test_the_licence_texts_are_recorded_with_their_hashes_and_what_the_writer_found_and_absent_means_absent(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self.files(d)
            legal = d / "legal"
            (legal / "LICENSES" / "o").mkdir(parents=True)
            (legal / "ATTRIBUTION.md").write_text("# a\n")
            (legal / "LICENSES" / "o" / "LICENSE").write_text("MIT\n")
            (legal / "LICENSES" / "INDEX.json").write_text(json.dumps({"sources": 3, "files": 5, "problems": [{"repo": "x"}]}))
            m = M.build_layers(d, d / "layered", {"tengoku": "abc"}, legal=legal)
            self.assertEqual(sorted(m["legal"]["files"]), ["ATTRIBUTION.md", "LICENSES/INDEX.json", "LICENSES/o/LICENSE"])
            self.assertEqual(m["legal"]["files"]["LICENSES/o/LICENSE"]["bytes"], 4)
            self.assertEqual((m["legal"]["sources"], m["legal"]["licence_files"], m["legal"]["problems"]), (3, 5, 1))
            self.assertNotIn(
                "legal", M.build_layers(d, d / "layered", {"tengoku": "abc"})
            )  # none given: none recorded, never an empty record
            (legal / "LICENSES" / "INDEX.json").write_text(json.dumps({"sources": 3, "files": 5, "problems": []}))
            self.assertEqual(M.build_layers(d, d / "layered", {"tengoku": "abc"}, legal=legal)["legal"]["problems"], 0)
            (legal / "LICENSES" / "INDEX.json").unlink()
            self.assertIsNone(
                M.build_layers(d, d / "layered", {"tengoku": "abc"}, legal=legal)["legal"]["problems"]
            )  # an index that is not there says nothing: not zero

    def test_main_takes_the_legal_directory(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self.files(d)
            (d / "legal").mkdir()
            (d / "legal" / "ATTRIBUTION.md").write_text("# a\n")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    M.main_layers(
                        ["--dir", str(d), "--layered", str(d / "layered"), "--out", str(d / "m.json"), "--legal", str(d / "legal")]
                    ),
                    0,
                )
            self.assertEqual(list(json.loads((d / "m.json").read_text())["legal"]["files"]), ["ATTRIBUTION.md"])
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self.files(d)
            (d / "empty").mkdir()
            with self.assertRaises(SystemExit):
                M.build_layers(d, d / "layered", {}, legal=d / "empty")

    def test_a_statements_snapshot_records_its_flavor_counts_what_was_refused_and_lists_no_theorems(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self.files(d)
            (d / "layer-stats.jsonl").write_text(
                json.dumps({"ext": None, "replay": {"added": 9, "skipped": 3, "refused": []}})
                + "\n"
                + json.dumps({"ext": None, "replay": {"added": 5, "skipped": 0, "refused": ["A.weird", "A.odd"]}})
                + "\n"
            )
            (d / "layers-load.json").write_text(
                json.dumps(
                    {
                        "rows": [["Foundation", 0.4, {"median": 0.3, "net_median": 0.06, "net_min": 0.05, "constants": 12}]],
                        "empty": {"min": 0.2, "median": 0.24},
                    }
                )
            )
            m = M.build_layers(d, d / "layered", {"tengoku": "abc"}, flavor="statements")
            self.assertEqual(m["flavor"], "statements")
            self.assertEqual(m["theorems"], [])  # the table of which layer holds which theorem is the layers index
            self.assertEqual(m["totals"]["theorems"], 2)  # the count stays
            self.assertEqual(m["totals"]["refused"], 2)
            self.assertEqual(m["libraries"], ["A"])
            self.assertEqual(m["checks"]["session_load"]["sets"]["Foundation"]["constants"], 12)
            plain = M.build_layers(d, d / "layered", {"tengoku": "abc"})
            self.assertNotIn("flavor", plain)  # a proofs promotion is recorded as before
            self.assertNotIn("refused", plain["totals"])
            self.assertEqual(len(plain["theorems"]), 2)

    def test_main_takes_the_flavor_and_the_layers_index_stats_are_recorded_with_the_indexes(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self.files(d)
            idx = d / "idx"
            idx.mkdir()
            (idx / "layers.jsonl").write_text('{"name": "A.t1", "library": "A", "layer": "TengaiData.Topic.A"}\n')
            (idx / "layers-stats.json").write_text(json.dumps({"placed": 1, "unplaced": 0, "sha256": {"layers.jsonl": "x"}}))
            args = [
                "layers",
                "--dir",
                str(d),
                "--layered",
                str(d / "layered"),
                "--out",
                str(d / "a.json"),
                "--pin",
                "tengoku=abc",
                "--indexes",
                str(idx),
                "--flavor",
                "statements",
            ]
            self.assertEqual(M.main(args), 0)
            m = json.loads((d / "a.json").read_text())
            self.assertEqual(m["flavor"], "statements")
            self.assertEqual(m["indexes"]["layers"], {"placed": 1, "unplaced": 0})
            self.assertEqual(sorted(m["indexes"]["files"]), ["layers-stats.json", "layers.jsonl"])

    def test_the_faithfulness_check_is_recorded_when_it_ran_and_null_when_it_did_not(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self.files(d)
            self.assertIsNone(
                M.build_layers(d, d / "layered", {}, flavor="statements")["checks"]["faithful"]
            )  # it did not run: null, never true
            report = {
                "names": 10,
                "not_asked": 2,
                "compared": 8,
                "absent_in_both": 0,
                "statement_stubs": 5,
                "kept_with_value": 1,
                "same_with_value": 1,
                "same_without_value": 1,
                "refused_and_stubbed": 0,
                "by_kind": {"thm->axiom": 5},
                "problems": {},
                "problem_counts": {},
                "passed": True,
            }
            (d / "faithful.json").write_text(json.dumps(report))
            f = M.build_layers(d, d / "layered", {}, flavor="statements")["checks"]["faithful"]
            self.assertEqual((f["names"], f["compared"], f["statement_stubs"], f["kept_with_value"], f["not_asked"]), (10, 8, 5, 1, 2))
            self.assertEqual((f["problems"], f["ok"]), ({}, True))
            report.update({"passed": False, "problem_counts": {"type_differs": 3}})
            (d / "faithful.json").write_text(json.dumps(report))
            f = M.build_layers(d, d / "layered", {}, flavor="statements")["checks"]["faithful"]
            self.assertEqual((f["problems"], f["ok"]), ({"type_differs": 3}, False))

    def test_the_cap_the_sessions_were_judged_against_is_recorded_when_the_run_wrote_it(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self.files(d)
            load = json.loads((d / "layers-load.json").read_text())
            load["cap"] = 0.25
            (d / "layers-load.json").write_text(json.dumps(load))
            self.assertEqual(M.build_layers(d, d / "layered", {})["checks"]["session_load"]["cap"], 0.25)

    def test_the_attribution_is_recorded_when_there_is_one(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self.files(d)
            self.assertNotIn("attribution", M.build_layers(d, d / "layered", {}))
            att = {
                "libraries": {"A": {"sources": [{"repo": "https://github.com/o/a", "commit": "c" * 40, "licence": "MIT"}], "records": 2}},
                "licences": {"MIT": 1},
                "unknown": [],
            }
            (d / "attribution.json").write_text(json.dumps(att))
            self.assertEqual(M.build_layers(d, d / "layered", {})["attribution"], att)

    def test_the_manifest_is_the_same_for_the_same_inputs_and_main_writes_it(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self.files(d)
            args = ["layers", "--dir", str(d), "--layered", str(d / "layered"), "--out", str(d / "a.json"), "--pin", "tengoku=abc"]
            self.assertEqual(M.main(args), 0)
            self.assertEqual(M.main([*args[:-4], "--out", str(d / "b.json"), "--pin", "tengoku=abc"]), 0)
            self.assertEqual((d / "a.json").read_text(), (d / "b.json").read_text())

    def indexes(self, d: Path) -> Path:
        idx = d / "idx"
        idx.mkdir()
        (idx / "shape.jsonl").write_text('{"shape": "ab", "ids": ["i1"]}\n')
        (idx / "graph.jsonl").write_text('{"id": "i1", "deps": []}\n')
        (idx / "stats.json").write_text(json.dumps({"statements": 1, "sha256": {"shape.jsonl": "x"}}))
        (idx / "intent-stats.json").write_text(json.dumps({"documents": 3, "tokens": 40, "sha256": {"intent.jsonl": "y"}}))
        return idx

    def test_the_indexes_are_recorded_with_their_hashes_and_the_counts_the_builders_wrote(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self.files(d)
            m = M.build_layers(d, d / "layered", {"tengoku": "abc"}, self.indexes(d))
            idx = m["indexes"]
            self.assertEqual(sorted(idx["files"]), ["graph.jsonl", "intent-stats.json", "shape.jsonl", "stats.json"])
            self.assertEqual(idx["files"]["shape.jsonl"]["bytes"], len('{"shape": "ab", "ids": ["i1"]}\n'))
            self.assertEqual(len(idx["files"]["shape.jsonl"]["sha256"]), 64)
            self.assertEqual(
                (idx["build"], idx["intent"]), ({"statements": 1}, {"documents": 3, "tokens": 40})
            )  # the hashes of the builders are in `files`, not twice
            self.assertNotIn("indexes", M.build_layers(d, d / "layered", {"tengoku": "abc"}))  # without a directory: no record
            empty = d / "empty"
            empty.mkdir()
            with self.assertRaises(SystemExit):
                M.build_layers(d, d / "layered", {}, empty)  # a directory without a file is not an index

    def test_main_takes_the_indexes_directory(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self.files(d)
            idx = self.indexes(d)
            args = [
                "layers",
                "--dir",
                str(d),
                "--layered",
                str(d / "layered"),
                "--out",
                str(d / "a.json"),
                "--pin",
                "tengoku=abc",
                "--indexes",
                str(idx),
            ]
            self.assertEqual(M.main(args), 0)
            self.assertIn("indexes", json.loads((d / "a.json").read_text()))

    def test_a_layer_without_its_olean_is_an_error_and_a_check_that_did_not_run_is_null(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self.files(d)
            (d / "layered" / "TengaiData" / "Topic" / "A.olean").unlink()
            with self.assertRaises(SystemExit):
                M.build_layers(d, d / "layered", {})
            (d / "layered" / "TengaiData" / "Topic" / "A.olean").write_bytes(b"a")
            (d / "nanoda-layers.status").unlink()
            (d / "layers-load.json").unlink()
            m = M.build_layers(d, d / "layered", {})
            self.assertIsNone(m["checks"]["nanoda"])
            self.assertIsNone(m["checks"]["session_load"])
