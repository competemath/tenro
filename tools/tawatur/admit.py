#!/usr/bin/env python3
"""admit.py - admission, eviction and status of tawatur routes, and the calibration of their thresholds (Tengai ADR-0002). Standard library only.

A ROUTE is a proof of a statement that is already in `data/`: {name, footprint, waypoints, size}.
  footprint  F(p): the constants the REDUCED proof term reaches (tools/closure/closure.py), minus the forced layer X; padding with unused `have`s changes nothing
  waypoints  W(p): the isnad ids of the `have` statements of the proof (canonical, so reordering algebra does not count)
  size       the number of constants in the proof term (compactness: the last tie-break, never a divergence)
Two routes DIVERGE when 1 - Jaccard(F) >= a AND 1 - Jaccard(W) >= b. Raw edit distance and length are never used. The thresholds a and b are not chosen: `calibrate` finds them from labelled
pairs (alias pairs must fail, independent pairs must pass; `similar` pairs carry no constraint), and says when no thresholds can do both.

  admit    a candidate enters a folder of routes only if it diverges from EVERY stored route; with the folder full (cap 3) the best triple of the four decides: the one maximising the
           minimum pairwise divergence, then compactness; the candidate replaces a route only if that triple contains it (an exact tie keeps the folder as it is).
  status   the statement is tawatur when at least three of its routes are PAIRWISE divergent and each has substance (a footprint of at least `floor` constants).
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

CAP = 3


def distance(a: set[str] | frozenset[str], b: set[str] | frozenset[str]) -> float:
    """1 - Jaccard; two empty sets are identical (distance 0)."""
    union = set(a) | set(b)
    return 1 - len(set(a) & set(b)) / len(union) if union else 0.0


def divergence(p: dict, q: dict) -> tuple[float, float]:
    return distance(p["footprint"], q["footprint"]), distance(p["waypoints"], q["waypoints"])


def diverge(p: dict, q: dict, a: float, b: float) -> bool:
    df, dw = divergence(p, q)
    return df >= a and dw >= b


def pair_score(p: dict, q: dict) -> float:
    """how far apart two routes are on their weaker axis (used to rank triples, not to decide admission)"""
    return min(divergence(p, q))


def triple_key(triple: tuple[dict, ...]) -> tuple[float, int]:
    """larger is better: the minimum pairwise divergence, then (negated) total size"""
    return min(pair_score(p, q) for p, q in itertools.combinations(triple, 2)), -sum(r["size"] for r in triple)


def admit(stored: list[dict], cand: dict, a: float, b: float, cap: int = CAP) -> tuple[list[dict], str, dict | None]:
    """(new folder, decision, evicted route). Decisions: rejected (not divergent from every stored route), added, replaced, kept (the folder's best triple does not contain it)."""
    if any(not diverge(cand, s, a, b) for s in stored):
        return stored, "rejected", None
    if len(stored) < cap:
        return [*stored, cand], "added", None
    # on an exact tie the folder stays as it is (stability: the newcomer must be strictly better), then by name so the choice is deterministic
    best = max(
        itertools.combinations([*stored, cand], cap),
        key=lambda t: (triple_key(t), sum(r is not cand for r in t), tuple(r["name"] for r in t)),
    )
    if cand not in best:
        return stored, "kept", None
    evicted = next(s for s in stored if s not in best)
    return list(best), "replaced", evicted


def status(routes: list[dict], a: float, b: float, floor: int = 5) -> dict:
    substantial = [r for r in routes if len(r["footprint"]) >= floor]
    best: list[str] = []
    for k in range(min(len(substantial), CAP), 2, -1):
        for group in itertools.combinations(substantial, k):
            if all(diverge(p, q, a, b) for p, q in itertools.combinations(group, 2)):
                best = [r["name"] for r in group]
                break
        if best:
            break
    return {"tawatur": len(best) >= 3, "pairwise_divergent": best, "routes": len(routes), "with_substance": len(substantial)}


def calibrate(pairs: list[tuple[float, float, str]], step: float = 0.01) -> dict:
    """pairs: (footprint distance, waypoint distance, label). Finds (a, b) on a grid with every alias pair NOT divergent and every independent pair divergent, maximising the smallest
    slack (how far every constraint is from being violated). If no thresholds satisfy all, returns the ones with the fewest violations and says so."""
    alias = [(df, dw) for df, dw, lab in pairs if lab == "alias"]
    indep = [(df, dw) for df, dw, lab in pairs if lab == "independent"]
    best: tuple[tuple[int, float], float, float] | None = None
    n = int(round(1 / step))
    for ia in range(n + 1):
        for ib in range(n + 1):
            a, b = ia * step, ib * step
            viol = sum(1 for df, dw in alias if df >= a and dw >= b) + sum(1 for df, dw in indep if not (df >= a and dw >= b))
            slack = min([max(a - df, b - dw) for df, dw in alias] + [min(df - a, dw - b) for df, dw in indep] + [1.0])
            key = (-viol, slack)
            if best is None or key > best[0]:
                best = (key, a, b)
    assert best is not None
    (neg_viol, slack), a, b = best
    return {
        "a": round(a, 4),
        "b": round(b, 4),
        "violations": -neg_viol,
        "feasible": neg_viol == 0,
        "slack": round(slack, 4),
        "alias_pairs": len(alias),
        "independent_pairs": len(indep),
    }


def main(argv: list[str] | None = None) -> int:
    """admit.py calibrate PAIRS.jsonl   (lines {"df", "dw", "label"})   |   admit.py status FOLDER.json --a A --b B   (a JSON list of routes)"""
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) >= 2 and argv[0] == "calibrate":
        rows = [json.loads(ln) for ln in Path(argv[1]).read_text(encoding="utf-8").splitlines() if ln.strip()]
        print(json.dumps(calibrate([(r["df"], r["dw"], r["label"]) for r in rows]), indent=1))
        return 0
    if len(argv) >= 6 and argv[0] == "status" and argv[2] == "--a" and argv[4] == "--b":
        routes = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        print(json.dumps(status(routes, float(argv[3]), float(argv[5])), indent=1))
        return 0
    print(main.__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
