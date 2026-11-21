#!/usr/bin/env python3
"""compare_ids.py - the promotion lens, checked: every transplanted theorem states in tengai exactly what it stated in Tengoku. Standard library only (Tengoku's isnad.py is loaded, never copied).

  compare_ids.py --isnad-py TOOLS/scripts/isnad.py --names NAMES.txt --source ISNAD_TENGOKU.tsv --replayed ISNAD_REPLAYED.tsv [--out REPORT.json]

SOURCE is `tengoku-isnad` over the Tengoku modules the sample came from; REPLAYED is `tengoku-isnad` over the replayed module, run in an environment that holds the replayed constants and Lean core alone.
For each name in NAMES the statement id (`kind.<hyps>h<vars>v.s<size>.<sha of the canonical statement>`) must be the same in both: the id is the canonical elaborated statement, so equal ids mean the
replayed theorem says what the Tengoku one said; an id that differs only in the hypothesis count or the size class (same kind, variables and canonical hash) is reported as `drift`, not failed. The report has the counts and every name that is missing or differs; the exit code is 1 if there is one.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from tengoku_isnad import load_module  # noqa: E402


def ids_of(isnad, lines: list[str], wanted: set[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for ln in lines:
        if ln.startswith(f"isnad{isnad.VERSION}\t"):
            r = isnad.Record(ln)
            if r.name in wanted and r.name not in out:
                out[r.name] = r.id
    return out


def split_id(ident: str) -> tuple[str, str, str, str] | None:
    """`kind.<hyps>h<vars>v.s<size>.<sha>` -> (kind, vars, sha, hypotheses and size class); None if it is not that shape"""
    parts = ident.split(".")
    if len(parts) < 4 or not parts[-1] or not parts[-2].startswith("s"):
        return None
    shape = parts[-3]
    if "h" not in shape or not shape.endswith("v"):
        return None
    hyps, vars_ = shape[:-1].split("h", 1)
    return (".".join(parts[:-3]), vars_, parts[-1], f"{hyps}h.{parts[-2]}")


def compare(names: list[str], source: dict[str, str], replayed: dict[str, str], unchecked: frozenset[str] = frozenset()) -> dict:
    """unchecked: names whose sample row has no statement id by construction (a sample of the intake manifests: no isnad pass): they are counted (`no_source_id`), not compared, and not a failure.
    equal: the same id. drift: the same statement (kind, variables and canonical hash) whose hypothesis count or size class differs: isnad reads those off the telescope and the node count,
    which depend on what the environment knows (a reducible definition; expression metadata the replay does not carry), not on the statement. different: anything else, a changed statement."""
    checked = [n for n in names if n not in unchecked]
    missing_source = [n for n in checked if n not in source]
    missing_replayed = [n for n in checked if n in source and n not in replayed]
    different: list[dict] = []
    drift: list[dict] = []
    equal = 0
    for n in checked:
        if n not in source or n not in replayed:
            continue
        a_id, b_id = source[n], replayed[n]
        if a_id == b_id:
            equal += 1
            continue
        sa, sb = split_id(a_id), split_id(b_id)
        row = {"name": n, "source": a_id, "replayed": b_id}
        if sa and sb and sa[:3] == sb[:3]:
            drift.append(row)
        else:
            different.append(row)
    return {
        "names": len(names),
        "equal": equal,
        "drift": drift,
        "no_source_id": len(names) - len(checked),
        "missing_in_source": missing_source,
        "missing_in_replayed": missing_replayed,
        "different": different,
        "ok": equal + len(drift) == len(checked),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--isnad-py", required=True)
    ap.add_argument("--names", required=True)
    ap.add_argument("--source")
    ap.add_argument(
        "--source-jsonl",
        help="SAMPLE.jsonl of pick.py (name, id, ...): the Tengoku ids as candidates.jsonl recorded them, instead of an isnad run over the source modules",
    )
    ap.add_argument("--replayed", required=True)
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    isnad = load_module(Path(a.isnad_py))
    names = [n for n in Path(a.names).read_text(encoding="utf-8").splitlines() if n.strip()]
    wanted = set(names)
    unchecked: frozenset[str] = frozenset()
    if a.source_jsonl:
        rows = [json.loads(ln) for ln in Path(a.source_jsonl).read_text(encoding="utf-8").splitlines() if ln.strip()]
        source = {r["name"]: r["id"] for r in rows if r["name"] in wanted and r.get("id")}
        unchecked = frozenset(r["name"] for r in rows if r["name"] in wanted and not r.get("id"))
    elif a.source:
        source = ids_of(isnad, Path(a.source).read_text(encoding="utf-8").splitlines(), wanted)
    else:
        ap.error("give --source or --source-jsonl")
    replayed = ids_of(isnad, Path(a.replayed).read_text(encoding="utf-8").splitlines(), wanted)
    report = compare(names, source, replayed, unchecked)
    text = json.dumps(report, sort_keys=True)
    if a.out:
        Path(a.out).write_text(text + "\n", encoding="utf-8")
    print(text[:2000])
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
