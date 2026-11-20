#!/usr/bin/env python3
"""import_time.py - the wall time of a command, several runs: the cold-import latency of a Lean file (invariant of docs/design.md: an absolute cap, C_load). Standard library only.

  import_time.py --runs 5 -- lake env lean check.lean

One JSON object: the runs in seconds, their minimum and median, and the exit code of every run (a run that fails is reported, never timed as a success).
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time


def measure(cmd: list[str], runs: int) -> dict:
    times: list[float] = []
    codes: list[int] = []
    for _ in range(runs):
        t0 = time.perf_counter()
        r = subprocess.run(cmd, capture_output=True, check=False)
        times.append(round(time.perf_counter() - t0, 4))
        codes.append(r.returncode)
    return {"runs": times, "min": min(times), "median": round(statistics.median(times), 4), "exit_codes": codes}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    a = ap.parse_args(argv)
    cmd = a.cmd[1:] if a.cmd and a.cmd[0] == "--" else a.cmd
    if not cmd:
        ap.error("give a command after --")
    out = measure(cmd, a.runs)
    print(json.dumps(out, sort_keys=True))
    return 0 if all(c == 0 for c in out["exit_codes"]) else 1


if __name__ == "__main__":
    sys.exit(main())
