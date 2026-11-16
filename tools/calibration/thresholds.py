#!/usr/bin/env python3
"""thresholds.py - the tawatur thresholds a and b from the labelled pairs (tools/tawatur/admit.py `calibrate`).

  thresholds.py LABELS.jsonl [--human HUMAN.jsonl]

LABELS.jsonl is label.py's output; its pairs carry `df` (footprint distance) and, when the closures carried waypoints, `dw`. HUMAN.jsonl holds the owner's overrides, one line
`{"a": name, "b": name, "label": alias|similar|independent, "reason": ...}`: a human label replaces the rule label of that pair, and nothing else is ever edited by hand. A pair without `dw`
cannot take part (the divergence needs both axes), and the output says how many were left out. Prints JSON: the thresholds (or the best that violate the fewest pairs, and `feasible: false`).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tawatur"))
from admit import calibrate  # noqa: E402


def pairs_of(groups: list[dict], human: list[dict]) -> tuple[list[tuple[float, float, str]], int]:
    override = {frozenset((h["a"], h["b"])): h["label"] for h in human}
    out, skipped = [], 0
    for g in groups:
        for p in g["pairs"]:
            if "dw" not in p:
                skipped += 1
                continue
            out.append((p["df"], p["dw"], override.get(frozenset((p["a"], p["b"])), p["label"])))
    return out, skipped


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(__doc__)
        return 2
    groups = [json.loads(ln) for ln in Path(argv[0]).read_text(encoding="utf-8").splitlines() if ln.strip()]
    human = (
        [json.loads(ln) for ln in Path(argv[argv.index("--human") + 1]).read_text(encoding="utf-8").splitlines() if ln.strip()]
        if "--human" in argv
        else []
    )
    pairs, skipped = pairs_of(groups, human)
    result = {**calibrate(pairs), "pairs_used": len(pairs), "pairs_without_waypoints": skipped, "human_overrides": len(human)}
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
