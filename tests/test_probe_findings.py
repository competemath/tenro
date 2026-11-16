import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "soundness"))
import probe_findings as P  # noqa: E402
import verdict as V  # noqa: E402


class Findings(unittest.TestCase):
    def test_unused_lines_become_findings_and_other_lines_are_ignored(self):
        lines = ["unused\tPr.t\tPr.Cases\t2\th\ta < b\n", "probe: 1 unused hypotheses\n", "noise\n"]
        self.assertEqual(P.findings(lines), ["Pr.t (Pr.Cases): hypothesis #2 `h : a < b` is never used"])

    def test_the_file_is_what_the_verdict_reads(self):
        out = {"findings": P.findings(["unused\tPr.t\tPr.Cases\t2\th\ta < b\n"])}
        self.assertEqual(V.check_findings(json.loads(json.dumps(out)))["status"], "fail")
        self.assertEqual(V.check_findings({"findings": P.findings([])})["status"], "pass")

    def test_usage(self):
        self.assertEqual(P.main([]), 2)


if __name__ == "__main__":
    unittest.main()
