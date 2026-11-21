"""tools/promote/missing.py: the names lean4export did not find are taken out of the sample, once, and counted by library."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "promote"))
import missing as M  # noqa: E402

ERR = (
    "PANIC at dumpConstant Export:237:48: Constant Physlib.Fin.f not found in environment.\n"
    "backtrace:\n/home/runner/lean4export(+0x997a6d5) [0x55]\n"
    "PANIC at dumpConstant Export:237:48: Constant Physlib.Fin.f not found in environment.\n"  # twice: once
    "PANIC at dumpConstant Export:237:48: Constant fderiv_x' not found in environment.\n"
)


class Missing(unittest.TestCase):
    def test_the_names_are_read_once_and_in_order(self):
        names, other = M.read_missing(ERR)
        self.assertEqual(names, ["Physlib.Fin.f", "fderiv_x'"])
        self.assertEqual(other, [])

    def test_another_panic_is_not_dropped(self):
        names, other = M.read_missing("PANIC at foo Bar:1:2: unreachable code has been reached\n" + ERR)
        self.assertEqual(len(other), 1)
        self.assertEqual(len(names), 2)

    def files(self, d: Path, err: str = ERR):
        (d / "e.err").write_text(err)
        (d / "n.txt").write_text("A.ok\nPhyslib.Fin.f\nfderiv_x'\nB.ok\n")
        rows = [
            {"name": "A.ok", "id": None, "library": "a", "module": "Tengoku.A.M"},
            {"name": "Physlib.Fin.f", "id": None, "library": "physlib", "module": "Tengoku.Physlib.M"},
            {"name": "fderiv_x'", "id": None, "library": "physlib", "module": "Tengoku.Physlib.N"},
            {"name": "B.ok", "id": None, "library": "b", "module": "Tengoku.B.M"},
        ]
        (d / "s.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))

    def test_main_takes_them_out_of_the_names_and_the_sample(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self.files(d)
            code = M.main(
                ["--err", str(d / "e.err"), "--names", str(d / "n.txt"), "--sample", str(d / "s.jsonl"), "--out", str(d / "m.txt")]
            )
            self.assertEqual(code, 0)
            self.assertEqual((d / "n.txt").read_text().split(), ["A.ok", "B.ok"])
            self.assertEqual([json.loads(x)["name"] for x in (d / "s.jsonl").read_text().splitlines()], ["A.ok", "B.ok"])
            self.assertEqual((d / "m.txt").read_text().split(), ["Physlib.Fin.f", "fderiv_x'"])

    def test_nothing_missing_changes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self.files(d, err="")
            before = (d / "n.txt").read_text()
            self.assertEqual(M.main(["--err", str(d / "e.err"), "--names", str(d / "n.txt"), "--sample", str(d / "s.jsonl")]), 0)
            self.assertEqual((d / "n.txt").read_text(), before)

    def test_a_sample_with_nothing_left_fails_and_another_panic_fails(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self.files(
                d,
                err="".join(
                    f"PANIC at dumpConstant Export:237:48: Constant {n} not found in environment.\n"
                    for n in ("A.ok", "Physlib.Fin.f", "fderiv_x'", "B.ok")
                ),
            )
            self.assertEqual(M.main(["--err", str(d / "e.err"), "--names", str(d / "n.txt")]), 1)
            self.files(d, err="PANIC at foo Bar:1:2: something else\n")
            self.assertEqual(M.main(["--err", str(d / "e.err"), "--names", str(d / "n.txt")]), 1)
            self.assertEqual((d / "n.txt").read_text().split(), ["A.ok", "Physlib.Fin.f", "fderiv_x'", "B.ok"])  # untouched


if __name__ == "__main__":
    unittest.main()
