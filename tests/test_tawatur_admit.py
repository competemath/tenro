import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "tawatur"))
import admit as A  # noqa: E402


def route(name, footprint, waypoints, size=None):
    return {"name": name, "footprint": set(footprint), "waypoints": set(waypoints), "size": size if size is not None else len(footprint)}


def block(prefix, n):
    return {f"{prefix}{i}" for i in range(n)}


R1 = route("r1", block("a", 10), block("wa", 4))
R2 = route("r2", block("b", 10), block("wb", 4))
R3 = route("r3", block("c", 10), block("wc", 4))
R4 = route("r4", block("d", 10), block("wd", 4))
ALIAS = route("alias", block("a", 9) | {"z"}, block("wa", 4))


class Distance(unittest.TestCase):
    def test_jaccard_distance(self):
        self.assertEqual(A.distance({"a", "b"}, {"a", "b"}), 0.0)
        self.assertEqual(A.distance({"a"}, {"b"}), 1.0)
        self.assertAlmostEqual(A.distance({"a", "b"}, {"b", "c"}), 2 / 3)
        self.assertEqual(A.distance(set(), set()), 0.0)

    def test_divergence_needs_both_axes(self):
        same_footprint_new_waypoints = route("x", R1["footprint"], block("wz", 4))
        self.assertFalse(A.diverge(R1, same_footprint_new_waypoints, 0.5, 0.5))
        self.assertTrue(A.diverge(R1, R2, 0.5, 0.5))


class Admission(unittest.TestCase):
    def test_a_near_copy_is_rejected_and_a_new_route_added(self):
        self.assertEqual(A.admit([R1], ALIAS, 0.5, 0.5)[1], "rejected")
        folder, decision, _ = A.admit([R1], R2, 0.5, 0.5)
        self.assertEqual((decision, [r["name"] for r in folder]), ("added", ["r1", "r2"]))

    def test_must_diverge_from_every_stored_route(self):
        near_r2 = route("n", block("b", 9) | {"q"}, block("wb", 4))
        self.assertEqual(A.admit([R1, R2], near_r2, 0.5, 0.5)[1], "rejected")

    def test_full_folder_keeps_the_best_triple(self):
        # r4 shares half its footprint with r1, so it diverges from all but is closer to r1 than r2, r3 are to each other
        close = route("close", block("a", 5) | block("d", 5), block("wa", 2) | block("wd", 2), size=40)
        folder, decision, evicted = A.admit([R1, R2, R3], close, 0.3, 0.3)
        self.assertEqual(decision, "kept")
        self.assertEqual(folder, [R1, R2, R3])
        self.assertIsNone(evicted)
        folder, decision, evicted = A.admit([R1, R2, close], R3, 0.3, 0.3)
        self.assertEqual(decision, "replaced")
        self.assertEqual(evicted["name"], "close")
        self.assertEqual(sorted(r["name"] for r in folder), ["r1", "r2", "r3"])

    def test_ties_go_to_the_more_compact_route(self):
        big = route("big", block("c", 10), block("wc", 4), size=100)
        small = route("small", block("c", 10) | set(), block("wc", 4), size=20)
        folder, decision, _ = A.admit([R1, R2, big], route("small2", block("e", 10), block("we", 4), size=20), 0.5, 0.5)
        self.assertEqual(decision, "replaced")
        self.assertNotIn("big", [r["name"] for r in folder])
        self.assertEqual(small["size"], 20)


class Status(unittest.TestCase):
    def test_three_pairwise_divergent_routes_with_substance(self):
        s = A.status([R1, R2, R3], 0.5, 0.5)
        self.assertTrue(s["tawatur"])
        self.assertEqual(s["pairwise_divergent"], ["r1", "r2", "r3"])

    def test_two_routes_or_a_copy_do_not_make_it(self):
        self.assertFalse(A.status([R1, R2], 0.5, 0.5)["tawatur"])
        self.assertFalse(A.status([R1, R2, ALIAS], 0.5, 0.5)["tawatur"])

    def test_substance_floor(self):
        tiny = route("tiny", {"t1", "t2"}, {"w1"})
        s = A.status([R1, R2, tiny], 0.5, 0.5)
        self.assertFalse(s["tawatur"])
        self.assertEqual(s["with_substance"], 2)


