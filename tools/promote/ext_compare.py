#!/usr/bin/env python3
"""ext_compare.py - the extension entries of a snapshot against Tengoku's, constant by constant. Standard library only.

  ext_compare.py SOURCE.jsonl SNAPSHOT.jsonl --instances global|scoped --out REPORT.json

SOURCE.jsonl is what `tengai-extinfo` printed in Tengoku's environment for the constants of the layers, SNAPSHOT.jsonl what the SAME tool printed for the SAME constants in the snapshot's environment (the layers
imported, after `tengai-replay --ext` put the entries back): one JSON object a line, `{"n": [name components], ...}` with `red`, `proj`, `class`, `st`, `inst` and `bi` for what the constant carries (a constant
that carries nothing has no row). The tool is the same on both sides, so what is compared is what Lean itself says about each constant, not what the replay meant to do.

Per constant, per kind: **same**, **differs** (the row says another thing), **lost** (the source has it and the snapshot has not), **extra** (the snapshot has it and the source has not). An instance's priority
must agree; its kind is judged against `--instances`: the replay registers every instance as GLOBAL (`global`) or every instance as SCOPED to the namespace of its module (`scoped`), whatever kind the source row
says, so the instances that Tengoku has the other way are counted as **deviations**, not as differences: they are known and by construction, the number is what the owner has to decide about (a scoped instance of
Tengoku, `Classical.propDecidable` is one, that a `global` snapshot makes global behaves differently there). `ok` is true when nothing is lost, extra or different; deviations do not make it false and are always reported.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

KINDS = ("red", "proj", "class", "st", "inst", "bi")
EXAMPLES = 5


def read(path: Path) -> dict[tuple, dict]:
    rows: dict[tuple, dict] = {}
    with open(path, encoding="utf-8") as f:
        for i, ln in enumerate(f, start=1):
            if not ln.strip():
                continue
            try:
                row = json.loads(ln)
                key = tuple(row["n"])
            except (ValueError, KeyError, TypeError) as e:
                raise SystemExit(f"ext_compare: {path.name} line {i} is not a row of tengai-extinfo ({e!r}): {ln.strip()[:100]}") from e
            if key in rows:
                raise SystemExit(f"ext_compare: {path.name} has two rows for {'.'.join(str(c) for c in key)}")
            rows[key] = row
    return rows


def compare_inst(src: dict, snap: dict, mode: str) -> str:
    """same / differs / deviation for an instance entry"""
    if src.get("prio") != snap.get("prio"):
        return "differs"
    if snap.get("kind") != mode:  # the snapshot registers every instance one way: anything else there is not what the replay does
        return "differs"
    return "same" if src.get("kind") == mode else "deviation"


def compare(source: dict[tuple, dict], snapshot: dict[tuple, dict], mode: str) -> dict:
    if mode not in ("global", "scoped"):
        raise SystemExit("ext_compare: --instances is global or scoped")
    counts: dict[str, Counter] = {k: Counter() for k in KINDS}
    examples: dict[str, list] = {"differs": [], "lost": [], "extra": [], "deviation": []}
    deviations: Counter = Counter()

    def note(category: str, kind: str, name: tuple, detail=None) -> None:
        counts[kind][category] += 1
        if category in examples and len(examples[category]) < EXAMPLES:
            examples[category].append(
                {"name": ".".join(str(c) for c in name), "kind": kind, **({"detail": detail} if detail is not None else {})}
            )

    for name in sorted(set(source) | set(snapshot), key=lambda n: tuple(str(c) for c in n)):
        a, b = source.get(name), snapshot.get(name)
        for kind in KINDS:
            x, y = (a or {}).get(kind), (b or {}).get(kind)
            if x is None and y is None:
                continue
            if x is None:
                note("extra", kind, name)
            elif y is None:
                note("lost", kind, name)
            elif kind == "inst":
                verdict = compare_inst(x, y, mode)
                if verdict == "deviation":
                    deviations[f"{x.get('kind')}_became_{mode}"] += 1
                note(verdict, kind, name, None if verdict == "same" else {"source": x, "snapshot": y})
            elif x == y:
                note("same", kind, name)
            else:
                note("differs", kind, name)
    totals = {c: sum(counts[k][c] for k in KINDS) for c in ("same", "differs", "lost", "extra", "deviation")}
    return {
        "instances": mode,
        "source_rows": len(source),
        "snapshot_rows": len(snapshot),
        "kinds": {k: dict(sorted(counts[k].items())) for k in KINDS if counts[k]},
        "totals": totals,
        "deviations": dict(sorted(deviations.items())),
        "examples": examples,
        "ok": totals["differs"] == totals["lost"] == totals["extra"] == 0,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", type=Path)
    ap.add_argument("snapshot", type=Path)
    ap.add_argument("--instances", required=True, choices=["global", "scoped"])
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)
    report = compare(read(a.source), read(a.snapshot), a.instances)
    a.out.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    t = report["totals"]
    print(
        f"ext_compare: {report['source_rows']:,} rows in Tengoku, {report['snapshot_rows']:,} in the snapshot; entries: {t['same']:,} same, {t['differs']:,} differ, {t['lost']:,} lost, {t['extra']:,} extra; "
        f"instances registered {report['instances']}: {t['deviation']:,} that Tengoku has the other way ({report['deviations'] or 'none'}); {'no problem' if report['ok'] else 'PROBLEMS'}"
    )
    for category in ("differs", "lost", "extra"):
        for e in report["examples"][category]:
            print(f"  {category}: {e['name']} ({e['kind']})")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
