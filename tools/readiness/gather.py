#!/usr/bin/env python3
"""gather.py - put the measurements the other tools wrote into the one INPUTS.json that report.py reads. Standard library only.

  gather.py DIR [--budget perf-budget.toml] > INPUTS.json

Known files in DIR (each optional; a missing file is a missing measurement, never a default):
  load.json, scale.json   tools/perf/perf_profile.py            -> load, scale
  verdict.json            tools/soundness/verdict.py             -> soundness
  data-stats.json         {"lemmas", "definitions", "structural_duplicates", "statements"} -> data
  lens-report.json        tools/lens/lens.py check               -> migration (and migration_integrity_violations from its "integrity_violations" if present)
  retrieval.json, obfuscation.json, tamper.json, harness.json, validity.json, campaign.json  -> the keys of the same name (the owner's eval runs)
  mathlib-load.json       {"net_median_s": ...}                  -> mathlib_load_net_median_s (context)
"""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

DIRECT = {
    "load.json": "load", "scale.json": "scale", "verdict.json": "soundness", "data-stats.json": "data", "lens-report.json": "migration",
    "retrieval.json": "retrieval", "obfuscation.json": "obfuscation", "tamper.json": "tamper", "harness.json": "harness",
    "validity.json": "validity", "campaign.json": "campaign",
}  # fmt: skip


def gather(directory: Path, budget: Path | None = None) -> dict:
    out: dict = {}
    for fname, key in DIRECT.items():
        f = directory / fname
        if f.is_file():
            out[key] = json.loads(f.read_text(encoding="utf-8"))
    if "migration" in out and "integrity_violations" in out["migration"]:
        out["migration_integrity_violations"] = out["migration"]["integrity_violations"]
    m = directory / "mathlib-load.json"
    if m.is_file():
        out["mathlib_load_net_median_s"] = json.loads(m.read_text(encoding="utf-8"))["net_median_s"]
    if budget and budget.is_file():
        with budget.open("rb") as fh:
            out["budget"] = tomllib.load(fh)
    return out


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(__doc__)
        return 2
    budget = Path(argv[argv.index("--budget") + 1]) if "--budget" in argv else None
    print(json.dumps(gather(Path(argv[0]), budget), indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
