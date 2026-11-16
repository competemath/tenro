#!/usr/bin/env python3
"""summary.py - what a calibration run found, as markdown: the counts by label, and the groups a person must look at (calibration/PROTOCOL.md, "What a person sees").

summary.py LABELS.jsonl [--tags-read N] > summary.md
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def render(groups: list[dict], tags_read: int | None = None, stats: dict | None = None) -> str:
    counts = Counter(g["label"] for g in groups)
    out = ["# Calibration run", ""]
    if tags_read is not None:
        out += [f"Tags read from the sources: {tags_read} (a group is a lower bound: an untagged theorem is not seen).", ""]
    if stats:
        out += [
            f"Statement groups in the tagged tree: {stats['groups']}; {stats['single_library_groups']} have theorems from one library only (alias by rule 1, not exported); "
            f"{stats['cross_library_groups']} cross-library, of which {stats['selected_groups']} were sampled (deterministically) and labelled below.",
            "",
        ]
    out += [f"Groups: {len(groups)} (alias {counts['alias']}, similar {counts['similar']}, independent {counts['independent']}).", ""]
    review = [g for g in groups if g["review"]]
    out += [f"For a person: {len(review)} group(s) (every independent one, and every one with a borderline pair).", ""]
    for g in review:
        out.append(f"## `{g['id']}` ({g['label']})")
        out += [
            f"- {x['a']} / {x['b']}: {x['label']} ({x['rule']}, Jaccard {x['jaccard']}{', borderline' if x['borderline'] else ''})"
            for x in g["pairs"]
        ]
        out.append("")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("labels")
    ap.add_argument("--tags-read", type=int)
    ap.add_argument("--stats", type=Path)
    a = ap.parse_args(argv)
    with open(a.labels, encoding="utf-8") as f:
        groups = [json.loads(line) for line in f if line.strip()]
    print(render(groups, a.tags_read, json.loads(a.stats.read_text()) if a.stats else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
