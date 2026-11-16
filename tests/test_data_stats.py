import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "readiness"))
import data_stats as D  # noqa: E402
import report as R  # noqa: E402


class DataStats(unittest.TestCase):
    def test_duplicates_are_the_theorems_beyond_the_first_of_each_statement(self):
        s = D.stats({"lemmas": 10, "definitions": 2, "modules": 3}, ["a", "b", "a", "a", "c"])
        self.assertEqual((s["statements"], s["structural_duplicates"], s["theorems_with_an_id"]), (3, 2, 5))
        self.assertEqual(D.stats({"lemmas": 1, "definitions": 1}, ["x"])["structural_duplicates"], 0)

    def test_the_report_reads_it(self):
        rep = R.report({"data": D.stats({"lemmas": 8, "definitions": 2}, ["a", "b"])})
        crit = {c["criterion"]: c["status"] for c in rep["gates"][0]["criteria"]}
        self.assertEqual(crit["lemma-to-definition ratio in data/"], "pass")  # 4 lemmas per definition is the limit, not past it
        self.assertEqual(crit["structural duplicates in data/"], "pass")
        rep = R.report({"data": D.stats({"lemmas": 9, "definitions": 2}, ["a", "a"])})
        crit = {c["criterion"]: c["status"] for c in rep["gates"][0]["criteria"]}
        self.assertEqual(crit["lemma-to-definition ratio in data/"], "fail")
        self.assertEqual(crit["structural duplicates in data/"], "fail")

    def test_an_empty_library_is_unmeasured_not_passing(self):
        rep = R.report({"data": D.stats({"lemmas": 0, "definitions": 0}, [])})
        crit = {c["criterion"]: c["status"] for c in rep["gates"][0]["criteria"]}
        self.assertEqual(crit["lemma-to-definition ratio in data/"], "unmeasured")

    def test_usage(self):
        self.assertEqual(D.main([]), 2)


if __name__ == "__main__":
    unittest.main()
