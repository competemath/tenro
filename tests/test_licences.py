"""tools/release/licences.py: the licence texts of the libraries of a snapshot, fetched at the commits they were taken from, and what is done when a text is missing or is not the licence the registry says."""

import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "release"))
import licences as L  # noqa: E402

C1, C2 = "a" * 40, "b" * 40

MIT = (
    'MIT License\n\nCopyright (c) 2024 Someone\n\nPermission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal\n'
    "in the Software without restriction.\n\nThe above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.\n"
)
APACHE = "                                 Apache License\n                           Version 2.0, January 2004\n   TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION\n"
BSD3 = "Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:\n3. Neither the name of the copyright holder nor the names of its contributors\n"
GPL = "GNU GENERAL PUBLIC LICENSE\nVersion 3, 29 June 2007\n"


def att(*libs: tuple[str, str, str, str]) -> dict:
    """libs: (key, repo name, commit, licence)"""
    libraries = {
        key: {"sources": [{"repo": f"https://github.com/o/{repo}", "commit": commit, "licence": lic}], "records": 5}
        for key, repo, commit, lic in libs
    }
    return {"libraries": libraries, "licences": {}, "unknown": []}


class Fake:
    """what the two rounds return, from a table"""

    def __init__(self, tree: dict, blobs: dict) -> None:
        self.tree, self.blobs = tree, blobs
        self.read_asked: list = []

    def root_files(self, pairs):
        return {p: self.tree.get(p) for p in pairs}

    def read(self, wanted):
        self.read_asked = list(wanted)
        return {w: self.blobs.get(w) for w in wanted}


def repo(name: str) -> str:
    return f"https://github.com/o/{name}"


class Classify(unittest.TestCase):
    def test_the_standard_texts_are_read_as_what_they_are(self):
        self.assertEqual(L.classify(MIT), {"MIT"})
        self.assertEqual(L.classify(APACHE), {"Apache-2.0"})
        self.assertEqual(L.classify(BSD3), {"BSD-3-Clause"})
        self.assertEqual(L.classify(GPL), set())

    def test_the_reading_does_not_depend_on_line_breaks_or_case(self):
        self.assertEqual(L.classify(MIT.replace(" ", "\n").upper()), {"MIT"})

    def test_a_dual_licence_file_reads_as_both(self):
        self.assertEqual(L.classify(MIT + "\n" + APACHE), {"MIT", "Apache-2.0"})


class Sources(unittest.TestCase):
    def test_two_libraries_of_one_repository_are_one_source(self):
        a = att(("x", "r", C1, "MIT"), ("y", "r", C1, "MIT"), ("z", "s", C2, "Apache-2.0"))
        s = L.sources_of(a)
        self.assertEqual(sorted(s), [(repo("r"), C1), (repo("s"), C2)])
        self.assertEqual(s[(repo("r"), C1)]["libraries"], ["x", "y"])

    def test_a_repository_that_is_not_github_or_a_short_commit_is_refused_before_it_reaches_a_query(self):
        for bad_repo, commit in (
            ("https://example.com/o/r", C1),
            ('https://github.com/o/r"){ x', C1),
            ("https://github.com/o/r", "abc123"),
        ):
            a = att(("x", "r", commit, "MIT"))
            a["libraries"]["x"]["sources"][0]["repo"] = bad_repo
            with self.assertRaises(SystemExit, msg=bad_repo):
                L.sources_of(a)

    def test_one_source_under_two_licences_is_refused(self):
        a = att(("x", "r", C1, "MIT"), ("y", "r", C1, "Apache-2.0"))
        with self.assertRaises(SystemExit):
            L.sources_of(a)


class Fetch(unittest.TestCase):
    def test_only_the_files_named_like_a_licence_or_a_notice_are_read(self):
        a = att(("x", "r", C1, "MIT"))
        tree = {
            (repo("r"), C1): [
                "README.md",
                "LICENSE",
                "LICENSE-APACHE",
                "COPYING.txt",
                "NOTICE",
                "Licence.md",
                "lakefile.toml",
                "licenses",
                'LICENSE"x',
                "license_notes.py",
                "unlicense",
            ]
        }
        hub = Fake(tree, {})
        L.fetch(a, hub)
        names = sorted(n for _, _, n in hub.read_asked)
        self.assertEqual(names, ["COPYING.txt", "LICENSE", "LICENSE-APACHE", "Licence.md", "NOTICE", "license_notes.py", "unlicense"])
        self.assertNotIn('LICENSE"x', names)  # a name outside the safe charset never reaches a query

    def test_at_most_eight_files_per_source(self):
        a = att(("x", "r", C1, "MIT"))
        hub = Fake({(repo("r"), C1): [f"LICENSE-{i}" for i in range(20)]}, {})
        L.fetch(a, hub)
        self.assertEqual(len(hub.read_asked), 8)

    def test_a_binary_or_truncated_file_and_a_missing_repository_leave_nothing(self):
        a = att(("x", "r", C1, "MIT"), ("y", "gone", C2, "MIT"))
        hub = Fake(
            {(repo("r"), C1): ["LICENSE", "NOTICE"], (repo("gone"), C2): None},
            {(repo("r"), C1, "LICENSE"): MIT.encode(), (repo("r"), C1, "NOTICE"): None},
        )
        found = L.fetch(a, hub)
        self.assertEqual(found[(repo("r"), C1)], {"LICENSE": MIT.encode()})
        self.assertIsNone(found[(repo("gone"), C2)])  # not found is not the same as a repository without a licence file


