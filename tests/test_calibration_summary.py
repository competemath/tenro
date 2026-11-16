import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "calibration"))
import summary  # noqa: E402


class SummaryTest(unittest.TestCase):
    def test_counts_and_review_list(self):
        pair = {"a": "A.t", "b": "B.t", "label": "independent", "rule": "independent", "jaccard": 0.0, "borderline": False}
        groups = [
            {"id": "g1", "members": ["A.t", "B.t"], "pairs": [pair], "label": "independent", "review": True},
            {
                "id": "g2",
                "members": ["C.t", "D.t"],
                "pairs": [{**pair, "label": "alias", "rule": "same-chain"}],
                "label": "alias",
                "review": False,
            },
        ]
        text = summary.render(groups, tags_read=7)
        self.assertIn("Groups: 2 (alias 1, similar 0, independent 1).", text)
        self.assertIn("For a person: 1 group(s)", text)
        self.assertIn("## `g1` (independent)", text)
        self.assertNotIn("g2", text)
        self.assertIn("Tags read from the sources: 7", text)


if __name__ == "__main__":
    unittest.main()
