import hashlib
import io
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "release"))
import pack as K  # noqa: E402


def make(d: Path, payload=b"olean-bytes" * 100):
    (d / "o" / "TengaiData").mkdir(parents=True)
    (d / "o" / "TengaiData" / "Sample.olean").write_bytes(payload)
    manifest = {
        "schema": 1,
        "theorems": [{"name": "A.t"}],
        "artifact": {"olean": {"bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}},
        "checks": {"nanoda": {"status": "ok"}, "kernel": "accepted"},
    }
    (d / "manifest.json").write_text(json.dumps(manifest))
    return manifest


class Pack(unittest.TestCase):
    def test_the_same_inputs_give_the_same_bytes_and_it_verifies(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            make(d)
            a = K.pack(d / "o", d / "manifest.json", d / "a.tar")
            b = K.pack(d / "o", d / "manifest.json", d / "b.tar")
            self.assertEqual(a["sha256"], b["sha256"])
            self.assertEqual(a["members"], ["manifest.json", "TengaiData/Sample.olean"])
            r = K.verify(d / "a.tar", d / "into", a["sha256"])
            self.assertEqual(r["modules"], ["TengaiData/Sample.olean"])
            self.assertEqual(r["lean_path"], str((d / "into").resolve()))
            self.assertEqual(r["checks"], {"kernel": "accepted", "nanoda": "ok"})

    def test_a_wrong_file_hash_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            make(d)
            K.pack(d / "o", d / "manifest.json", d / "a.tar")
            with self.assertRaises(SystemExit):
                K.verify(d / "a.tar", d / "into", "0" * 64)

    def test_an_olean_that_is_not_the_one_in_the_manifest_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            make(d)
            (d / "o" / "TengaiData" / "Sample.olean").write_bytes(b"tampered" * 100)  # the manifest was written for other bytes
            K.pack(d / "o", d / "manifest.json", d / "a.tar")
            with self.assertRaises(SystemExit) as cm:
                K.verify(d / "a.tar", d / "into")
            self.assertIn("differs from the manifest", str(cm.exception))

    def test_a_member_that_escapes_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            with tarfile.open(d / "evil.tar", "w") as t:
                info = tarfile.TarInfo("../outside.txt")
                info.size = 1
                t.addfile(info, io.BytesIO(b"x"))
            with self.assertRaises(SystemExit):
                K.verify(d / "evil.tar", d / "into")
            self.assertFalse((d / "outside.txt").exists())

    def test_a_directory_without_oleans_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "o" / "TengaiData").mkdir(parents=True)
            (d / "manifest.json").write_text("{}")
            with self.assertRaises(SystemExit):
                K.pack(d / "o", d / "manifest.json", d / "a.tar")

    def test_main_pack_then_verify(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            make(d)
            self.assertEqual(
                K.main(["pack", "--olean-dir", str(d / "o"), "--manifest", str(d / "manifest.json"), "--out", str(d / "s.tar")]), 0
            )
            self.assertEqual(K.main(["verify", str(d / "s.tar"), "--into", str(d / "u")]), 0)


if __name__ == "__main__":
    unittest.main()