class Problems(unittest.TestCase):
    def test_a_text_that_matches_the_registry_is_not_a_problem(self):
        a = att(("x", "r", C1, "MIT"))
        self.assertEqual(L.problems_of(a, {(repo("r"), C1): {"LICENSE": MIT.encode()}}), [])

    def test_a_dual_licence_passes_when_either_file_matches(self):
        a = att(("x", "r", C1, "MIT"))
        self.assertEqual(L.problems_of(a, {(repo("r"), C1): {"LICENSE-APACHE": APACHE.encode(), "LICENSE-MIT": MIT.encode()}}), [])

    def test_no_file_is_a_problem_and_so_is_a_text_that_is_another_licence_than_the_registry_says(self):
        a = att(("x", "r", C1, "MIT"), ("y", "s", C2, "Apache-2.0"), ("z", "t", C1, "MIT"))
        found = {
            (repo("r"), C1): {},
            (repo("s"), C2): {"LICENSE": GPL.encode()},
            (repo("t"), C1): {"LICENSE": APACHE.encode()},
            (repo("u"), C2): None,
        }
        a["libraries"]["u"] = {"sources": [{"repo": repo("u"), "commit": C2, "licence": "MIT"}], "records": 1}
        problems = {p["repo"]: p for p in L.problems_of(a, found)}
        self.assertIn("no licence file", problems[repo("r")]["problem"])
        self.assertIn("not found", problems[repo("u")]["problem"])
        self.assertEqual(problems[repo("s")]["reads_as"], [])  # a text this does not recognise is a problem, never a guess
        self.assertEqual(problems[repo("t")]["reads_as"], ["Apache-2.0"])
        self.assertEqual(problems[repo("t")]["registry_licence"], "MIT")


class Write(unittest.TestCase):
    def test_the_files_are_kept_byte_for_byte_with_their_hashes_and_the_attribution_is_not_tied_to_a_tag(self):
        a = att(("x", "r", C1, "MIT"), ("y", "r", C1, "MIT"), ("z", "s", C2, "Apache-2.0"))
        found = {
            (repo("r"), C1): {"LICENSE": MIT.encode()},
            (repo("s"), C2): {"LICENSE": APACHE.encode(), "NOTICE": b"Notice\xe2\x80\x94text\n"},
        }
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            index = L.write(out, a, found)
            self.assertEqual((out / "LICENSES" / "o" / f"r@{C1[:12]}" / "LICENSE").read_bytes(), MIT.encode())
            self.assertEqual((out / "LICENSES" / "o" / f"s@{C2[:12]}" / "NOTICE").read_bytes(), b"Notice\xe2\x80\x94text\n")
            self.assertTrue((out / "ATTRIBUTION.md").read_text().startswith("# Where the content of this snapshot comes from"))
            on_disk = json.loads((out / "LICENSES" / "INDEX.json").read_text())
        self.assertEqual(on_disk, index)
        self.assertEqual(index["sources"], 2)
        self.assertEqual(index["files"], 3)
        self.assertEqual(index["problems"], [])
        x = index["libraries"]["x"]["sources"][0]["files"][0]
        self.assertEqual(
            (x["file"], x["bytes"], x["sha256"]), (f"o/r@{C1[:12]}/LICENSE", len(MIT.encode()), hashlib.sha256(MIT.encode()).hexdigest())
        )
        self.assertEqual(
            index["libraries"]["y"]["sources"][0]["files"], index["libraries"]["x"]["sources"][0]["files"]
        )  # two libraries, one repository: the same files

    def test_the_problems_are_in_the_index(self):
        a = att(("x", "r", C1, "MIT"))
        with tempfile.TemporaryDirectory() as d:
            index = L.write(Path(d), a, {(repo("r"), C1): {}})
        self.assertEqual(len(index["problems"]), 1)


