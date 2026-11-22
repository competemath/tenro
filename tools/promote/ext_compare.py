#!/usr/bin/env python3
"""ext_compare.py - the extension entries of a snapshot against Tengoku's, constant by constant. Standard library only.

  ext_compare.py SOURCE.jsonl SNAPSHOT.jsonl --instances global|scoped --out REPORT.json

SOURCE.jsonl is what `tengai-extinfo` printed in Tengoku's environment for the constants of the layers, SNAPSHOT.jsonl what the SAME tool printed for the SAME constants in the snapshot's environment (the layers
imported, after `tengai-replay --ext` put the entries back): one JSON object a line, `{"n": [name components], ...}` with `red`, `proj`, `class`, `st`, `inst`, `sinst` (the namespaces it is a scoped instance in, with their priorities) and `bi` for what the constant carries (a constant
that carries nothing has no row). The tool is the same on both sides, so what is compared is what Lean itself says about each constant, not what the replay meant to do.

`--added NAMES.jsonl` (the names the layer replays added, `tengai-replay --added`, one JSON array of components a line) says which constants the snapshot is responsible for: a constant of the layers that
the replay did NOT add is one that **Lean core already holds**, and the replay leaves it alone. Tengoku's libraries may have changed what core says about it (the first rehearsal: `instSMulOfMul` is core's `instance
(priority := 910)` and Tengoku has it at 1100) and the snapshot cannot carry that. Those constants are compared all the same and reported apart, as **core**: a count, never part of `ok`. Without `--added` every
constant counts.

Per constant, per kind: **same**, **differs** (the row says another thing), **lost** (the source has it and the snapshot has not), **extra** (the snapshot has it and the source has not). The first EXAMPLES of each
are listed with what each side says (a snapshot with a dozen of them must be able to be read from its own log, and the first run of a whole tree had 9 differences and 5 losses that showed their names only). An instance's priority
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

KINDS = ("red", "proj", "class", "st", "inst", "sinst", "bi")
EXAMPLES = 40


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


def canonical(kind: str, row):
    """a row as it is compared: the scoped registrations of an instance are a set (tengai-extinfo sorts them, a file written by hand or by another version need not)"""
    if kind == "sinst" and isinstance(row, list):
        return sorted(row, key=lambda e: json.dumps(e, sort_keys=True))
    return row


def compare_inst(src: dict, snap: dict, mode: str) -> str:
    """same / differs / deviation for an instance entry"""
    if src.get("prio") != snap.get("prio"):
        return "differs"
    if snap.get("kind") != mode:  # the snapshot registers every instance one way: anything else there is not what the replay does
        return "differs"
    return "same" if src.get("kind") == mode else "deviation"


def read_added(path: Path) -> set[tuple]:
    """the names the layer replays added: one JSON array of name components a line"""
    out: set[tuple] = set()
    with open(path, encoding="utf-8") as f:
        for i, ln in enumerate(f, start=1):
            if ln.strip():
                try:
                    out.add(tuple(json.loads(ln)))
                except (ValueError, TypeError) as e:
                    raise SystemExit(f"ext_compare: {path.name} line {i} is not a name ({e!r}): {ln.strip()[:100]}") from e
    return out


def compare(source: dict[tuple, dict], snapshot: dict[tuple, dict], mode: str, added: set[tuple] | None = None) -> dict:
    if mode not in ("global", "scoped"):
        raise SystemExit("ext_compare: --instances is global or scoped")
    counts: dict[str, Counter] = {k: Counter() for k in KINDS}
    core_counts: Counter = Counter()
    examples: dict[str, list] = {"differs": [], "lost": [], "extra": [], "deviation": [], "core": []}
    deviations: Counter = Counter()
    core_names: set[tuple] = set()

    def example(bucket: str, name: tuple, kind: str, detail=None, **more) -> None:
        if len(examples[bucket]) < EXAMPLES:
            examples[bucket].append(
                {"name": ".".join(str(c) for c in name), "kind": kind, **more, **({"detail": detail} if detail is not None else {})}
            )

    for name in sorted(set(source) | set(snapshot), key=lambda n: tuple(str(c) for c in n)):
        a, b = source.get(name), snapshot.get(name)
        core = added is not None and name not in added  # a constant Lean core holds: the replay did not add it
        if core:
            core_names.add(name)
        for kind in KINDS:
            x, y = (a or {}).get(kind), (b or {}).get(kind)
            if x is None and y is None:
                continue
            detail = None
            if x is None:
                category = "extra"
                detail = {"snapshot": y}
            elif y is None:
                category = "lost"
                detail = {"source": x}
            elif kind == "inst":
                category = compare_inst(x, y, mode)
                if category != "same":
                    detail = {"source": x, "snapshot": y}
            else:
                category = "same" if canonical(kind, x) == canonical(kind, y) else "differs"
                if category == "differs":
                    detail = {"source": x, "snapshot": y}
            if core:
                core_counts[category] += 1
                if category != "same":
                    example("core", name, kind, detail, how=category)
                continue
            counts[kind][category] += 1
            if category == "deviation":
                deviations[f"{x.get('kind')}_became_{mode}"] += 1
            if category != "same":
                example(category, name, kind, detail)
    totals = {c: sum(counts[k][c] for k in KINDS) for c in ("same", "differs", "lost", "extra", "deviation")}
    return {
        "instances": mode,
        "source_rows": len(source),
        "snapshot_rows": len(snapshot),
        "kinds": {k: dict(sorted(counts[k].items())) for k in KINDS if counts[k]},
        "totals": totals,
        "deviations": dict(sorted(deviations.items())),
        "examples": examples,
        "core": None
        if added is None
        else {"constants": len(core_names), **{c: core_counts[c] for c in ("same", "differs", "lost", "extra", "deviation")}},
        "ok": totals["differs"] == totals["lost"] == totals["extra"] == 0,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", type=Path)
    ap.add_argument("snapshot", type=Path)
    ap.add_argument("--instances", required=True, choices=["global", "scoped"])
    ap.add_argument(
        "--added",
        type=Path,
        help="the names the layer replays added (tengai-replay --added): the other constants of the layers are Lean core's, reported apart",
    )
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)
    report = compare(read(a.source), read(a.snapshot), a.instances, read_added(a.added) if a.added else None)
    a.out.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    t = report["totals"]
    print(
        f"ext_compare: {report['source_rows']:,} rows in Tengoku, {report['snapshot_rows']:,} in the snapshot; entries: {t['same']:,} same, {t['differs']:,} differ, {t['lost']:,} lost, {t['extra']:,} extra; "
        f"instances registered {report['instances']}: {t['deviation']:,} that Tengoku has the other way ({report['deviations'] or 'none'}); {'no problem' if report['ok'] else 'PROBLEMS'}"
    )
    if report["core"] is not None:
        c = report["core"]
        print(
            f"  Lean core's own constants ({c['constants']:,}, left alone by the replay): {c['same']:,} entries the same, {c['differs']:,} differ, {c['lost']:,} lost, {c['extra']:,} extra: reported, not judged"
        )
        for e in report["examples"]["core"]:
            print(
                f"    core {e['how']}: {e['name']} ({e['kind']}) {json.dumps(e['detail'], sort_keys=True) if 'detail' in e else ''}".rstrip()
            )
    for category in ("differs", "lost", "extra"):
        for e in report["examples"][category]:
            print(f"  {category}: {e['name']} ({e['kind']}) {json.dumps(e['detail'], sort_keys=True) if 'detail' in e else ''}".rstrip())
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
