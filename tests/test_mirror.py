"""tools/mirror/mirror.py on throwaway git repositories: core/ is exactly a Tengai tag (or the tag plus a registered patch), and anything else is refused."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "mirror"))
import mirror  # noqa: E402

ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
}


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, env=ENV).stdout.strip()


class Mirror(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        d = Path(self._tmp.name)
        self.upstream = d / "tengai"
        self.upstream.mkdir()
        git(self.upstream, "init", "-q", "-b", "main")
        (self.upstream / "Tengai.lean").write_text("-- root\n")
        (self.upstream / "lean-toolchain").write_text("leanprover/lean4:v4.34.0-rc2\n")
        (self.upstream / "Tengai").mkdir()
        (self.upstream / "Tengai" / "A.lean").write_text("theorem a : True := trivial\n")
        git(self.upstream, "add", "-A")
        git(self.upstream, "commit", "-q", "-m", "v0")
        git(self.upstream, "tag", "v0.1")
        self.tenro = d / "tenro"
        (self.tenro / "hyp").mkdir(parents=True)
        (self.tenro / "lean-toolchain").write_text("leanprover/lean4:v4.34.0-rc2\n")
        (self.tenro / "core.lock").write_text(json.dumps({"repo": str(self.upstream), "tag": "v0.1", "tree": "x"}))
        mirror.ROOT, mirror.LOCK, mirror.CORE = self.tenro, self.tenro / "core.lock", self.tenro / "core"
        self.assertEqual(mirror.main(["sync", "v0.1"]), 0)

    def check(self, hyp=None) -> int:
        return mirror.main(["check", *(["--hyp", hyp] if hyp else [])])

    def test_a_fresh_sync_is_the_tag(self):
        self.assertEqual(self.check(), 0)
        lock = json.loads(mirror.LOCK.read_text())
        self.assertEqual(lock["tree"], git(self.upstream, "rev-parse", "v0.1^{tree}"))

    def test_an_edited_file_is_refused(self):
        (mirror.CORE / "Tengai" / "A.lean").write_text("theorem a : True := trivial -- edited\n")
        self.assertEqual(self.check(), 1)

    def test_an_added_file_is_refused(self):
        (mirror.CORE / "Tengai" / "B.lean").write_text("")
        self.assertEqual(self.check(), 1)

    def test_a_deleted_file_is_refused(self):
        (mirror.CORE / "Tengai" / "A.lean").unlink()
        self.assertEqual(self.check(), 1)

    def test_a_file_mode_is_part_of_the_tree(self):
        (mirror.CORE / "Tengai" / "A.lean").chmod(0o755)
        self.assertEqual(self.check(), 1)

    def test_an_ignored_stray_file_is_still_seen(self):
        (mirror.CORE / ".lake").mkdir()
        (mirror.CORE / ".lake" / "junk").write_text("x")
        self.assertEqual(self.check(), 1)

    def test_a_moved_tag_is_refused_until_a_person_syncs_again(self):
        (self.upstream / "Tengai" / "A.lean").write_text("theorem a : True := trivial -- new\n")
        git(self.upstream, "commit", "-q", "-am", "v1")
        git(self.upstream, "tag", "-f", "v0.1")
        self.assertEqual(self.check(), 1)
        self.assertEqual(mirror.main(["sync", "v0.1"]), 0)
        self.assertEqual(self.check(), 0)

    def test_a_toolchain_that_differs_is_refused(self):
        (self.tenro / "lean-toolchain").write_text("leanprover/lean4:v4.99.0\n")
        self.assertEqual(self.check(), 1)

    def hyp(self, name="h1", change=True):
        """a hypothesis: core/ edited, and the patch that makes the same edit to the tag (written from a scratch repository, so its paths are the repository's own)"""
        d = self.tenro / "hyp" / name
        d.mkdir(parents=True)
        (d / "manifest.json").write_text("{}")
        text = "theorem a : True := trivial -- hypothesis\n"
        if change:
            (mirror.CORE / "Tengai" / "A.lean").write_text(text)
        scratch = Path(self._tmp.name) / f"scratch-{name}"
        subprocess.run(["git", "clone", "-q", str(self.upstream), str(scratch)], check=True, env=ENV, capture_output=True)
        (scratch / "Tengai" / "A.lean").write_text(text)
        (d / "core.patch").write_text(git(scratch, "diff") + "\n")
        return d

    def test_a_hypothesis_is_the_tag_plus_its_patch(self):
        self.hyp()
        self.assertEqual(self.check("h1"), 0)
        self.assertEqual(self.check(), 1, "without the hypothesis the same core/ is not the tag")

    def test_a_hypothesis_whose_core_goes_beyond_its_patch_is_refused(self):
        self.hyp()
        (mirror.CORE / "Tengai" / "Extra.lean").write_text("")
        self.assertEqual(self.check("h1"), 1)

    def test_a_patch_that_does_not_apply_stops_the_check(self):
        d = self.hyp()
        (d / "core.patch").write_text("diff --git Nope Nope\n--- Nope\n+++ Nope\n@@ -1 +1 @@\n-a\n+b\n")
        with self.assertRaises(SystemExit):
            self.check("h1")

    def test_the_dry_run_passes_while_the_patch_applies_to_the_current_tengai(self):
        self.hyp()
        self.assertEqual(mirror.main(["dry-run"]), 0)

    def test_the_dry_run_finds_a_patch_that_upstream_has_overtaken(self):
        self.hyp()
        (self.upstream / "Tengai" / "A.lean").write_text("theorem a : True := trivial -- someone else\n")
        git(self.upstream, "commit", "-q", "-am", "v1")
        self.assertEqual(mirror.main(["dry-run"]), 1)

    def test_the_dry_run_with_no_hypothesis_passes(self):
        self.assertEqual(mirror.main(["dry-run"]), 0)

    def test_a_missing_patch_stops_the_check(self):
        with self.assertRaises(SystemExit):
            self.check("nothing")


if __name__ == "__main__":
    unittest.main()
