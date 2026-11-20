import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "campaign"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "common"))
import candidates as K  # noqa: E402


class FakeIsnad:
    """just what candidates.py asks of Tengoku's isnad.py: Record(line), DEPS_TAG, parse_deps_line"""

    DEPS_TAG = "isnad1-deps"

    class Record:
        def __init__(self, line):
            p = line.split("\t")
            self.name, self.module, self.hyps, self.nodes, self.id = p[1], p[2], int(p[3]), int(p[4]), p[5]

    @staticmethod
    def parse_deps_line(line):
        p = line.split("\t")
        return p[1], p[2], p[3:]


def rec(name, module, hyps, nodes, ident):
    return f"isnad1\t{name}\t{module}\t{hyps}\t{nodes}\t{ident}"


def dep(name, module, *ds):
    return "\t".join(["isnad1-deps", name, module, *ds])


class Domains(unittest.TestCase):
    def test_the_area_of_a_module(self):
        self.assertEqual(K.domain_of("Tengoku.Algebra.Group.Basic"), "Algebra")
        self.assertEqual(K.domain_of("Tengoku.Seed.NumberTheory.Padics"), "NumberTheory")
        self.assertEqual(K.domain_of("Tengoku.Aintlib.Foo"), "Aintlib")
        self.assertEqual(K.domain_of("Init.Data.Nat"), "core")
        self.assertEqual(K.domain_of("Tengoku"), "core")


class Library(unittest.TestCase):
    def rows(self):
        records = [
            rec("L.a", "Tengoku.Lib.A", 2, 40, "eq.2h1v.s5.aaaaaaaaaaaa"),
            rec("L.b", "Tengoku.Lib.B", 0, 3, "eq.0h1v.s1.bbbbbbbbbbbb"),
            rec("L.c", "Tengoku.Lib.C", 1, 100, "le.1h2v.s6.cccccccccccc"),
            rec("L.a", "Tengoku.Lib.A2", 2, 40, "eq.2h1v.s5.aaaaaaaaaaaa"),  # a name read twice: one line
        ]
        deps = [
            dep("L.a", "Tengoku.Lib.A", "L.b", "L.c", "Nat.add_comm", "Real.sqrt_pos", "Group.mul_assoc"),
            dep("L.c", "Tengoku.Lib.C", "L.c", "L.b"),  # a theorem does not depend on itself
        ]
        depmod = {
            "Nat.add_comm": "Init.Data.Nat.Basic",
            "Real.sqrt_pos": "Tengoku.Seed.Analysis.SpecialFunctions",
            "Group.mul_assoc": "Tengoku.Algebra.Group.Defs",
        }
        return K.library_candidates(FakeIsnad, "lib", [r for r in records], deps, depmod, {"Tengoku.Lib.A": "2026-08-01"})

    def test_one_line_per_theorem_with_the_numbers_the_selection_uses(self):
        rows = {r["name"]: r for r in self.rows()}
        self.assertEqual(sorted(rows), ["L.a", "L.b", "L.c"])
        a = rows["L.a"]
        self.assertEqual((a["hyps"], a["size"], a["date"], a["library"]), (2, 5, "2026-08-01", "lib"))  # 40 nodes: floor(log2) = 5
        self.assertEqual(a["own_deps"], 2)
        self.assertEqual(a["dep_domains"], ["Algebra", "Analysis", "Lib"])  # core is plumbing; a library's own area counts
        self.assertEqual(rows["L.c"]["own_deps"], 1)
        self.assertIsNone(rows["L.b"]["date"])

    def test_an_unknown_dependency_adds_no_area(self):
        records = [rec("L.a", "Tengoku.Lib.A", 1, 40, "eq.1h1v.s5.aaaaaaaaaaaa")]
        rows = K.library_candidates(FakeIsnad, "lib", records, [dep("L.a", "Tengoku.Lib.A", "Mystery.lemma")], {}, {})
        self.assertEqual(rows[0]["dep_domains"], [])
        self.assertEqual(rows[0]["own_deps"], 0)

    def test_aliases_are_counted_across_libraries(self):
        rows = [{"id": "x", "library": "a"}, {"id": "x", "library": "b"}, {"id": "y", "library": "a"}]
        self.assertEqual([r["aliases"] for r in K.with_aliases(rows)], [1, 1, 0])


class CommandLine(unittest.TestCase):
    def test_the_whole_pipeline_from_tsv_files_to_a_selection(self):
        import heldout as H

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            # a stand-in for Tengoku's isnad.py with the three names candidates.py uses
            (d / "isnad.py").write_text(
                "DEPS_TAG = 'isnad1-deps'\n"
                "class Record:\n"
                "    def __init__(self, line):\n"
                "        p = line.split('\\t')\n"
                "        self.name, self.module, self.hyps, self.nodes, self.id = p[1], p[2], int(p[3]), int(p[4]), p[5]\n"
                "def parse_deps_line(line):\n"
                "    p = line.split('\\t')\n"
                "    return p[1], p[2], p[3:]\n"
            )
            lines = [rec(f"L.t{i}", "Tengoku.Lib.A", 1, 64, f"eq.1h1v.s6.{i:012x}") for i in range(30)]
            (d / "i.tsv").write_text("\n".join(lines) + "\n")
            (d / "d.tsv").write_text("\n".join(dep(f"L.t{i}", "Tengoku.Lib.A", "L.t0", "L.t1") for i in range(2, 30)) + "\n")
            (d / "m.tsv").write_text("")
            self.assertEqual(
                K.main(
                    [
                        "--isnad-py",
                        str(d / "isnad.py"),
                        "--library",
                        "lib",
                        str(d / "i.tsv"),
                        str(d / "d.tsv"),
                        str(d / "m.tsv"),
                        "--out",
                        str(d / "c.jsonl"),
                    ]
                ),
                0,
            )
            cands = [json.loads(x) for x in (d / "c.jsonl").read_text().splitlines()]
            self.assertEqual(len(cands), 30)
            sel = H.select(cands, "2026-07-01", 10, "s", 1.0)
            self.assertEqual(sel["counts"]["dependency-ablation"], 10)
            self.assertEqual(sel["counts"]["post-cutoff"], 0)


if __name__ == "__main__":
    unittest.main()
