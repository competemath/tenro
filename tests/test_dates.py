import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "campaign"))
import dates as D  # noqa: E402


def git(cwd, *args, when=None):
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
    }
    if when:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = when
    subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True)


def write(root, rel, text="theorem x : True := trivial\n"):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


class FileOf(unittest.TestCase):
    FILES = {"Lib/Algebra/Basic.lean", "Lib/Number/Basic.lean", "Lib/Top.lean", "Other/Top.lean", "Lib/Deep/Only.lean"}

    def test_the_longest_unique_suffix(self):
        self.assertEqual(D.file_of("Tengoku.L.Lib.Algebra.Basic", "L", self.FILES), "Lib/Algebra/Basic.lean")
        self.assertEqual(D.file_of("Tengoku.L.Deep.Only", "L", self.FILES), "Lib/Deep/Only.lean")  # the root was dropped by the copy

    def test_an_ambiguous_module_has_no_file(self):
        self.assertIsNone(D.file_of("Tengoku.L.Top", "L", self.FILES))

    def test_a_module_of_another_library_or_unknown_has_none(self):
        self.assertIsNone(D.file_of("Tengoku.M.Lib.Top", "L", self.FILES))
        self.assertIsNone(D.file_of("Tengoku.L.Nope", "L", self.FILES))


class Log(unittest.TestCase):
    def test_earliest_add_wins_and_root_commits_are_left_out(self):
        text = "\n".join(
            [
                "@aaa\t2025-01-01T00:00:00+00:00\t",  # root commit
                "Old.lean",
                "@bbb\t2026-08-02T10:00:00+00:00\tbbb0",
                "New.lean",
                "@ccc\t2026-09-09T10:00:00+00:00\tbbb",
                "New.lean",  # added again later: the earlier date stays
                "notes.md",
            ]
        )
        self.assertEqual(D.parse_log(text), {"New.lean": "2026-08-02"})


class RealRepo(unittest.TestCase):
    def test_dates_from_a_real_history_and_renames_stay_undated(self):
        with tempfile.TemporaryDirectory() as d:
            up, work = Path(d) / "up", Path(d)
            up.mkdir()
            git(up, "init", "-q", "-b", "main")
            write(up, "Lib/Root.lean")
            git(up, "add", "-A")
            git(up, "commit", "-q", "-m", "import", when="2024-03-01T12:00:00")
            write(up, "Lib/Basic.lean", "theorem b : True := trivial\n")
            git(up, "add", "-A")
            git(up, "commit", "-q", "-m", "basic", when="2026-08-05T12:00:00")
            git(up, "mv", "Lib/Basic.lean", "Lib/Moved.lean")
            git(up, "commit", "-q", "-m", "rename", when="2026-09-05T12:00:00")
            write(up, "Lib/Fresh.lean")
            git(up, "add", "-A")
            git(up, "commit", "-q", "-m", "fresh", when="2026-10-10T12:00:00")
            commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=up, capture_output=True, text=True).stdout.strip()
            log = D.git("log", commit, "-M", "--diff-filter=A", "--name-only", "--format=@%H%x09%aI%x09%P", cwd=up)
            files = {f for f in D.git("ls-tree", "-r", "--name-only", commit, cwd=up).splitlines() if f.endswith(".lean")}
            got = D.module_dates(["Tengoku.L.Lib.Root", "Tengoku.L.Lib.Moved", "Tengoku.L.Lib.Fresh"], "L", log, files)
            self.assertEqual(got, {"Tengoku.L.Lib.Fresh": "2026-10-10"})  # root commit: none; renamed: none (a rename is not an add)
            self.assertEqual(work, Path(d))

    def test_main_writes_the_table(self):
        import json

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            up = d / "up"
            up.mkdir()
            git(up, "init", "-q", "-b", "main")
            write(up, "A.lean")
            git(up, "add", "-A")
            git(up, "commit", "-q", "-m", "root", when="2024-01-01T00:00:00")
            write(up, "Lib/New.lean")
            git(up, "add", "-A")
            git(up, "commit", "-q", "-m", "new", when="2026-08-08T00:00:00")
            commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=up, capture_output=True, text=True).stdout.strip()
            (d / "sources.json").write_text(json.dumps({"corpora": {"my-lib": {"repo": str(up), "commit": commit}}}))
            (d / "mods.txt").write_text("Tengoku.MyLib.Lib.New\nTengoku.MyLib.Lib.Missing\n")
            self.assertEqual(
                D.main(
                    [
                        "--sources",
                        str(d / "sources.json"),
                        "--library",
                        "MyLib",
                        "--modules",
                        str(d / "mods.txt"),
                        "--out",
                        str(d / "out.tsv"),
                        "--workdir",
                        str(d / "w"),
                    ]
                ),
                0,
            )
            self.assertEqual((d / "out.tsv").read_text(), "Tengoku.MyLib.Lib.New\t2026-08-08\n")

    def test_no_corpus_means_no_dates_and_two_stop(self):
        self.assertIsNone(D.corpus_of({"corpora": {}}, "Nope"))
        with self.assertRaises(SystemExit):
            D.corpus_of({"corpora": {"a": {"repo": "r", "commit": "c"}, "A": {"repo": "r2", "commit": "c2"}}}, "a")


if __name__ == "__main__":
    unittest.main()
