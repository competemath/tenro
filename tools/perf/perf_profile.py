#!/usr/bin/env python3
"""perf_profile.py - the import-latency measurements behind the performance gate (Tengai's docs/design.md, gate 1; perf-budget.toml).

  perf_profile.py load  --module Tengai [--root DIR] [--runs 9]            cold-process `import <module>` wall time, net of the bare-Lean baseline
  perf_profile.py scale [--sizes 0,200,800] [--runs 7] [--workdir DIR]     the same for synthetic libraries of N one-theorem modules: the slope is ms per added module

`load` starts a FRESH `lean` process on a file that holds `import <module>` and nothing else, `runs` times, and reports the median and the 95th percentile of the wall time;
the same is done for `import Init` and subtracted (starting Lean and loading its own core is not Tengai's cost). "Cold" means a new process: the operating system's file cache
is warm after the first run, as it is for every build the gate guards, and the first run is kept apart (`first_s`) so a cold file cache is visible too. Output is one JSON object
on stdout. Nothing here proves anything: it measures. The caps and budgets those numbers become are fixed in perf-budget.toml (tools/perf/check_budget.py).
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def wall(cmd: list[str], cwd: Path) -> float:
    """Wall-clock seconds of one process; a failing process stops the run (a number from a broken import would pass any cap)."""
    t0 = time.perf_counter()
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    dt = time.perf_counter() - t0
    if r.returncode != 0:
        sys.exit(f"profile: {' '.join(cmd)} failed in {cwd}:\n{(r.stderr or r.stdout)[-600:]}")
    return dt


def summarise(times: list[float]) -> dict:
    s = sorted(times)
    p95 = s[min(len(s) - 1, max(0, round(0.95 * (len(s) - 1))))]
    return {"runs": len(s), "first_s": round(times[0], 4), "median_s": round(statistics.median(s), 4), "p95_s": round(p95, 4)}


def time_import(module: str, root: Path, runs: int, run=wall) -> dict:
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "Load.lean"
        f.write_text(f"import {module}\n", encoding="utf-8")
        times = [run(["lake", "env", "lean", str(f)], root) for _ in range(runs)]
    return summarise(times)


def load(module: str, root: Path, runs: int, run=wall) -> dict:
    mine, base = time_import(module, root, runs, run), time_import("Init", root, runs, run)
    return {
        "module": module,
        "runs": runs,
        "module_median_s": mine["median_s"],
        "baseline_median_s": base["median_s"],
        "net_median_s": round(max(mine["median_s"] - base["median_s"], 0.0), 4),
        "net_p95_s": round(max(mine["p95_s"] - base["median_s"], 0.0), 4),
        "first_s": mine["first_s"],
    }


def slope(points: list[tuple[int, float]]) -> float:
    """Least-squares slope of y against x (seconds per module), by the closed form; at least two distinct x."""
    n = len(points)
    mx, my = sum(x for x, _ in points) / n, sum(y for _, y in points) / n
    den = sum((x - mx) ** 2 for x, _ in points)
    if den == 0:
        raise ValueError("scale needs at least two different sizes")
    return sum((x - mx) * (y - my) for x, y in points) / den


def write_library(root: Path, name: str, n: int) -> None:
    """A Lake project `name` with n modules `<name>/M<i>.lean`, each one theorem, and a root `<name>.lean` importing them all."""
    (root / name).mkdir(parents=True, exist_ok=True)
    for i in range(n):
        (root / name / f"M{i}.lean").write_text(
            f"theorem {name}_t{i} (a : Nat) : a + {i} = {i} + a := Nat.add_comm a {i}\n", encoding="utf-8"
        )
    (root / f"{name}.lean").write_text("".join(f"import {name}.M{i}\n" for i in range(n)) or "-- empty\n", encoding="utf-8")


def scale(sizes: list[int], runs: int, workdir: Path, toolchain: str) -> dict:
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "lean-toolchain").write_text(toolchain + "\n", encoding="utf-8")
    libs = [f"Syn{n}" for n in sizes]
    for lib, n in zip(libs, sizes, strict=True):
        write_library(workdir, lib, n)
    (workdir / "lakefile.toml").write_text(
        'name = "perfsyn"\n'
        + "".join(f'[[lean_lib]]\nname = "{lib}"\nglobs = ["{lib}", "{lib}.+"]\n' for lib in libs)
        encoding="utf-8",
    )
    wall(["lake", "build"], workdir)
    rows = [{"modules": n, **time_import(lib, workdir, runs)} for lib, n in zip(libs, sizes, strict=True)]
    base = time_import("Init", workdir, runs)["median_s"]
    pts = [(r["modules"], r["median_s"]) for r in rows]
    return {"baseline_median_s": base, "rows": rows, "ms_per_module": round(1000 * slope(pts), 4)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("load")
    s.add_argument("--module", required=True)
    s.add_argument("--root", type=Path, default=Path("."))
    s.add_argument("--runs", type=int, default=9)
    s = sub.add_parser("scale")
    s.add_argument("--sizes", default="0,200,800")
    s.add_argument("--runs", type=int, default=7)
    s.add_argument("--workdir", type=Path)
    a = ap.parse_args(argv)
    if a.cmd == "load":
        print(json.dumps(load(a.module, a.root, a.runs), indent=1))
        return 0
    toolchain = Path("lean-toolchain").read_text(encoding="utf-8").strip()
    sizes = [int(x) for x in a.sizes.split(",")]
    if a.workdir:
        print(json.dumps(scale(sizes, a.runs, a.workdir, toolchain), indent=1))
    else:
        with tempfile.TemporaryDirectory() as d:
            print(json.dumps(scale(sizes, a.runs, Path(d), toolchain), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
