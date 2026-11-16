#!/usr/bin/env python3
"""waypoints.py - put each proof's waypoints (isnad.py waypoints) into the closure records.

  waypoints.py CLOSURES.jsonl HAVES.txt --isnad-py TENGOKU/scripts/isnad.py > CLOSURES-WITH-WAYPOINTS.jsonl

HAVES.txt is the output of `tengoku-isnad --haves` for the modules of the records (`isnad1-have` lines); the ids are made by Tengoku's own isnad.py. Every record gets `waypoints`: the sorted
ids of the statements of the `have`s of its proof (empty when it has none: Lean lists only theorems that have some). A record whose theorem the Lean side did not report is NOT given an empty set by
default: `--assume-complete` says the HAVES.txt covers every record's module, and only then does a missing theorem mean "no haves"; otherwise it is left without the field, and the divergence is not computed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from tengoku_isnad import load_module  # noqa: E402


def merge(records: list[dict], have_lines: list[str], waypoint_sets, assume_complete: bool) -> list[dict]:
    sets = waypoint_sets([ln for ln in have_lines if ln.startswith("isnad1-have\t")])
    out = []
    for r in records:
        if r["name"] in sets:
            r = {**r, "waypoints": sets[r["name"]]}
        elif assume_complete:
            r = {**r, "waypoints": []}
        out.append(r)
    return out


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 4 or argv[2] != "--isnad-py":
        print(__doc__)
        return 2
    records = [json.loads(ln) for ln in Path(argv[0]).read_text(encoding="utf-8").splitlines() if ln.strip()]
    haves = Path(argv[1]).read_text(encoding="utf-8").splitlines()
    mod = load_module(Path(argv[3]))
    for r in merge(records, haves, mod.waypoint_sets, "--assume-complete" in argv):
        print(json.dumps(r, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
