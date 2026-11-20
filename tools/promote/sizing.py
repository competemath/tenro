#!/usr/bin/env python3
"""sizing.py - how much of Tengoku a transplant into tengai would carry, from the closures of theorems (tools/closure/closure.py). Standard library only.

  sizing.py CLOSURES.jsonl [--core-prefix Init --core-prefix Std --core-prefix Lean ...] [--steps 1,10,100,1000]

Input: the lines of `closure.py --modules ...` (each with `name`, `closure`, `modules`). A transplant of a theorem is its reduced closure: every constant its proof reaches that Lean core does not already hold.
One JSON object comes out:

  per_theorem   how many constants a theorem alone needs outside Lean core (min, median, p90, max) and how many theorems need none (`core_closed`)
  curve         for the first K theorems of the file (K in --steps): how many DISTINCT constants outside Lean core their transplants need together, and the share that is shared
                (distinct / sum of the parts): the smaller it is, the more compact a bulk transplant is
  unplaced      constants whose module is not known (a constant without a module is counted as outside core, never as core: a gap here makes the numbers worse, not better)

A constant is in Lean core when its module is `Init`, `Std` or `Lean` or below one (`--core-prefix` changes the list).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable

CORE = ("Init", "Std", "Lean")


def in_core(module: str, prefixes: tuple[str, ...]) -> bool:
    return any(module == p or module.startswith(p + ".") for p in prefixes)


def outside_core(record: dict, prefixes: tuple[str, ...]) -> tuple[set[str], int]:
    """(the constants of the record's closure that Lean core does not hold, how many of them have no known module)"""
    modules = record.get("modules", {})
    out: set[str] = set()
    unplaced = 0
    for c in record["closure"]:
        m = modules.get(c)
        if m is None:
            unplaced += 1
            out.add(c)
        elif not in_core(m, prefixes):
            out.add(c)
    return out, unplaced


def quantile(sorted_values: list[int], q: float) -> int:
    if not sorted_values:
        return 0
    return sorted_values[min(len(sorted_values) - 1, int(q * len(sorted_values)))]


def analyse(records: Iterable[dict], prefixes: tuple[str, ...] = CORE, steps: tuple[int, ...] = (1, 10, 100, 1000)) -> dict:
    """records may be a generator: only the set of constants outside Lean core is kept of each (a closure file is hundreds of megabytes)"""
    sets: list[set[str]] = []
    unplaced = 0
    for r in records:
        s, u = outside_core(r, prefixes)
        sets.append(s)
        unplaced += u
    sizes = sorted(len(s) for s in sets)
    curve = []
    union: set[str] = set()
    parts = 0
    marks = {k for k in steps if k <= len(sets)} | ({len(sets)} if sets else set())
    for i, s in enumerate(sets, start=1):
        union |= s
        parts += len(s)
        if i in marks:
            curve.append(
                {"theorems": i, "distinct": len(union), "sum_of_parts": parts, "share": round(len(union) / parts, 4) if parts else 1.0}
            )
    return {
        "theorems": len(sets),
        "core_closed": sum(1 for n in sizes if n == 0),
        "per_theorem": {
            "min": sizes[0] if sizes else 0,
            "median": quantile(sizes, 0.5),
            "p90": quantile(sizes, 0.9),
            "max": sizes[-1] if sizes else 0,
        },
        "curve": curve,
        "unplaced": unplaced,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("closures")
    ap.add_argument("--core-prefix", action="append", default=None)
    ap.add_argument("--steps", default="1,10,100,1000")
    a = ap.parse_args(argv)

    def stream():
        with open(a.closures, encoding="utf-8") as f:
            for ln in f:
                if ln.strip():
                    yield json.loads(ln)

    prefixes = tuple(a.core_prefix) if a.core_prefix else CORE
    steps = tuple(int(x) for x in a.steps.split(",") if x)
    print(json.dumps(analyse(stream(), prefixes, steps), sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
