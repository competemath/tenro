"""tools/export/export_stats.py: the lines of a lean4export file by kind, and what the export cost."""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "export"))
sys.path.insert(0, str(ROOT / "tests"))
import export_stats as E  # noqa: E402
from test_closure import Builder  # noqa: E402

TIME_LOG = """PANIC at something: a line the exporter printed
\tCommand being timed: "lake env lean4export Tengoku.All --statements"
\tElapsed (wall clock) time (h:mm:ss or m:ss): 1:02:03.50
\tMaximum resident set size (kbytes): 12345678
\tExit status: 0
"""


def small_export(path: Path) -> None:
    """compressed JSON like lean4export's: 3 names (+ the anonymous one is not a line), 1 level, 4 terms in either key order, an axiom, a definition, a theorem"""
    b = Builder()
    b.lines.append({"il": 1, "param": b.name("u")})
    b.decl("axiom", "T", b.sort())
    t = b.const("T")
    b.decl("def", "D", t, b.const("T"))
    b.decl("thm", "lem", t, b.const("D"))
    path.write_text("".join(json.dumps(o, separators=(",", ":")) + "\n" for o in b.lines), encoding="utf-8")


class Counting(unittest.TestCase):
    def test_the_lines_are_counted_by_kind(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "e.ndjson"
            small_export(p)
            s = E.stats(p, label="small")
        self.assertEqual(s["declarations"], {"axiom": 1, "def": 1, "inductive": 0, "opaque": 0, "quot": 0, "thm": 1})
        self.assertEqual(s["terms"], 4)  # sort, const T, const T, const D
        self.assertEqual(s["levels"], 1)
        self.assertEqual(s["names"], 4)  # u, T, D, lem
        self.assertEqual(s["lines"], 13)  # the meta line, 4 names, 1 level, 4 terms, 3 declarations

    def test_the_total_is_the_number_of_lines_of_the_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "e.ndjson"
            small_export(p)
            n = len(p.read_text(encoding="utf-8").splitlines())
            size = p.stat().st_size
            s = E.stats(p)
        self.assertEqual(s["lines"], n)
        self.assertEqual(s["bytes"], size)
        self.assertEqual(
            n, 1 + s["names"] + s["levels"] + s["terms"] + sum(s["declarations"].values())
        )  # the meta line, then every line is of exactly one kind

    def test_without_grep_the_count_is_the_same(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "e.ndjson"
            small_export(p)
            with_grep = E.stats(p)
            with mock.patch.object(E.shutil, "which", return_value=None):
                without = E.stats(p)
        self.assertEqual(with_grep["declarations"], without["declarations"])
        self.assertEqual(
            (with_grep["names"], with_grep["terms"], with_grep["levels"]), (without["names"], without["terms"], without["levels"])
        )
        self.assertIsNone(without["zstd3_bytes"])


class Cost(unittest.TestCase):
    def test_wall_time_and_memory_come_from_the_time_log(self):
        self.assertEqual(E.parse_time_log(TIME_LOG), {"wall_seconds": 3723.5, "max_rss_kb": 12345678})

    def test_a_log_without_the_figures_gives_none(self):
        self.assertEqual(E.parse_time_log("nothing here"), {"wall_seconds": None, "max_rss_kb": None})

    def test_minutes_and_seconds_only(self):
        self.assertEqual(E.parse_time_log("Elapsed (wall clock) time (h:mm:ss or m:ss): 3:22.85\n")["wall_seconds"], 202.85)


class Command(unittest.TestCase):
    def test_it_prints_a_paragraph_and_writes_the_figures(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            small_export(root / "e.ndjson")
            (root / "err.txt").write_text(TIME_LOG, encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = E.main(
                    [
                        str(root / "e.ndjson"),
                        "--time-log",
                        str(root / "err.txt"),
                        "--label",
                        "the tree as statements",
                        "--out",
                        str(root / "s.json"),
                    ]
                )
            stats = json.loads((root / "s.json").read_text(encoding="utf-8"))
        self.assertEqual(code, 0)
        self.assertIn("### the tree as statements", out.getvalue())
        self.assertIn("export 62.1 min, peak 12.3 GB", out.getvalue())
        self.assertEqual(stats["max_rss_kb"], 12345678)
        self.assertEqual(stats["label"], "the tree as statements")


if __name__ == "__main__":
    unittest.main()
