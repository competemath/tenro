"""tools/release/notes.py: the gates a snapshot passes before it is released, and the notes and the attribution it is released with."""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "release"))
import notes as N  # noqa: E402

SHA = "ab" * 32

MANIFEST = {
    "schema": 2,
    "flavor": "statements",
    "libraries": ["alpha", "beta"],
    "theorems": [],
    "layers": [{"module": "TengaiData.Foundation"}, {"module": "TengaiData.Topic.Alpha"}],
    "pins": {"tengoku": "1d727eb", "tengai": "v0.0.18"},
    "totals": {"olean_bytes": 3_900_000_000, "constants_added": 612257, "theorems": 311773, "refused": 0},
    "legal": {
        "files": {"ATTRIBUTION.md": {"bytes": 10, "sha256": "c" * 64}, "LICENSES/INDEX.json": {"bytes": 10, "sha256": "d" * 64}},
        "sources": 2,
        "licence_files": 3,
        "problems": 0,
    },
    "attribution": {
        "libraries": {
            "alpha": {"sources": [{"repo": "https://github.com/o/alpha", "commit": "a" * 40, "licence": "Apache-2.0"}], "records": 10},
            "beta": {"sources": [{"repo": "https://github.com/o/beta", "commit": "b" * 40, "licence": "MIT"}], "records": 5},
        },
        "licences": {"Apache-2.0": 1, "MIT": 1},
        "unknown": [],
    },
    "checks": {
        "kernel": "accepted",
        "faithful": {
            "names": 20,
            "compared": 20,
            "statement_stubs": 10,
            "kept_with_value": 2,
            "same_with_value": 4,
            "same_without_value": 4,
            "refused_and_stubbed": 0,
            "absent_in_both": 0,
            "not_asked": 0,
            "problems": {},
            "ok": True,
        },
        "session_load": {
            "cap": 0.25,
            "sets": {"Foundation": {"net_median": 0.017}, "Topic_Alpha": {"net_median": 0.038}, "Combo_All": {"net_median": 0.21}},
        },
    },
}


EXT = {"layers": 2, "reducibility": 11, "projections": 4, "structures": 3, "classes": 2, "instances": 1234, "failed": 0, "ok": True}


class Gates(unittest.TestCase):
    def test_a_faithful_attributed_statements_snapshot_may_be_released(self):
        self.assertEqual(N.gates(MANIFEST), [])

    def test_every_gate_stops_a_release(self):
        cases = {
            "flavor": lambda m: m.update(flavor=None),
            "kernel": lambda m: m["checks"].update(kernel=None),
            "faithful did not run": lambda m: m["checks"].update(faithful=None),
            "faithful found problems": lambda m: m["checks"]["faithful"].update(ok=False, problems={"type_differs": 2}),
            "no attribution": lambda m: m.pop("attribution"),
            "no licence texts": lambda m: m.pop("legal"),
            "a source without a licence text": lambda m: m["legal"].update(problems=2),
            "licence texts of an unknown state": lambda m: m["legal"].update(problems=None),
            "a library without a licence": lambda m: m["attribution"].update(unknown=["beta"]),
        }
        for name, break_it in cases.items():
            m = copy.deepcopy(MANIFEST)
            break_it(m)
            self.assertNotEqual(N.gates(m), [], name)

    def test_extension_entries_that_lean_refused_stop_a_release_and_none_carried_does_not(self):
        m = copy.deepcopy(MANIFEST)
        m["checks"]["extensions"] = dict(EXT, failed=3, ok=False)
        self.assertIn("refused 3 extension entries", " ".join(N.gates(m)))
        m["checks"]["extensions"] = EXT
        self.assertEqual(N.gates(m), [])
        self.assertEqual(N.gates(MANIFEST), [])  # a snapshot without them (checks.extensions absent) is released as constants only

    def test_an_independent_kernel_that_did_not_accept_stops_a_release_and_none_run_does_not(self):
        m = copy.deepcopy(MANIFEST)
        m["checks"]["nanoda"] = {"status": "FAILED", "declarations": None}
        self.assertIn("nanoda", " ".join(N.gates(m)))
        m["checks"]["nanoda"] = {"status": "ok", "declarations": 700_000}
        self.assertEqual(N.gates(m), [])
        self.assertEqual(N.gates(MANIFEST), [])  # it did not run: the notes say so, the release is not stopped

    def test_a_problem_names_what_it_is(self):
        m = copy.deepcopy(MANIFEST)
        m["checks"]["faithful"].update(ok=False, problems={"type_differs": 2})
        self.assertIn("type_differs", " ".join(N.gates(m)))


