"""tools/promote/attribution.py: the repository, commit and licence of each library of a snapshot, from Tengoku's intake records and registry."""

import contextlib
import io
import json
import re
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


class Filter(unittest.TestCase):
    """a whole-tree export that leaves libraries out holds none of their content: the attribution must not name them (the first real one still did, and a library without a licence text would have blocked the release for content that is not there)"""

    def attribution(self):
        with tempfile.TemporaryDirectory() as d:
            return A.build(intake(Path(d)), LICENCES)

    def report(self, *roots):
        return {"excluded": [{"root": r, "why": "requested"} for r in roots]}

    def test_a_root_is_the_registry_library_of_the_same_name_without_hyphens_and_case(self):
        att, gone, unmatched = A.drop_excluded(self.attribution(), self.report("Tengoku.Alpha"))
        self.assertEqual((sorted(att["libraries"]), gone, unmatched), (["beta", "gamma"], ["alpha"], []))

    def test_the_counts_and_the_unknown_list_are_made_again(self):
        before = self.attribution()
        self.assertEqual((before["licences"], before["unknown"]), ({"Apache-2.0": 1, "MIT": 1}, ["gamma"]))
        att, _, _ = A.drop_excluded(before, self.report("Tengoku.Gamma"))
        self.assertEqual(
            (att["licences"], att["unknown"]), ({"Apache-2.0": 1, "MIT": 1}, [])
        )  # the library without a licence is no longer named: nothing blocks for it
        att, _, _ = A.drop_excluded(before, self.report("Tengoku.Alpha"))
        self.assertEqual((att["licences"], att["unknown"]), ({"MIT": 1}, ["gamma"]))

    def test_names_are_compared_without_hyphens_underscores_and_case(self):
        att = {
            "libraries": {"lana-belyi": {"sources": [], "records": 1}, "keep_me": {"sources": [], "records": 1}},
            "licences": {},
            "unknown": ["lana-belyi", "keep_me"],
        }
        out, gone, _ = A.drop_excluded(att, self.report("Tengoku.LanaBelyi"))
        self.assertEqual((list(out["libraries"]), gone, out["unknown"]), (["keep_me"], ["lana-belyi"], ["keep_me"]))

    def test_two_libraries_with_one_name_are_an_error_not_a_guess(self):
        att = {"libraries": {"a-b": {"sources": [], "records": 1}, "ab": {"sources": [], "records": 1}}, "licences": {}, "unknown": []}
        with self.assertRaisesRegex(SystemExit, "cannot be told from what was kept"):
            A.drop_excluded(att, self.report("Tengoku.Ab"))

    def test_a_root_that_matches_no_library_is_reported_and_dropping_twice_changes_nothing(self):
        once, gone, unmatched = A.drop_excluded(self.attribution(), self.report("Tengoku.Alpha", "Tengoku.Nothing"))
        self.assertEqual((gone, unmatched), (["alpha"], ["Tengoku.Nothing"]))
        twice, gone2, unmatched2 = A.drop_excluded(once, self.report("Tengoku.Alpha", "Tengoku.Nothing"))
        self.assertEqual((twice, gone2, unmatched2), (once, [], ["Tengoku.Alpha", "Tengoku.Nothing"]))

    def test_nothing_left_out_leaves_the_attribution_as_it_was(self):
        before = self.attribution()
        att, gone, unmatched = A.drop_excluded(before, {"excluded": []})
        self.assertEqual((att, gone, unmatched), (before, [], []))

    def test_the_real_names_of_the_eight_libraries_of_the_first_run_each_match_one_registry_library(self):
        roots = [
            "LanaBelyi",
            "LanaFormalSchemes",
            "LanaGenl",
            "LanaHeights",
            "LanaOka",
            "LanaOrbicurveCores",
            "LanaTateCurvesTheta",
            "LanaTemperedFundamentalGroups",
        ]
        registry = {"lana-" + "-".join(w.lower() for w in re.findall("[A-Z][a-z]+", r)[1:]): {"sources": [], "records": 1} for r in roots}
        registry.update(
            {
                "lana-iut": {"sources": [], "records": 1},
                "lana-pi1": {"sources": [], "records": 1},
                "lana-elliptic-curves": {"sources": [], "records": 1},
            }
        )
        out, gone, unmatched = A.drop_excluded(
            {"libraries": registry, "licences": {}, "unknown": []}, self.report(*("Tengoku." + r for r in roots))
        )
        self.assertEqual(sorted(out["libraries"]), ["lana-elliptic-curves", "lana-iut", "lana-pi1"])
        self.assertEqual((len(gone), unmatched), (8, []))

    def test_main_filters_a_file_in_place_and_says_what_it_left_out(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "a.json").write_text(json.dumps(self.attribution()))
            (root / "r.json").write_text(json.dumps(self.report("Tengoku.Beta")))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(
                    A.main(["--filter", str(root / "a.json"), "--exclude-report", str(root / "r.json"), "--out", str(root / "a.json")]), 0
                )
            att = json.loads((root / "a.json").read_text())
        self.assertEqual(sorted(att["libraries"]), ["alpha", "gamma"])
        self.assertIn("1 libraries left out (beta), 2 remain", out.getvalue())

    def test_the_filter_needs_the_report_and_the_build_needs_the_intake(self):
        for args in (["--filter", "x.json", "--out", "y.json"], ["--out", "y.json"]):
            with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                A.main(args)


if __name__ == "__main__":
    unittest.main()
