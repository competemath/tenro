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