class Texts(unittest.TestCase):
    def test_the_notes_say_what_it_is_what_was_and_was_not_checked_and_where_it_comes_from(self):
        text = N.notes_md(MANIFEST, "snapshot-2026-11-22", "45000625394", 648_240_378, SHA)
        for needle in (
            "311,773 theorem statements of 2 libraries",
            "axiom of its type",
            "experimental",
            "not a v1",
            "0 refused of 612,257",
            "20 constants compared",
            "the slowest is Topic_Alpha at +0.038 s",  # a combination of topics is not a session
            "What was not checked",
            "independent kernel",
            "ATTRIBUTION.md",
            "Apache-2.0: 1, MIT: 1",
            "3 files of 2 repositories",
            "legal/LICENSES/",
            SHA,
        ):
            self.assertIn(needle, text)
        self.assertNotIn("Combo_All", text)

    def test_the_notes_say_what_extension_entries_it_carries_or_that_it_carries_none(self):
        without = N.notes_md(MANIFEST, "snapshot-x", "1", 100, SHA)
        self.assertIn("constants only, no instances, simp sets, notation or tactics", without)
        self.assertNotIn("extension entries", without)
        m = copy.deepcopy(MANIFEST)
        m["checks"]["extensions"] = EXT
        text = N.notes_md(m, "snapshot-x", "1", 100, SHA)
        self.assertIn("1,234 instances, 2 classes, 3 structures, 4 projection functions, 11 reducibility attributes", text)
        self.assertIn("no simp sets, notation, macros or tactics", text)
        self.assertNotIn("constants only", text)
        self.assertIn("refused by Lean: 0", text)

    def test_the_notes_say_that_an_independent_kernel_accepted_the_layers_and_then_do_not_list_it_as_unchecked(self):
        m = copy.deepcopy(MANIFEST)
        m["checks"]["nanoda"] = {"status": "ok", "declarations": 700_123}
        text = N.notes_md(m, "snapshot-x", "1", 100, SHA)
        self.assertIn("700,123 declarations", text)
        self.assertIn("axiom of its type there", text)
        self.assertNotIn("An independent kernel over the layers", text)
        self.assertIn("What was not checked", text)
        without = N.notes_md(MANIFEST, "snapshot-x", "1", 100, SHA)
        self.assertIn("An independent kernel over the layers", without)
        self.assertNotIn("nanoda", without)

    def test_the_attribution_lists_every_library_with_its_repository_commit_and_licence(self):
        text = N.attribution_md(MANIFEST["attribution"], "snapshot-x")
        self.assertIn("| alpha | [o/alpha](https://github.com/o/alpha) | `aaaaaaaaaaaa` | Apache-2.0 | 10 |", text)
        self.assertIn("| beta | [o/beta](https://github.com/o/beta) | `bbbbbbbbbbbb` | MIT | 5 |", text)
        self.assertIn("each at the commit shown", text)


class Command(unittest.TestCase):
    def run_main(self, manifest: dict, tag: str = "snapshot-2026-11-22", sha: str = SHA) -> tuple[int, Path]:
        d = Path(tempfile.mkdtemp())
        (d / "m.json").write_text(json.dumps(manifest))
        code = N.main(
            [
                "--tag",
                tag,
                "--run",
                "1",
                "--archive-bytes",
                "100",
                "--archive-sha256",
                sha,
                "--out-notes",
                str(d / "n.md"),
                "--out-attribution",
                str(d / "a.md"),
                str(d / "m.json"),
            ]
        )
        return code, d

    def test_a_good_snapshot_writes_the_notes_and_the_attribution(self):
        code, d = self.run_main(MANIFEST)
        self.assertEqual(code, 0)
        self.assertTrue((d / "n.md").read_text().startswith("# snapshot-2026-11-22"))
        self.assertIn("alpha", (d / "a.md").read_text())

    def test_nothing_is_written_when_a_gate_stops_it(self):
        m = copy.deepcopy(MANIFEST)
        m["checks"]["faithful"] = None
        code, d = self.run_main(m)
        self.assertEqual(code, 1)
        self.assertFalse((d / "n.md").exists())
        self.assertFalse((d / "a.md").exists())

    def test_a_tag_that_is_a_version_or_not_a_snapshot_is_refused(self):
        for tag in ("v1.0.0", "v2", "1.0", "snapshot", "snapshot-", "snapshot-a b", "snapshot-" + "x" * 80, "release-1"):
            self.assertEqual(self.run_main(MANIFEST, tag)[0], 1, tag)
        self.assertEqual(self.run_main(MANIFEST, "snapshot-v1")[0], 0)  # a name that merely contains a v

    def test_an_archive_hash_that_is_not_a_sha256_is_refused(self):
        self.assertEqual(self.run_main(MANIFEST, sha="abc")[0], 1)


if __name__ == "__main__":
    unittest.main()
