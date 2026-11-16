import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "calibration"))
import thresholds as T  # noqa: E402
import waypoints as W  # noqa: E402


def pair(a, b, label, df=None, dw=None):
    p = {"a": a, "b": b, "label": label, "rule": "x", "jaccard": 0, "borderline": False}
    if df is not None:
        p["df"] = df
    if dw is not None:
        p["dw"] = dw
    return p


class Thresholds(unittest.TestCase):
    def groups(self):
        return [
            {"id": "g1", "pairs": [pair("A", "B", "alias", 0.1, 0.2), pair("A", "C", "independent", 0.9, 0.8)]},
            {"id": "g2", "pairs": [pair("D", "E", "alias", 0.3, 0.1), pair("F", "G", "similar", 0.5, 0.5), pair("H", "I", "alias", 0.2)]},
        ]

    def test_pairs_need_both_axes_and_the_count_of_the_rest_is_reported(self):
        pairs, skipped = T.pairs_of(self.groups(), [])
        self.assertEqual((len(pairs), skipped), (4, 1))

    def test_a_human_label_replaces_the_rule_label_of_that_pair_only(self):
        pairs, _ = T.pairs_of(self.groups(), [{"a": "C", "b": "A", "label": "similar", "reason": "x"}])
        self.assertEqual([lab for _, _, lab in pairs], ["alias", "similar", "alias", "similar"])

    def test_the_cli_prints_feasible_thresholds(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "labels.jsonl"
            f.write_text("".join(json.dumps(g) + "\n" for g in self.groups()))
            self.assertEqual(T.main([str(f)]), 0)
            self.assertEqual(T.main([]), 2)


class Waypoints(unittest.TestCase):
    sets = staticmethod(lambda lines: {"A.t": ["id1", "id2"]} if lines else {})

    def test_records_get_their_waypoints_and_a_missing_theorem_stays_unknown_unless_complete(self):
        recs = [{"name": "A.t"}, {"name": "B.u"}]
        got = W.merge(recs, ["isnad1-have\tA.t\tM"], self.sets, assume_complete=False)
        self.assertEqual(got[0]["waypoints"], ["id1", "id2"])
        self.assertNotIn("waypoints", got[1])
        got = W.merge(recs, ["isnad1-have\tA.t\tM"], self.sets, assume_complete=True)
        self.assertEqual(got[1]["waypoints"], [])

    def test_label_pairs_carry_both_axes_when_both_records_have_waypoints(self):
        import label

        P = label.load_params(Path(__file__).resolve().parents[1] / "calibration" / "protocol.toml")
        a = {
            "id": "s",
            "name": "A.t",
            "lib": "L1",
            "closure": [f"x{i}" for i in range(9)],
            "statement_closure": [],
            "modules": {},
            "waypoints": ["w1", "w2"],
        }
        b = {**a, "name": "B.u", "lib": "L2", "closure": [f"y{i}" for i in range(9)], "waypoints": ["w2", "w3"]}
        r = label.label_pair(a, b, P)
        self.assertEqual((r["df"], r["dw"]), (1.0, round(1 - 1 / 3, 4)))
        del b["waypoints"]
        self.assertNotIn("dw", label.label_pair(a, b, P))


if __name__ == "__main__":
    unittest.main()
