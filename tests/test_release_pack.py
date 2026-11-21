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


def make_layers(d: Path, tamper: str | None = None):
    """a promotion in layers: a foundation and a topic layer that imports it, under TengaiData/ and TengaiData/Topic/"""
    files = {"TengaiData/Foundation.olean": b"foundation" * 50, "TengaiData/Topic/Aintlib.olean": b"topic" * 30}
    for name, data in files.items():
        p = d / "o" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    layers = [
        {
            "module": "TengaiData.Foundation",
            "imports": [],
            "olean": {
                "bytes": len(files["TengaiData/Foundation.olean"]),
                "sha256": hashlib.sha256(files["TengaiData/Foundation.olean"]).hexdigest(),
            },
        },
        {
            "module": "TengaiData.Topic.Aintlib",
            "imports": ["TengaiData.Foundation"],
            "olean": {
                "bytes": len(files["TengaiData/Topic/Aintlib.olean"]),
                "sha256": hashlib.sha256(files["TengaiData/Topic/Aintlib.olean"]).hexdigest(),
            },
        },
    ]
    if tamper == "imports":
        layers[1]["imports"] = ["TengaiData.Elsewhere"]
    if tamper == "missing":
        layers.append({"module": "TengaiData.Topic.Ghost", "imports": [], "olean": {"bytes": 1, "sha256": "0" * 64}})
    if tamper == "extra":
        layers.pop()
    if tamper == "hash":
        layers[0]["olean"]["sha256"] = "f" * 64
    manifest = {"schema": 2, "theorems": [{"name": "A.t"}], "layers": layers, "checks": {"nanoda": {"status": "ok"}, "kernel": "accepted"}}
    (d / "manifest.json").write_text(json.dumps(manifest))
    return manifest


class PackLayers(unittest.TestCase):
    def roundtrip(self, tamper=None):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            make_layers(d, tamper)
            K.pack(d / "o", d / "manifest.json", d / "s.tar")
            return K.verify(d / "s.tar", d / "into")

    def test_a_promotion_in_layers_packs_and_verifies(self):
        r = self.roundtrip()
        self.assertEqual(r["modules"], ["TengaiData/Foundation.olean", "TengaiData/Topic/Aintlib.olean"])
        self.assertEqual(r["checks"], {"nanoda": "ok", "kernel": "accepted"})

    def test_a_layer_the_snapshot_does_not_hold_is_refused(self):
        with self.assertRaises(SystemExit) as c:
            self.roundtrip("missing")
        self.assertIn("missing ['TengaiData.Topic.Ghost']", str(c.exception))

    def test_a_layer_the_manifest_does_not_list_is_refused(self):
        with self.assertRaises(SystemExit) as c:
            self.roundtrip("extra")
        self.assertIn("not in the manifest ['TengaiData.Topic.Aintlib']", str(c.exception))

    def test_a_layer_that_differs_from_the_manifest_is_refused(self):
        with self.assertRaises(SystemExit) as c:
            self.roundtrip("hash")
        self.assertIn("TengaiData.Foundation differs from the manifest", str(c.exception))

    def test_a_layer_that_imports_what_the_manifest_does_not_list_is_refused(self):
        with self.assertRaises(SystemExit) as c:
            self.roundtrip("imports")
        self.assertIn("TengaiData.Elsewhere", str(c.exception))


INDEXES = {
    "shape.jsonl": b'{"shape": "ab", "ids": ["i1"]}\n',
    "graph.jsonl": b'{"id": "i1", "deps": []}\n',
    "names.jsonl": b'{"id": "i1", "names": ["A.t"]}\n',
}


def make_indexed(d: Path, tamper=None):
    """a promotion in layers whose manifest lists its indexes; `tamper` changes the manifest or the directory after the manifest was written"""
    make_layers(d)
    idx = d / "idx"
    idx.mkdir()
    for name, data in INDEXES.items():
        (idx / name).write_bytes(data)
    m = json.loads((d / "manifest.json").read_text())
    m["indexes"] = {"files": {n: {"bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()} for n, b in INDEXES.items()}}
    if tamper == "unlisted":
        (idx / "intent.jsonl").write_bytes(b"{}\n")
    if tamper == "missing":
        m["indexes"]["files"]["intent.jsonl"] = {"bytes": 3, "sha256": "0" * 64}
    if tamper == "hash":
        m["indexes"]["files"]["shape.jsonl"]["sha256"] = "f" * 64
    (d / "manifest.json").write_text(json.dumps(m))
    return idx


class PackIndexes(unittest.TestCase):
    def roundtrip(self, tamper=None):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            idx = make_indexed(d, tamper)
            packed = K.pack(d / "o", d / "manifest.json", d / "s.tar", idx)
            return packed, K.verify(d / "s.tar", d / "into")

    def test_the_indexes_travel_with_the_layers_and_verify(self):
        packed, r = self.roundtrip()
        self.assertEqual(packed["members"][-3:], ["indexes/graph.jsonl", "indexes/names.jsonl", "indexes/shape.jsonl"])
        self.assertEqual(r["modules"], ["TengaiData/Foundation.olean", "TengaiData/Topic/Aintlib.olean"])

    def test_the_same_inputs_give_the_same_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            idx = make_indexed(d)
            a = K.pack(d / "o", d / "manifest.json", d / "a.tar", idx)
            b = K.pack(d / "o", d / "manifest.json", d / "b.tar", idx)
            self.assertEqual(a["sha256"], b["sha256"])

    def test_an_index_that_differs_from_the_manifest_is_refused(self):
        with self.assertRaises(SystemExit) as c:
            self.roundtrip("hash")
        self.assertIn("the index shape.jsonl differs from the manifest", str(c.exception))

    def test_an_index_the_manifest_does_not_list_is_refused(self):
        with self.assertRaises(SystemExit) as c:
            self.roundtrip("unlisted")
        self.assertIn("not in the manifest ['intent.jsonl']", str(c.exception))

    def test_an_index_the_snapshot_does_not_hold_is_refused(self):
        with self.assertRaises(SystemExit) as c:
            self.roundtrip("missing")
        self.assertIn("missing ['intent.jsonl']", str(c.exception))

    def test_a_snapshot_with_indexes_but_a_manifest_without_them_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            idx = make_indexed(d)
            m = json.loads((d / "manifest.json").read_text())
            del m["indexes"]
            (d / "manifest.json").write_text(json.dumps(m))
            K.pack(d / "o", d / "manifest.json", d / "s.tar", idx)
            with self.assertRaises(SystemExit) as c:
                K.verify(d / "s.tar", d / "into")
            self.assertIn("not in the manifest", str(c.exception))


if __name__ == "__main__":
    unittest.main()
