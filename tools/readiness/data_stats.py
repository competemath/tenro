#!/usr/bin/env python3
"""data_stats.py - the `data-stats.json` that gate 1 reads (tools/readiness/report.py): lemma and definition counts and structural duplicates.

  data_stats.py LEAN_COUNTS.json ISNAD.tsv --isnad-py TENGOKU/scripts/isnad.py > data-stats.json

LEAN_COUNTS.json is the line `tools/readiness/DataStats.lean` printed ({"lemmas", "definitions", "modules"}); ISNAD.tsv is `tengoku-isnad` over the same modules. A STRUCTURAL DUPLICATE is a theorem whose
statement id (tools/index/build.py's unit) an earlier theorem already has: `data/` holds one proof per statement, so the count must be 0 in Tengai. Standard library only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from tengoku_isnad import load_isnad  # noqa: E402


def stats(counts: dict, ids: list[str]) -> dict:
    statements = len(set(ids))
    return {
        "lemmas": counts["lemmas"],
        "definitions": counts["definitions"],
        "modules": counts.get("modules"),
        "statements": statements,
        "theorems_with_an_id": len(ids),
        "structural_duplicates": len(ids) - statements,
    }


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 4 or argv[2] != "--isnad-py":
        print(__doc__)
        return 2
    counts = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    records, _ = load_isnad(Path(argv[3]), Path(argv[1]).read_text(encoding="utf-8").splitlines(), [])
    print(json.dumps(stats(counts, [r[1] for r in records]), indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
