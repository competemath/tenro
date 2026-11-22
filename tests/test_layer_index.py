"""tools/promote/layer_index.py: which layer holds the statement of each theorem of a layered snapshot."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "promote"))
import layer_index as L  # noqa: E402

FOUNDATION = "TengaiData.Foundation"
TOPIC_A = "TengaiData.Topic.A"
TOPIC_B = "TengaiData.Topic.B"


def write_layers(d: Path, names: dict[str, list[list]]) -> None:
    """layers.json and the names file of every layer (module -> the names the layer's units start with, as the component arrays layers.py writes)"""
    layers = []
    for module, units in names.items():
        file = f"{module}.names.jsonl"
        (d / file).write_text("".join(json.dumps(u) + "\n" for u in units), encoding="utf-8")
        topic = None if module == FOUNDATION else module.rsplit(".", 1)[-1]
        layers.append({"module": module, "topic": topic, "imports": [] if topic is None else [FOUNDATION], "units": len(units), "constants": len(units), "file": file})
    (d / "layers.json").write_text(json.dumps({"layers": layers, "topics": {}, "totals": {}}), encoding="utf-8")


SAMPLE = [
    {"name": "A.t1", "library": "A", "module": "m"},
    {"name": "A.shared", "library": "A", "module": "m"},
    {"name": "B.t2", "library": "B", "module": "m"},
    {"name": "B.gone", "library": "B", "module": "m"},
]


class Index(unittest.TestCase):
    def layers(self, d: Path) -> None:
        write_layers(
            d,
            {
                FOUNDATION: [["Nat", "foo"], ["A", "shared"], ["Eq"]],
                TOPIC_A: [["A", "t1"], ["A", "helper"]],
                TOPIC_B: [["B", "t2"]],
            },
        )

    def test_a_theorem_is_placed_in_the_layer_whose_unit_starts_with_its_name(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self.layers(d)
            rows, stats = L.build(d, SAMPLE)
        self.assertEqual(
            rows,
            [
                {"name": "A.shared", "library": "A", "layer": FOUNDATION},  # two libraries need it: the foundation
                {"name": "A.t1", "library": "A", "layer": TOPIC_A},
                {"name": "B.t2", "library": "B", "layer": TOPIC_B},
            ],
        )
        self.assertEqual((stats["theorems"], stats["placed"], stats["unplaced"], stats["in_foundation"]), (4, 3, 1, 1))
        self.assertEqual(stats["unplaced_examples"], ["B.gone"])  # counted, never guessed
        self.assertEqual(stats["per_layer"], {FOUNDATION: 1, TOPIC_A: 1, TOPIC_B: 1})

    def test_a_numeric_component_is_written_as_its_digits_as_closure_py_does(self):
        self.assertEqual(L.dotted(["Foo", "_private", 3, "bar"]), "Foo._private.3.bar")

    def test_a_name_that_starts_a_unit_in_two_layers_is_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            write_layers(d, {FOUNDATION: [["A", "t1"]], TOPIC_A: [["A", "t1"]]})
            with self.assertRaises(SystemExit):
                L.build(d, SAMPLE)

    def test_main_writes_the_index_and_its_counts_deterministically(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self.layers(d)
            (d / "sample.jsonl").write_text("".join(json.dumps(r) + "\n" for r in SAMPLE), encoding="utf-8")
            self.assertEqual(L.main(["--layers", str(d), "--sample", str(d / "sample.jsonl"), "--out", str(d / "o1")]), 0)
            self.assertEqual(L.main(["--layers", str(d), "--sample", str(d / "sample.jsonl"), "--out", str(d / "o2")]), 0)
            a = (d / "o1" / "layers.jsonl").read_text(encoding="utf-8")
            self.assertEqual(a, (d / "o2" / "layers.jsonl").read_text(encoding="utf-8"))
            lines = [json.loads(ln) for ln in a.splitlines()]
            self.assertEqual([x["name"] for x in lines], ["A.shared", "A.t1", "B.t2"])  # sorted by name
            stats = json.loads((d / "o1" / "layers-stats.json").read_text(encoding="utf-8"))
            self.assertEqual(len(stats["sha256"]["layers.jsonl"]), 64)
            self.assertEqual(stats["placed"], 3)


if __name__ == "__main__":
    unittest.main()
