"""tools/release/use.py: the layers of an unpacked snapshot that a problem needs, and the header that imports them."""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "release"))
import use as U  # noqa: E402

F, A, B, G = "TengaiData.Foundation", "TengaiData.Topic.Aintlib", "TengaiData.Topic.LeanPool", "TengaiData.Group.Seed"


def snapshot(root: Path, with_olean: bool = True) -> Path:
    d = root / "snap"
    layers = [
        {"module": F, "topic": None, "imports": [], "constants": 100},
        {"module": G, "topic": None, "imports": [F], "constants": 10, "group": "Seed"},
        {"module": A, "topic": "aintlib", "imports": [F], "constants": 30},
        {"module": B, "topic": "lean-pool", "imports": [F, G], "constants": 50},
    ]
    (d / "indexes").mkdir(parents=True)
    (d / "manifest.json").write_text(json.dumps({"schema": 2, "layers": layers, "pins": {"tengoku": "abc"}}))
    for m in (F, G, A, B) if with_olean else (F,):
        p = d / U.olean_of(m)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
    rows = [
        {"name": "Nat.add_comm", "library": "aintlib", "layer": A},
        {"name": "Nat.mul_comm", "library": "aintlib", "layer": A},
        {"name": "Real.exp_pos", "library": "lean-pool", "layer": B},
        {"name": "Foo.bar", "library": "aintlib", "layer": F},
    ]
    (d / "indexes" / "layers.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return d


class Plan(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.d = snapshot(Path(self._t.name))

    def tearDown(self):
        self._t.cleanup()

    def test_a_theorem_needs_its_layer_and_the_layers_that_layer_imports_and_nothing_else(self):
        p = U.plan(self.d, ["Nat.add_comm"], [])
        self.assertEqual(p["imports"], [A])
        self.assertEqual(p["loads"], [F, A])
        self.assertEqual(p["constants_loaded"], 130)
        self.assertEqual(p["because"], {A: ["Nat.add_comm"]})

    def test_two_theorems_of_one_layer_are_one_import_and_two_layers_are_two(self):
        self.assertEqual(U.plan(self.d, ["Nat.add_comm", "Nat.mul_comm"], [])["imports"], [A])
        p = U.plan(self.d, ["Nat.add_comm", "Real.exp_pos"], [])
        self.assertEqual(p["imports"], [A, B])
        self.assertEqual(p["loads"], [F, G, A, B])  # a group the topic imports is loaded
        self.assertEqual(p["constants_loaded"], 190)

    def test_a_topic_is_found_by_its_key_or_by_the_name_of_its_module_in_any_spelling(self):
        for name in ("lean-pool", "LeanPool", "leanpool", "lean_pool"):
            self.assertEqual(U.plan(self.d, [], [name])["imports"], [B], name)

    def test_a_theorem_in_the_foundation_needs_the_foundation_alone(self):
        p = U.plan(self.d, ["Foo.bar"], [])
        self.assertEqual((p["imports"], p["loads"]), ([F], [F]))

    def test_an_unknown_theorem_names_the_closest_and_an_unknown_topic_too(self):
        with self.assertRaises(SystemExit) as c:
            U.plan(self.d, ["Nat.add_comn"], [])
        self.assertIn("'Nat.add_comn' (closest: Nat.add_comm", str(c.exception))
        with self.assertRaises(SystemExit) as c:
            U.plan(self.d, [], ["lean-poll"])
        self.assertIn("closest: lean-pool", str(c.exception))

    def test_a_layer_whose_olean_is_not_there_is_refused(self):
        with tempfile.TemporaryDirectory() as t:
            d = snapshot(Path(t), with_olean=False)
            with self.assertRaises(SystemExit) as c:
                U.plan(d, ["Nat.add_comm"], [])
            self.assertIn("is not in", str(c.exception))

    def test_a_directory_that_is_not_an_unpacked_snapshot_is_refused(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(SystemExit):
                U.plan(Path(t), ["x"], [])


class Command(unittest.TestCase):
    def test_main_prints_the_imports_the_layers_loaded_and_the_lean_path_and_writes_the_header(self):
        with tempfile.TemporaryDirectory() as t:
            d = snapshot(Path(t))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(
                    U.main([str(d), "--theorem", "Real.exp_pos", "--theorem", "Nat.add_comm", "--header", str(Path(t) / "h.lean")]), 0
                )
            text = out.getvalue()
            self.assertIn(f"import {A}\nimport {B}\n", text)
            self.assertIn("-- 4 layers, 190 constants loaded", text)
            self.assertIn(f'LEAN_PATH="{d.resolve()}:$(lake env printenv LEAN_PATH)"', text)
            self.assertEqual((Path(t) / "h.lean").read_text(), f"import {A}\nimport {B}\n")

    def test_list_topics_and_asking_for_nothing(self):
        with tempfile.TemporaryDirectory() as t:
            d = snapshot(Path(t))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(U.main([str(d), "--list-topics"]), 0)
            self.assertIn("lean-pool", out.getvalue())
            self.assertIn("50 constants", out.getvalue())
            with self.assertRaises(SystemExit):
                with contextlib.redirect_stderr(io.StringIO()):
                    U.main([str(d)])


if __name__ == "__main__":
    unittest.main()
