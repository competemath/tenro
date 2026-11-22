#!/usr/bin/env python3
"""faithful.py - is a replayed snapshot faithful to the environment it was exported from? Standard library only.

  faithful.py SOURCE.jsonl SNAPSHOT.jsonl [--out REPORT.json] [--examples N] [--only-in-snapshot]

Both files are the output of `tengai-typeinfo --hashes` (tengai v0.0.18) over the same names: one run in the source's environment (Tengoku's), one in the snapshot's. A record is `kind`, `thash` (the hash of
the type), `tsize` (its nodes), `vhash` (the hash of the value, when there is one) and `lparams`; a name that is not a constant is `{"n": ..., "missing": true}`. What counts as the same:

  the same kind                 the type must agree (hash, nodes, universe parameters), and the value too when both have one (a definition, a theorem kept with its proof, an opaque constant)
  theorem -> axiom              a statement stub (docs/statements.md): the type must agree; the stub has no value, the theorem's proof is not asked for
  anything else -> axiom        the kernel refused it and `--stub-refused` made it an axiom of its type: the type must agree, and it is COUNTED (a snapshot that refused nothing has none)
  any other change of kind      a problem

A name missing in the source and in the snapshot is not a problem (a sampled name the tree does not have: `missing.py` counted it); a name the source has and the snapshot lacks is. Nothing is guessed: a record that
differs says which field. The hashes are Lean's 32 bits and the node count: a difference is certain, an agreement makes one very unlikely and does not prove there is none (tengai's TengaiTypeInfo.lean says so).

`--only-in-snapshot` compares only the names the snapshot's file lists (the source's file holds the names of every layer; a run that replayed some of them asks about those): the others are counted as `not_asked`.

Exit status 0 when there is no problem. `--out` writes the counts and the first examples of every kind of problem as JSON.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


def read(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    with open(path, encoding="utf-8") as f:
        for ln in f:
            if ln.strip():
                r = json.loads(ln)
                out[".".join(str(c) for c in r["n"])] = r
    return out


def compare(source: dict[str, dict], snapshot: dict[str, dict], examples: int = 20, only_in_snapshot: bool = False) -> dict:
    counts: Counter[str] = Counter()
    kinds: Counter[str] = Counter()
    problems: dict[str, list] = {
        "missing_in_snapshot": [],
        "snapshot_has_what_the_source_lacks": [],
        "kind_changed": [],
        "type_differs": [],
        "value_differs": [],
        "universe_parameters_differ": [],
    }
    totals: Counter[str] = Counter()

    def problem(key: str, name: str, detail=None) -> None:
        totals[key] += 1
        if len(problems[key]) < examples:
            problems[key].append(name if detail is None else {"name": name, **detail})

    for name in sorted(set(source) | set(snapshot)):
        a, b = source.get(name), snapshot.get(name)
        if only_in_snapshot and b is None:
            counts["not_asked"] += 1
            continue
        if a is None:
            problem("snapshot_has_what_the_source_lacks", name)
            continue
        if b is None:  # the names of the two runs are the same; a name only in the source was not asked of the snapshot
            problem("missing_in_snapshot", name)
            continue
        if a.get("missing") and b.get("missing"):
            counts["absent_in_both"] += 1
            continue
        if a.get("missing") or b.get("missing"):
            problem("missing_in_snapshot" if b.get("missing") else "snapshot_has_what_the_source_lacks", name)
            continue
        ka, kb = a["kind"], b["kind"]
        stub = ka != kb and kb == "axiom"
        if ka != kb and not stub:
            problem("kind_changed", name, {"source": ka, "snapshot": kb})
            continue
        if stub:
            counts["statement_stubs" if ka == "thm" else "refused_and_stubbed"] += 1
        elif "vhash" in a:
            counts["kept_with_value" if ka == "thm" else "same_with_value"] += 1
        else:
            counts["same_without_value"] += 1
        kinds[f"{ka}->{kb}"] += 1
        if a["lparams"] != b["lparams"]:
            problem("universe_parameters_differ", name, {"source": a["lparams"], "snapshot": b["lparams"]})
        if (a["thash"], a["tsize"]) != (b["thash"], b["tsize"]):
            problem("type_differs", name, {"source": [a["thash"], a["tsize"]], "snapshot": [b["thash"], b["tsize"]]})
        if not stub and "vhash" in a and a.get("vhash") != b.get("vhash"):
            problem("value_differs", name, {"source": a.get("vhash"), "snapshot": b.get("vhash")})
        counts["compared"] += 1
    n_problems = sum(totals.values())
    return {
        "names": len(set(source) | set(snapshot)) - counts["not_asked"],
        "not_asked": counts["not_asked"],
        "compared": counts["compared"],
        "absent_in_both": counts["absent_in_both"],
        "statement_stubs": counts["statement_stubs"],
        "kept_with_value": counts["kept_with_value"],
        "same_with_value": counts["same_with_value"],
        "same_without_value": counts["same_without_value"],
        "refused_and_stubbed": counts["refused_and_stubbed"],
        "by_kind": dict(sorted(kinds.items())),
        "problems": {k: v for k, v in problems.items() if v},
        "problem_counts": dict(sorted(totals.items())),
        "passed": n_problems == 0 and counts["compared"] > 0,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", type=Path)
    ap.add_argument("snapshot", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--examples", type=int, default=20)
    ap.add_argument("--only-in-snapshot", action="store_true")
    a = ap.parse_args(argv)
    report = compare(read(a.source), read(a.snapshot), a.examples, a.only_in_snapshot)
    if a.out:
        a.out.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"faithful: {report['compared']:,} of {report['names']:,} names compared ({report['statement_stubs']:,} theorems stand as axioms of their type, "
        f"{report['kept_with_value']:,} kept with their proof, {report['same_with_value']:,} definitions and the like with a value, {report['same_without_value']:,} without; "
        f"{report['refused_and_stubbed']:,} stubbed after a refusal; {report['absent_in_both']:,} absent in both); "
        + (
            "no problem: passed"
            if report["passed"]
            else f"PROBLEMS {report['problem_counts']}"
            if report["problems"]
            else "nothing was compared: failed"
        )
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