class GitHubCalls(unittest.TestCase):
    def test_a_batch_of_repositories_is_one_query_with_an_alias_each_and_the_answer_is_read_back_by_alias(self):
        asked: list[str] = []

        def runner(q: str) -> str:
            asked.append(q)
            if "entries" in q:
                return json.dumps(
                    {
                        "data": {
                            "r0": {"object": {"entries": [{"name": "LICENSE", "type": "blob"}, {"name": "src", "type": "tree"}]}},
                            "r1": None,
                            "r2": {"object": None},
                        }
                    }
                )
            return json.dumps(
                {
                    "data": {
                        "b0": {"object": {"text": "hello", "isBinary": False, "isTruncated": False}},
                        "b1": {"object": {"text": "x", "isBinary": True, "isTruncated": False}},
                    }
                }
            )

        hub = L.GitHub(runner=runner, sleep=lambda s: None)
        out = hub.root_files([(repo("a"), C1), (repo("b"), C1), (repo("c"), C2)])
        self.assertEqual(out, {(repo("a"), C1): ["LICENSE"], (repo("b"), C1): None, (repo("c"), C2): None})  # only blobs are files
        self.assertEqual(len(asked), 1)
        self.assertIn(f'repository(owner: "o", name: "a") {{ object(expression: "{C1}:")', asked[0])
        got = hub.read([(repo("a"), C1, "LICENSE"), (repo("a"), C1, "NOTICE")])
        self.assertEqual(got, {(repo("a"), C1, "LICENSE"): b"hello", (repo("a"), C1, "NOTICE"): None})  # binary: nothing

    def test_batches_of_forty_and_no_more(self):
        asked: list[str] = []

        def runner(q: str) -> str:
            asked.append(q)
            return json.dumps({"data": {}})

        hub = L.GitHub(runner=runner, sleep=lambda s: None)
        hub.root_files([(repo(f"r{i}"), C1) for i in range(85)])
        self.assertEqual([q.count("repository(") for q in asked], [40, 40, 5])

    def test_a_repository_that_is_gone_is_an_answer_beside_the_others_and_any_other_error_is_tried_again(self):
        # found on the live API: `gh api graphql` exits 1 and prints the answer when one alias cannot be resolved
        gone = {
            "data": {"r0": None, "r1": {"object": {"entries": [{"name": "LICENSE", "type": "blob"}]}}},
            "errors": [{"type": "NOT_FOUND", "path": ["r0"], "message": "Could not resolve to a Repository"}],
        }
        hub = L.GitHub(runner=lambda q: json.dumps(gone), sleep=lambda s: None)
        self.assertEqual(hub.root_files([(repo("gone"), C1), (repo("a"), C1)]), {(repo("gone"), C1): None, (repo("a"), C1): ["LICENSE"]})
        waits: list[int] = []
        limited = {"data": {"r0": None}, "errors": [{"type": "RATE_LIMITED", "message": "API rate limit exceeded"}]}
        with self.assertRaises(SystemExit):
            L.GitHub(runner=lambda q: json.dumps(limited), sleep=waits.append).root_files([(repo("a"), C1)])
        self.assertEqual(waits, [0, 5, 20, 60])  # a rate limit is not taken for a missing repository

    def test_a_failed_call_is_tried_again_and_a_dead_api_stops_the_run(self):
        waits: list[int] = []
        calls = {"n": 0}

        def flaky(q: str) -> str:
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("502")
            return json.dumps({"data": {"r0": None}})

        hub = L.GitHub(runner=flaky, sleep=waits.append)
        self.assertEqual(hub.root_files([(repo("a"), C1)]), {(repo("a"), C1): None})
        self.assertEqual(waits, [0, 5, 20])

        def dead(q: str) -> str:
            raise RuntimeError("down")

        with self.assertRaises(SystemExit):
            L.GitHub(runner=dead, sleep=lambda s: None).root_files([(repo("a"), C1)])


class Command(unittest.TestCase):
    def test_main_exits_zero_whatever_the_problems_are_and_says_how_many(self):
        a = att(("x", "r", C1, "MIT"), ("y", "s", C2, "MIT"))
        hub = Fake({(repo("r"), C1): ["LICENSE"], (repo("s"), C2): ["README.md"]}, {(repo("r"), C1, "LICENSE"): MIT.encode()})
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            (out / "att.json").write_text(json.dumps(a))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(L.main([str(out / "att.json"), "--out", str(out / "legal")], hub=hub), 0)
            index = json.loads((out / "legal" / "LICENSES" / "INDEX.json").read_text())
        self.assertIn("2 sources, 1 licence and notice files kept, 1 sources without a text", buf.getvalue())
        self.assertEqual([p["repo"] for p in index["problems"]], [repo("s")])


if __name__ == "__main__":
    unittest.main()
