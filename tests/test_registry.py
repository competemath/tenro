import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "registry"))
import validate as v  # noqa: E402

SID = "eq.0h2v.s4.0123456789ab"
COMMIT = "a" * 40


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def manifest(root: Path, **over) -> dict:
    m = {
        "id": "drop-hyps", "title": "t", "change": "c", "metric": "solved per 1000 steps", "expected_effect": "+2 points", "direction": "improve",
        "sample_size": 400, "margin": 0.01, "protocol_sha256": sha((root / "eval" / "protocol.md").read_bytes()), "core_patch_sha256": None,
        "mirror_hash": "t" * 40, "registered": "2026-11-16", "status": "registered",
    }  # fmt: skip
    return {**m, **over}


def setup(root: Path) -> None:
    (root / "eval").mkdir()
    (root / "eval" / "protocol.md").write_text("protocol v1\n")
    (root / "core.lock").write_text(json.dumps({"tree": "t" * 40}))


class Manifest(unittest.TestCase):
    def test_a_complete_manifest_passes_and_each_defect_is_named(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            setup(root)
            self.assertEqual(v.check_manifest(manifest(root), "drop-hyps", root), [])
            bad = manifest(root, sample_size=0, margin=-1, direction="maybe", status="done", registered="yesterday")
            text = "\n".join(v.check_manifest(bad, "drop-hyps", root))
            for word in ("sample_size", "margin", "direction", "status", "registered"):
                self.assertIn(word, text)
            self.assertIn("directory name", "\n".join(v.check_manifest(manifest(root, id="other"), "drop-hyps", root)))
            self.assertIn("missing", v.check_manifest({"id": "x"}, "x", root)[0])

    def test_no_hypothesis_before_the_protocol(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            setup(root)
            m = manifest(root)
            (root / "eval" / "protocol.md").unlink()
            self.assertIn("before the protocol", "\n".join(v.check_manifest(m, "drop-hyps", root)))

    def test_protocol_patch_and_mirror_hashes_must_match(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            setup(root)
            (root / "hyp" / "drop-hyps").mkdir(parents=True)
            (root / "hyp" / "drop-hyps" / "core.patch").write_text("diff\n")
            text = "\n".join(v.check_manifest(manifest(root), "drop-hyps", root))
            self.assertIn("core.patch exists and core_patch_sha256 is null", text)
            ok = manifest(root, core_patch_sha256=sha(b"diff\n"))
            self.assertEqual(v.check_manifest(ok, "drop-hyps", root), [])
            (root / "eval" / "protocol.md").write_text("protocol v2\n")
            self.assertIn("protocol_sha256", "\n".join(v.check_manifest(ok, "drop-hyps", root)))
            self.assertIn("mirror_hash", "\n".join(v.check_manifest(manifest(root, mirror_hash="x" * 40), "drop-hyps", root)))

    def test_only_status_changes_after_registration(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            setup(root)
            old = manifest(root)
            self.assertEqual(v.check_frozen({**old, "status": "running"}, old, "drop-hyps"), [])
            self.assertEqual(len(v.check_frozen({**old, "sample_size": 10, "margin": 0.5}, old, "drop-hyps")), 2)

    def test_directories_without_a_manifest_are_reported(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            setup(root)
            (root / "hyp" / "empty").mkdir(parents=True)
            self.assertEqual(v.check_hyp(root), ["hyp/empty: no manifest.json"])


class Harvest(unittest.TestCase):
    REC = {"statement_id": SID, "problem_id": "p1", "run_id": "r1", "run_kind": "intake", "kernel_checked": True, "intake_commit": COMMIT}

    def write(self, root: Path, recs: list[dict], name="a.jsonl") -> None:
        p = root / "harvest" / "records"
        p.mkdir(parents=True, exist_ok=True)
        (p / name).write_text("".join(json.dumps(r) + "\n" for r in recs))

    def test_clean_records_pass(self):
        with tempfile.TemporaryDirectory() as d:
            self.write(Path(d), [self.REC])
            self.assertEqual(v.check_harvest(Path(d), {"p9"}), [])
            self.assertEqual(v.check_harvest(Path(d) / "none", None), [])  # no harvest at all, no list needed

    def test_evaluation_runs_and_held_out_problems_are_refused(self):
        with tempfile.TemporaryDirectory() as d:
            self.write(
                Path(d),
                [
                    {**self.REC, "run_kind": "eval"},
                    {**self.REC, "problem_id": "p9", "run_id": "r2"},
                    {**self.REC, "kernel_checked": False, "run_id": "r3"},
                ],
            )
            text = "\n".join(v.check_harvest(Path(d), {"p9"}))
            self.assertIn("only non-evaluation intake runs", text)
            self.assertIn("held out", text)
            self.assertIn("kernel_checked", text)

    def test_records_without_a_held_out_list_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            self.write(Path(d), [self.REC])
            self.assertIn("unchecked harvest", "\n".join(v.check_harvest(Path(d), None)))

    def test_duplicates_and_extra_keys(self):
        with tempfile.TemporaryDirectory() as d:
            self.write(Path(d), [self.REC, self.REC, {**self.REC, "text": "the statement", "run_id": "r2"}])
            text = "\n".join(v.check_harvest(Path(d), set()))
            self.assertIn("duplicate record", text)
            self.assertIn("keys must be exactly", text)

    def test_quarantine_holds_ids_and_a_reason_only(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "harvest").mkdir()
            (root / "harvest" / "quarantine.jsonl").write_text(
                json.dumps({"problem_id": "p9", "run_id": "r1", "reason": "held out"})
                + "\n"
                + json.dumps({"problem_id": "p9", "run_id": "r1", "reason": "x", "statement": "theorem ..."})
                + "\n"
            )
            probs = v.check_harvest(root, set())
            self.assertEqual(len(probs), 1)
            self.assertIn("quarantine.jsonl:2", probs[0])


if __name__ == "__main__":
    unittest.main()
