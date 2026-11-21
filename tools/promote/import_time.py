#!/usr/bin/env python3
"""import_time.py - the wall time of a command, several runs: the cold-import latency of a Lean file (invariant of docs/design.md: an absolute cap, C_load). Standard library only.

  import_time.py --runs 5 -- lake env lean check.lean
  import_time.py compare --runs 9 --baseline "lake env lean empty.lean" --target "Foundation=lake env lean foundation.lean" --target "Topic_A=lake env lean a.lean"

One JSON object: the runs in seconds, their minimum and median, and the exit code of every run (a run that fails is reported, never timed as a success).

`compare` times a baseline and several targets in PAIRED rounds: every round runs the baseline and each target once, in an order that shifts from round to round, and a target's net time is its time minus the baseline's of the
same round (`net_median`; `net_min` is the difference of the fastest runs). A runner's speed drifts and its neighbours' load comes and goes by amounts as large as an import; sequential blocks of runs put that drift into the
difference, paired rounds take most of it out (the same module measured +0.083 s and +0.171 s over an empty one in two sequential measurements).
"""

from __future__ import annotations

import argparse
import json
import shlex
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


def compare(baseline: list[str], targets: dict[str, list[str]], runs: int) -> dict:
    """paired rounds of the baseline and every target: the order shifts by one each round, a target's net time is its time minus the baseline's of the same round"""
    names = ["baseline", *targets]
    cmds = {"baseline": baseline, **targets}
    times: dict[str, list[float]] = {n: [] for n in names}
    codes: dict[str, list[int]] = {n: [] for n in names}
    for r in range(runs):
        shift = r % len(names)
        for n in names[shift:] + names[:shift]:
            t0 = time.perf_counter()
            res = subprocess.run(cmds[n], capture_output=True, check=False)
            times[n].append(round(time.perf_counter() - t0, 4))
            codes[n].append(res.returncode)
    base = times["baseline"]
    out: dict = {
        "runs": times,
        "exit_codes": codes,
        "baseline": {"min": min(base), "median": round(statistics.median(base), 4)},
    }
    for n in targets:
        net = [round(t - b, 4) for t, b in zip(times[n], base, strict=True)]
        out[n] = {
            "min": min(times[n]),
            "median": round(statistics.median(times[n]), 4),
            "net_median": round(statistics.median(net), 4),
            "net_min": round(min(times[n]) - min(base), 4),
            "net_runs": net,
        }
    return out


def main_compare(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="import_time.py compare")
    ap.add_argument("--runs", type=int, default=9)
    ap.add_argument("--baseline", required=True, help="the command of the baseline, one string")
    ap.add_argument("--target", action="append", default=[], help="NAME=COMMAND, one string; repeatable")
    a = ap.parse_args(argv)
    targets: dict[str, list[str]] = {}
    for t in a.target:
        name, _, cmd = t.partition("=")
        if not name or not cmd or name == "baseline" or name in targets:
            ap.error(f"a target is NAME=COMMAND with a name of its own: {t!r}")
        targets[name] = shlex.split(cmd)
    if not targets:
        ap.error("give at least one --target")
    out = compare(shlex.split(a.baseline), targets, a.runs)
    print(json.dumps(out, sort_keys=True))
    return 0 if all(c == 0 for cs in out["exit_codes"].values() for c in cs) else 1


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] == "compare":
        return main_compare(argv[1:])
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
