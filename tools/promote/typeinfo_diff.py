#!/usr/bin/env python3
"""typeinfo_diff.py - where the type of a theorem differs between two environments. Standard library only.

  typeinfo_diff.py SOURCE.jsonl REPLAYED.jsonl [--out REPORT.json]

Both files are the output of `tengai-typeinfo` (one JSON line a name: `size`, `mdata`, the leading `binders`, the `type` as a string) over the same names, one run in Tengoku's environment and one
in the replayed module. `compare_ids.py` reports a statement id that differs only in its size class as `drift`; this says which part of the expression differs: the node count, the number of
`mdata` nodes (the exporter drops them), a binder name, annotation or head, or the first character where the two type strings part. Nothing here decides anything: it is a diagnosis, printed so that
the reason is on the page and not a guess.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def read(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for ln in path.read_text(encoding="utf-8").splitlines():
        if ln.strip():
            r = json.loads(ln)
            out[".".join(str(c) for c in r["n"])] = r
    return out


def first_difference(a: str, b: str) -> dict | None:
    """where two strings first part, with a little of each around it; None when they are equal"""
    if a == b:
        return None
    k = next((i for i, (x, y) in enumerate(zip(a, b, strict=False)) if x != y), min(len(a), len(b)))
    lo = max(0, k - 40)
    return {"at": k, "source": a[lo : k + 60], "replayed": b[lo : k + 60]}


def diff_one(src: dict | None, rep: dict | None) -> dict:
    if src is None or rep is None or src.get("missing") or rep.get("missing"):
        return {
            "verdict": "missing",
            "source_missing": src is None or bool(src.get("missing")),
            "replayed_missing": rep is None or bool(rep.get("missing")),
        }
    sb, rb = src.get("binders", []), rep.get("binders", [])
    binder_at = next((i for i, (x, y) in enumerate(zip(sb, rb, strict=False)) if x != y), None)
    if binder_at is None and len(sb) != len(rb):
        binder_at = min(len(sb), len(rb))
    out = {
        "size": [src["size"], rep["size"]],
        "mdata": [src["mdata"], rep["mdata"]],
        "binders": [len(sb), len(rb)],
        "first_binder_difference": None
        if binder_at is None
        else {
            "index": binder_at,
            "source": sb[binder_at] if binder_at < len(sb) else None,
            "replayed": rb[binder_at] if binder_at < len(rb) else None,
        },
        "type_difference": first_difference(str(src.get("type", "")), str(rep.get("type", ""))),
    }
    reasons = []
    if src["mdata"] != rep["mdata"]:
        reasons.append("mdata nodes")
    if src["size"] != rep["size"]:
        reasons.append("node count")
    if binder_at is not None:
        reasons.append("binders")
    if out["type_difference"] is not None:
        reasons.append("type text")
    out["verdict"] = "same" if not reasons else "differs: " + ", ".join(reasons)
    return out


def report(source: dict[str, dict], replayed: dict[str, dict]) -> dict:
    return {name: diff_one(source.get(name), replayed.get(name)) for name in sorted(set(source) | set(replayed))}


def render(rep: dict) -> str:
    lines = []
    for name, d in rep.items():
        lines.append(f"{name}: {d['verdict']}")
        if d["verdict"] == "missing":
            continue
        lines.append(
            f"  nodes {d['size'][0]} -> {d['size'][1]}, mdata {d['mdata'][0]} -> {d['mdata'][1]}, leading binders {d['binders'][0]} -> {d['binders'][1]}"
        )
        if d["first_binder_difference"]:
            lines.append(f"  first binder difference: {json.dumps(d['first_binder_difference'], ensure_ascii=False)}")
        if d["type_difference"]:
            t = d["type_difference"]
            lines.append(f"  type strings part at {t['at']}:\n    source:   {t['source']!r}\n    replayed: {t['replayed']!r}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source")
    ap.add_argument("replayed")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    rep = report(read(Path(a.source)), read(Path(a.replayed)))
    if a.out:
        Path(a.out).write_text(json.dumps(rep, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(render(rep))
    return 0


if __name__ == "__main__":
    sys.exit(main())
