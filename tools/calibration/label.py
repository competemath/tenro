"""Label statement groups by calibration/PROTOCOL.md.

Input (stdin or --input): JSON lines {id, name, lib, closure, statement_closure?, modules?, from?} (the shape Tengoku's scripts/tawatur.py reads).
Output: one JSON line per group with two or more members: {id, members, pairs: [{a, b, label, rule, jaccard, borderline}], label, review}.
Pure and deterministic: the same input and parameters give the same bytes.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from util import distance, jaccard  # noqa: E402

AXIOMS = {"propext", "Classical.choice", "Quot.sound"}
STRENGTH = {"alias": 0, "similar": 1, "independent": 2}


def load_params(path: Path) -> dict:
    with path.open("rb") as f:
        return tomllib.load(f)


def _outside(rec: dict, forced: list[str]) -> set[str]:
    modules = rec.get("modules") or {}
    own = set(rec.get("statement_constants") or rec.get("statement_closure") or [])
    keep = set()
    for c in rec["closure"]:
        mod = modules.get(c, "")
        if c in AXIOMS or c in own or mod.split(".")[0] in forced:
            continue
        keep.add(c)
    return keep


def _uses(rec: dict, other: dict) -> bool:
    return other["name"] in set(rec["closure"])


def label_pair(a: dict, b: dict, p: dict) -> dict:
    ca, cb = _outside(a, p["forced_layer_modules"]), _outside(b, p["forced_layer_modules"])
    j = jaccard(ca, cb)
    margin = p["borderline_margin"]
    near = abs(j - p["alias_jaccard_min"]) <= margin or abs(j - p["independent_jaccard_max"]) <= margin
    collection = a["lib"] == b["lib"] and a["lib"] in p.get("collections", [])
    same_chain = (
        (a["lib"] == b["lib"] and not collection) or _uses(a, b) or _uses(b, a) or (a.get("from") and a.get("from") == b.get("from"))
    )
    floor = p["substance_floor"]
    if same_chain:
        label, rule, border = "alias", "same-chain", False
    elif min(len(ca), len(cb)) < floor:
        label, rule = "similar", "substance"
        border = min(len(ca), len(cb)) == floor - 1
    elif j >= p["alias_jaccard_min"]:
        label, rule, border = "alias", "shared-proof", near
    elif j <= p["independent_jaccard_max"]:
        label, rule, border = "independent", "independent", near
    else:
        label, rule, border = "similar", "between", near
    out = {
        "a": a["name"],
        "b": b["name"],
        "label": label,
        "rule": rule,
        "jaccard": round(j, 4),
        "borderline": bool(border),
        "df": round(1 - j, 4),
    }
    if "waypoints" in a and "waypoints" in b:  # the second axis of the divergence (isnad.py waypoints), when the closures carry it
        out["dw"] = round(distance(a["waypoints"], b["waypoints"]), 4)
    return out


def label_group(members: list[dict], p: dict) -> dict:
    members = sorted(members, key=lambda r: r["name"])
    pairs = [label_pair(a, b, p) for a, b in itertools.combinations(members, 2)]
    label = max((x["label"] for x in pairs), key=STRENGTH.__getitem__)
    review = label == "independent" or any(x["borderline"] for x in pairs)
    return {"id": members[0]["id"], "members": [m["name"] for m in members], "pairs": pairs, "label": label, "review": review}


def label_all(records: list[dict], p: dict) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for r in records:
        groups.setdefault(r["id"], []).append(r)
    return [label_group(g, p) for _, g in sorted(groups.items()) if len(g) >= 2]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", default="-")
    ap.add_argument("--params", default=str(Path(__file__).resolve().parents[2] / "calibration" / "protocol.toml"))
    args = ap.parse_args(argv)
    src = sys.stdin if args.input == "-" else open(args.input, encoding="utf-8")
    records = [json.loads(line) for line in src if line.strip()]
    for g in label_all(records, load_params(Path(args.params))):
        print(json.dumps(g, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
