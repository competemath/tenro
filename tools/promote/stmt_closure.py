#!/usr/bin/env python3
"""stmt_closure.py - what a base of STATEMENTS would hold: the closure of a sample when the proofs of theorems are left out. Standard library only (layers.py's planner is loaded, never copied).

  stmt_closure.py EXPORT.ndjson --topics TOPICS.json [--added ADDED.jsonl] [--out REPORT.json]

The snapshot of a promotion (layers.py, tengai-replay) holds every constant that a proof of a sampled theorem reaches, because the kernel checks the proofs again. An environment for SEARCH does not need
them: elaborating a statement, `exact`, `apply` or `simp [lemma]` only uses the TYPE of a lemma, and the proof of a lemma is never unfolded (proof irrelevance), so a lemma that stands as an axiom of its type
is enough for the search; a proof found there is checked afterwards in an environment that holds the real proofs (tengai docs/design.md, invariant I1: untrusted search, trusted checking). The lemmas that
only the proofs used drop out of the closure with the proofs, and so does everything they reach. This measures how much smaller that environment is, from the export alone, by planning the layers of the
sample under three regimes:

  full             every constant a sampled theorem reaches through types and values (what the snapshot holds)
  theorems         the same, with the values of theorems left out (a theorem is an axiom of its type)
  theorems+opaque  and with the values of opaque constants left out too (neither the kernel nor the elaborator unfolds them, so an axiom of the same type is the same constant for them)

per regime: the units (an inductive type with its constructors and recursor, or one other constant), the constants, the terms below them (the sum over units of the terms of the unit's own declarations: a measure
of the size of the .olean, with the same bias in every regime), the foundation, and what a session loads (the foundation's part it uses and its topic) for the median and the largest topic. A measurement: nothing
is replayed or checked, and a definition whose value is a proof (a `def` of a Prop) is not recognised: its value stays, so the figures are an upper bound for the statement regimes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layers as L  # noqa: E402

REGIMES: tuple[tuple[str, frozenset[str]], ...] = (
    ("full", frozenset()),
    ("theorems", frozenset({"thm"})),
    ("theorems+opaque", frozenset({"thm", "opaque"})),
)


def median(xs: list[int]) -> int:
    xs = sorted(xs)
    return xs[len(xs) // 2] if xs else 0


def measure(ex: L.Full, topics: dict[str, list[str]], universe: set[tuple] | None) -> dict:
    """the layer plan under each regime, reduced to its figures: totals, the foundation, the sessions"""
    out: dict[str, dict] = {}
    for name, stub in REGIMES:
        ex.set_stub(stub)
        p = L.plan(ex, topics, universe)
        foundation = next((x for x in p["layers"] if x["topic"] is None), None)
        sessions = list(p["topics"].values())
        out[name] = {
            "stubbed_kinds": sorted(stub),
            "totals": p["totals"],
            "foundation": {k: foundation[k] for k in ("units", "constants", "terms")} if foundation else None,
            "sessions": {
                "topics": len(sessions),
                "units_median": median([s["units_loaded"] for s in sessions]),
                "units_max": max((s["units_loaded"] for s in sessions), default=0),
                "terms_median": median([s["terms_loaded"] for s in sessions]),
                "terms_max": max((s["terms_loaded"] for s in sessions), default=0),
            },
        }
    return out


def share(part: int, whole: int) -> str:
    return f"{100 * part / whole:.0f} %" if whole else "-"


def markdown(report: dict) -> str:
    full = report["full"]
    lines = [
        "## what a base of statements would hold (theorem proofs left out; a measurement, nothing replayed)",
        "",
        "| regime | units | constants | terms | foundation units | session units (median / largest) | session terms (median / largest) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, r in report.items():
        t, f, s = r["totals"], r["foundation"] or {"units": 0}, r["sessions"]
        fu = full["foundation"]["units"] if full["foundation"] else 0
        lines.append(
            f"| {name} | {t['units']:,} ({share(t['units'], full['totals']['units'])}) | {t['constants']:,} ({share(t['constants'], full['totals']['constants'])}) | "
            f"{t['terms']:,} ({share(t['terms'], full['totals']['terms'])}) | {f['units']:,} ({share(f['units'], fu)}) | "
            f"{s['units_median']:,} / {s['units_max']:,} | {s['terms_median']:,} / {s['terms_max']:,} |"
        )
    lines += ["", "units by the kind of their first constant:", ""]
    kinds = sorted({k for r in report.values() for k in r["totals"]["kinds"]})
    lines += ["| regime | " + " | ".join(kinds) + " |", "|---|" + "---:|" * len(kinds)]
    for name, r in report.items():
        lines.append(f"| {name} | " + " | ".join(f"{r['totals']['kinds'].get(k, 0):,}" for k in kinds) + " |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("export", type=Path)
    ap.add_argument("--topics", required=True, type=Path)
    ap.add_argument("--added", type=Path, help="the names a replay added (what Lean core does not hold): only those are counted")
    ap.add_argument("--out", type=Path, help="the figures as JSON")
    a = ap.parse_args(argv)
    ex = L.Full()
    ex.read(a.export)
    topics = json.loads(a.topics.read_text(encoding="utf-8"))
    report = measure(ex, topics, L.read_names(a.added) if a.added else None)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(json.dumps(report, indent=1, sort_keys=True) + "\n")
    print(markdown(report), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
