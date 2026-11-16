#!/usr/bin/env python3
"""run_isnad.py - `tengoku-isnad` over a long list of modules, in batches, and a batch that fails does not end the run.

  run_isnad.py --modules modules.txt --out isnad.tsv --failed failed.txt [--batch 25] [--jobs 2] [--exe .lake/build/bin/tengoku-isnad]   (run from the Tengoku checkout)

One process per `batch` modules (an import of the whole batch's closure is the cost, Tengoku's scripts/isnad.py BATCH). When a batch stops, each of its modules is tried alone and the
ones that still stop are written to `failed.txt` with the reason: a calibration over 1,300 modules must not lose two hours of work to one module that does not import. A module name that is
not a Lean name (an empty component) is never passed on. The output is in the order of the module list whatever the order the batches finish in. Nothing is hidden: the number of
failures is printed and the run fails only when MORE than `--max-failed-share` of the modules fail (a broken toolchain, not a bad module).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

NAME = re.compile(r"(?:[^\W\d]|«)[\w'!?«»℀-⅏₀-ₜ-]*(?:\.(?:[^\W\d]|«)[\w'!?«»℀-⅏₀-ₜ-]*)*")
Runner = Callable[[list[str]], tuple[int, list[str], str]]


def valid(module: str) -> bool:
    return NAME.fullmatch(module) is not None


def run_exe(modules: list[str], exe: str) -> tuple[int, list[str], str]:
    cmd = ["lake", "env", exe, *[x for m in modules for x in ("--module", m)]]
    r = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return r.returncode, [ln for ln in r.stdout.splitlines() if ln.startswith("isnad1\t")], (r.stderr or r.stdout).strip()[-300:]


def batch_records(part: list[str], run: Runner) -> tuple[list[str], list[tuple[str, str]]]:
    """(records, [(module, reason)]): the batch in one process, or module by module when it stops."""
    code, lines, err = run(part)
    if code in (0, 1):  # 1: a named theorem was not found; with no --name this is only a count
        return lines, []
    if len(part) == 1:
        return [], [(part[0], err)]
    records: list[str] = []
    failed: list[tuple[str, str]] = []
    for m in part:
        got, bad = batch_records([m], run)
        records += got
        failed += bad
    return records, failed


def run_all(modules: list[str], run: Runner, batch: int, jobs: int) -> tuple[list[str], list[tuple[str, str]]]:
    good = [m for m in modules if valid(m)]
    failed = [(m, "not a Lean module name") for m in modules if not valid(m)]
    parts = [good[i : i + batch] for i in range(0, len(good), batch)]
    with ThreadPoolExecutor(max_workers=max(jobs, 1)) as pool:
        done = list(pool.map(lambda p: batch_records(p, run), parts))
    records: list[str] = []
    for got, bad in done:
        records += got
        failed += bad
    return records, failed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--modules", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--failed", type=Path, required=True)
    ap.add_argument("--batch", type=int, default=25)
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--exe", default=".lake/build/bin/tengoku-isnad")
    ap.add_argument("--max-failed-share", type=float, default=0.05)
    a = ap.parse_args(argv)
    modules = [ln.strip() for ln in a.modules.read_text(encoding="utf-8").splitlines() if ln.strip()]
    records, failed = run_all(modules, lambda part: run_exe(part, a.exe), a.batch, a.jobs)
    a.out.write_text("".join(r + "\n" for r in records), encoding="utf-8")
    a.failed.write_text("".join(f"{m}\t{why.replace(chr(10), ' ')}\n" for m, why in failed), encoding="utf-8")
    print(f"run_isnad: {len(modules)} modules, {len(records)} records, {len(failed)} modules failed")
    return 1 if modules and len(failed) / len(modules) > a.max_failed_share else 0


if __name__ == "__main__":
    sys.exit(main())
