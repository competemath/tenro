#!/usr/bin/env python3
"""probe_findings.py - the output of tools/soundness/Probes.lean as the `{"findings": [...]}` file tools/soundness/verdict.py reads.

  probe_findings.py hypothesis-dropping < probes.out > hypothesis-dropping.json

Each `unused<TAB>theorem<TAB>module<TAB>index<TAB>name<TAB>type` line is one finding: a hypothesis the proof never uses. In Tengai that is a defect to fix or to acknowledge (the statement is
weaker than its proof; the generalisation is the same proof without it); in Tenro it is a generalisation candidate (design: deduplicated by isnad shape, confirmed by full id). Standard library only.
"""

from __future__ import annotations

import json
import sys


def examined(lines) -> dict | None:
    """what the probe LOOKED AT: the `examined<TAB>theorems<TAB>hypotheses` line, None if the probe did not say"""
    for ln in lines:
        parts = ln.rstrip("\n").split("\t")
        if parts[0] == "examined" and len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
            return {"theorems": int(parts[1]), "hypotheses": int(parts[2])}
    return None


def findings(lines) -> list[str]:
    out = []
    for ln in lines:
        parts = ln.rstrip("\n").split("\t")
        if parts[0] != "unused" or len(parts) < 6:
            continue
        _, theorem, module, index, name, ty = parts[:6]
        out.append(f"{theorem} ({module}): hypothesis #{index} `{name} : {ty}` is never used")
    return out


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv != ["hypothesis-dropping"]:
        print(__doc__)
        return 2
    lines = list(sys.stdin)
    print(json.dumps({"findings": findings(lines), "examined": examined(lines)}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
