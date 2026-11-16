#!/usr/bin/env python3
"""check_budget.py - the performance gate (perf-budget.toml).

check_budget.py check   --budget perf-budget.toml --load load.json --scale scale.json    a measurement above a cap fails
check_budget.py ratchet --budget perf-budget.toml --base OLD.toml                        a cap above the one on the base branch fails (caps are only lowered)
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path

CAPS = (("load", "cap_net_median_s"), ("scale", "cap_ms_per_module"))


def read_toml(path: Path) -> dict:
    with path.open("rb") as f:
        return tomllib.load(f)


def check(budget: dict, load: dict, scale: dict) -> list[str]:
    problems = []
    if load["net_median_s"] > budget["load"]["cap_net_median_s"]:
        problems.append(f"cold import {load['net_median_s']} s is above the cap {budget['load']['cap_net_median_s']} s")
    if scale["ms_per_module"] > budget["scale"]["cap_ms_per_module"]:
        problems.append(f"{scale['ms_per_module']} ms per module is above the cap {budget['scale']['cap_ms_per_module']} ms")
    return problems


def ratchet(new: dict, old: dict) -> list[str]:
    problems = []
    for table, key in CAPS:
        if table in old and key in old[table] and new[table][key] > old[table][key]:
            problems.append(f"{table}.{key} was raised from {old[table][key]} to {new[table][key]}: caps are only lowered")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--budget", type=Path, required=True)
    c.add_argument("--load", type=Path, required=True)
    c.add_argument("--scale", type=Path, required=True)
    r = sub.add_parser("ratchet")
    r.add_argument("--budget", type=Path, required=True)
    r.add_argument("--base", type=Path, required=True)
    a = ap.parse_args(argv)
    if a.cmd == "check":
        problems = check(read_toml(a.budget), json.loads(a.load.read_text()), json.loads(a.scale.read_text()))
    else:
        problems = ratchet(read_toml(a.budget), read_toml(a.base))
    for p in problems:
        print(f"FAIL {p}")
    print("perf budget: ok" if not problems else f"perf budget: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
