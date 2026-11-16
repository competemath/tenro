#!/usr/bin/env python3
"""summary.py - what a calibration run found, as markdown: the counts by label, and the groups a person must look at (calibration/PROTOCOL.md, "What a person sees").

summary.py LABELS.jsonl [--tags-read N] > summary.md
"""

from __future__ import annotations

import argparse
import json
from collections import Counter


def render(groups: list[dict], tags_read: int | None = None) -> str:
    counts = Counter(g["label"] for g in groups)
    out = ["# Calibration run", ""]
    if tags_read is not None:
        out += [f"Tags read from the sources: {tags_read} (a group is a lower bound: an untagged theorem is not seen).", ""]
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
    a = ap.parse_args(argv)
    with open(a.labels, encoding="utf-8") as f:
        groups = [json.loads(line) for line in f if line.strip()]
    print(render(groups, a.tags_read))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