class Calibration(unittest.TestCase):
    def test_separable_labels_are_feasible_and_the_thresholds_separate_them(self):
        pairs = [
            (0.1, 0.2, "alias"),
            (0.3, 0.6, "alias"),
            (0.5, 0.1, "alias"),
            (0.8, 0.9, "independent"),
            (0.7, 0.8, "independent"),
            (0.5, 0.5, "similar"),
        ]
        r = A.calibrate(pairs)
        self.assertTrue(r["feasible"])
        for df, dw, lab in pairs:
            ok = df >= r["a"] and dw >= r["b"]
            if lab == "alias":
                self.assertFalse(ok)
            if lab == "independent":
                self.assertTrue(ok)
        self.assertGreater(r["slack"], 0)

    def test_inseparable_labels_are_reported_not_hidden(self):
        r = A.calibrate([(0.9, 0.9, "alias"), (0.1, 0.1, "independent")])
        self.assertFalse(r["feasible"])
        self.assertGreaterEqual(r["violations"], 1)

    def test_the_answer_is_the_centre_of_the_equally_good_region_not_its_edge(self):
        """one alias at df 0.40 and one independent at df 0.80 (waypoints equal): every a in (0.40, 0.80] separates them equally well, so the answer is the middle, and the region is reported"""
        r = A.calibrate([(0.40, 0.0, "alias"), (0.80, 0.0, "independent")])
        self.assertTrue(r["feasible"])
        lo, hi = r["region"]["a"]
        self.assertAlmostEqual(lo, 0.41, places=4)
        self.assertAlmostEqual(hi, 0.80, places=4)
        self.assertAlmostEqual(r["a"], (lo + hi) / 2, delta=0.01)
        self.assertEqual(r["region"]["b"], [0.0, 0.0])
        self.assertEqual(r["b"], 0.0)

    def test_the_chosen_point_is_inside_the_region_and_feasible_with_two_axes(self):
        pairs = [(0.1, 0.9, "alias"), (0.9, 0.1, "alias"), (0.9, 0.9, "independent")]
        r = A.calibrate(pairs)
        self.assertTrue(r["feasible"])
        a, b = r["a"], r["b"]
        self.assertTrue(r["region"]["a"][0] <= a <= r["region"]["a"][1] and r["region"]["b"][0] <= b <= r["region"]["b"][1])
        for df, dw, lab in pairs:
            self.assertEqual(df >= a and dw >= b, lab == "independent")

    def test_the_stored_calibration_is_the_default_and_is_consistent_with_itself(self):
        a, b = A.calibrated_thresholds()
        th = json.loads(A.THRESHOLDS_FILE.read_text(encoding="utf-8"))["thresholds"]
        self.assertTrue(th["feasible"])
        self.assertEqual((a, b), (th["a"], th["b"]))
        self.assertTrue(th["region"]["a"][0] <= a <= th["region"]["a"][1])

    def test_an_infeasible_or_inconsistent_stored_result_gives_no_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "t.json"
            good = {"a": 0.5, "b": 0.0, "region": {"a": [0.4, 0.7], "b": [0.0, 0.0]}, "feasible": True, "violations": 0}
            f.write_text(json.dumps({"thresholds": good}))
            self.assertEqual(A.calibrated_thresholds(f), (0.5, 0.0))
            f.write_text(json.dumps({"thresholds": {**good, "feasible": False, "violations": 2}}))
            with self.assertRaises(ValueError):
                A.calibrated_thresholds(f)
            f.write_text(json.dumps({"thresholds": {**good, "a": 0.9}}))
            with self.assertRaises(ValueError):
                A.calibrated_thresholds(f)

    def test_status_uses_the_calibrated_thresholds_unless_told_otherwise(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "folder.json"
            f.write_text(
                json.dumps([{**r, "footprint": sorted(r["footprint"]), "waypoints": sorted(r["waypoints"])} for r in (R1, R2, R3)])
            )
            self.assertEqual(A.main(["status", str(f)]), 0)
            self.assertEqual(A.main(["status", str(f), "--a", "0.5", "--b", "0.5"]), 0)
            self.assertEqual(A.main(["status", str(f), "--a", "0.5"]), 0)
            self.assertEqual(A.main(["status", str(f), "--nope", "1"]), 2)

    def test_the_cli(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "pairs.jsonl").write_text(
                json.dumps({"df": 0.1, "dw": 0.1, "label": "alias"})
                + "\n"
                + json.dumps({"df": 0.9, "dw": 0.9, "label": "independent"})
                + "\n"
            )
            self.assertEqual(A.main(["calibrate", str(d / "pairs.jsonl")]), 0)
            self.assertEqual(A.main([]), 2)


if __name__ == "__main__":
    unittest.main()
