import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "promote"))
import canon_report as C  # noqa: E402

TSV = [
    "violation\tgt-ge\tA.foo\tTengaiData.Foundation",
    "violation\tnot-eq\tA.foo\tTengaiData.Foundation",
    "violation\tgt-ge\tB.bar\tTengaiData.Topic.X",
    "violation\tglobal-instance\tB.instBaz\tTengaiData.Topic.X",
    "violation\tname-theorem\tB.Qux\tTengaiData.Topic.X",
    "not a violation line",
]


class Canon(unittest.TestCase):
    def test_counts_by_rule_by_layer_and_declarations(self):
        r = C.summarize(TSV)
        self.assertEqual(r["violations"], 5)
        self.assertEqual(r["declarations_with_a_violation"], 4)  # A.foo breaks two rules and counts once
        self.assertEqual(r["by_rule"], {"global-instance": 1, "gt-ge": 2, "name-theorem": 1, "not-eq": 1})
        self.assertEqual(r["by_module"], {"TengaiData.Foundation": 2, "TengaiData.Topic.X": 3})
        self.assertEqual(r["examples"]["gt-ge"], ["A.foo", "B.bar"])

    def test_nothing_found_is_a_report_of_zeros(self):
        r = C.summarize([])
        self.assertEqual((r["violations"], r["declarations_with_a_violation"], r["by_rule"]), (0, 0, {}))

    def test_a_layer_is_set_against_the_constants_it_added(self):
        layers = {"layers": [{"module": "TengaiData.Foundation"}, {"module": "TengaiData.Topic.X"}]}
        stats = [{"replay": {"added": 100}}, {"replay": {"added": 20}}]
        added = C.added_by_module(layers, stats)
        self.assertEqual(added, {"TengaiData.Foundation": 100, "TengaiData.Topic.X": 20})
        md = C.markdown(C.summarize(TSV), added)
        self.assertIn("120 constants", md)
        self.assertIn("3.3 %", md)  # 4 of 120
        self.assertIn("| TengaiData.Topic.X | 20 | 3 |", md)
        with self.assertRaises(SystemExit):
            C.added_by_module(layers, stats[:1])  # a plan and statistics that do not match are refused

    def test_main_reads_the_files_and_writes_the_report(self):
        with tempfile.TemporaryDirectory() as d:
            t = Path(d)
            (t / "canon.tsv").write_text("\n".join(TSV) + "\n")
            (t / "layers.json").write_text(json.dumps({"layers": [{"module": "TengaiData.Foundation"}, {"module": "TengaiData.Topic.X"}]}))
            (t / "stats.jsonl").write_text('{"replay": {"added": 100}}\n{"replay": {"added": 20}}\n')
            self.assertEqual(
                C.main(
                    [
                        str(t / "canon.tsv"),
                        "--layers",
                        str(t / "layers.json"),
                        "--layer-stats",
                        str(t / "stats.jsonl"),
                        "--out",
                        str(t / "r.json"),
                    ]
                ),
                0,
            )
            out = json.loads((t / "r.json").read_text())
            self.assertEqual((out["violations"], out["constants_added"]["TengaiData.Foundation"]), (5, 100))


if __name__ == "__main__":
    unittest.main()
