"""tools/promote/attribution.py: the repository, commit and licence of each library of a snapshot, from Tengoku's intake records and registry."""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "promote"))
import attribution as A  # noqa: E402

C1, C2 = "a" * 40, "b" * 40


def rec(url: str) -> str:
    return json.dumps({"name": "X.t", "source_url": url}) + "\n"


def intake(root: Path) -> Path:
    d = root / "intake"
    (d / "alpha").mkdir(parents=True)
    (d / "alpha" / "manifest.jsonl").write_text(
        rec(f"https://github.com/o/alpha/blob/{C1}/A/Basic.lean") * 2 + rec(f"https://github.com/o/alpha/blob/{C1}/A/More.lean")
    )
    (d / "beta").mkdir()
    (d / "beta" / "manifest.jsonl").write_text(
        rec(f"https://github.com/O/Beta/blob/{C1}/B.lean") + rec(f"https://github.com/O/Beta/blob/{C2}/B.lean")
    )
    (d / "gamma").mkdir()
    (d / "gamma" / "manifest.jsonl").write_text(rec(f"https://github.com/o/gamma/blob/{C2}/G.lean"))
    (d / "notes").mkdir()  # a directory without a manifest is not a library
    return d


LICENCES = {"https://github.com/o/alpha": "Apache-2.0", "https://github.com/o/beta": "MIT"}


class Build(unittest.TestCase):
    def test_each_library_names_its_repository_commit_and_licence(self):
        with tempfile.TemporaryDirectory() as d:
            r = A.build(intake(Path(d)), LICENCES)
        self.assertEqual(sorted(r["libraries"]), ["alpha", "beta", "gamma"])
        self.assertEqual(
            r["libraries"]["alpha"],
            {"sources": [{"repo": "https://github.com/o/alpha", "commit": C1, "licence": "Apache-2.0"}], "records": 3},
        )
        self.assertEqual([s["commit"] for s in r["libraries"]["beta"]["sources"]], [C1, C2])  # two commits of one repository: both named
        self.assertEqual(
            r["libraries"]["beta"]["sources"][0]["licence"], "MIT"
        )  # the registry's key is spelled in another case: GitHub names are not case sensitive

    def test_a_library_without_a_licence_is_unknown_and_not_guessed(self):
        with tempfile.TemporaryDirectory() as d:
            r = A.build(intake(Path(d)), LICENCES)
        self.assertEqual(r["unknown"], ["gamma"])
        self.assertIsNone(r["libraries"]["gamma"]["sources"][0]["licence"])
        self.assertEqual(r["licences"], {"Apache-2.0": 1, "MIT": 1})  # the libraries per licence

    def test_a_library_whose_records_name_no_source_is_unknown(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "intake" / "delta").mkdir(parents=True)
            (root / "intake" / "delta" / "manifest.jsonl").write_text(rec("not a url"))
            r = A.build(root / "intake", LICENCES)
        self.assertEqual((r["unknown"], r["libraries"]["delta"]["sources"], r["libraries"]["delta"]["records"]), (["delta"], [], 1))

    def test_only_the_libraries_asked_for_are_listed(self):
        with tempfile.TemporaryDirectory() as d:
            r = A.build(intake(Path(d)), LICENCES, only={"alpha"})
        self.assertEqual(list(r["libraries"]), ["alpha"])
        self.assertEqual(r["unknown"], [])


class Command(unittest.TestCase):
    def test_main_reads_the_registry_and_the_sample_and_writes_the_report(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            inn = intake(root)
            (root / "sources.json").write_text(json.dumps({"licences": LICENCES, "allowed": []}))
            (root / "sample.jsonl").write_text(
                json.dumps({"name": "X.t", "library": "alpha"}) + "\n" + json.dumps({"name": "Y.t", "library": "gamma"}) + "\n"
            )
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(
                    A.main(
                        [
                            "--intake",
                            str(inn),
                            "--sources",
                            str(root / "sources.json"),
                            "--sample",
                            str(root / "sample.jsonl"),
                            "--out",
                            str(root / "a.json"),
                        ]
                    ),
                    0,
                )
            report = json.loads((root / "a.json").read_text())
        self.assertEqual(sorted(report["libraries"]), ["alpha", "gamma"])
        self.assertIn("UNKNOWN for 1", out.getvalue())


if __name__ == "__main__":
    unittest.main()
