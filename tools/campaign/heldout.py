#!/usr/bin/env python3
"""heldout.py - choose the held-out problems of a campaign by written rules, deterministically (docs/heldout-selection.md). Standard library only.

  heldout.py CANDIDATES.jsonl --cutoff YYYY-MM-DD [--per-stratum 100] [--seed S] [--max-library-share 0.2] [--out SELECTION.json]

CANDIDATES.jsonl has one theorem per line: {"id": isnad statement id, "name", "library", "module", "date": "YYYY-MM-DD" or null, "deps": [statement ids it depends on], "hyps": int, "size": int,
"aliases": number of other records that state the same thing}. It is built from `tengoku-isnad` and its `--deps` output (the slice workflows).

The three strata are those of readiness gate 5, and a theorem is in at most one, chosen in this order of scarcity:
  post-cutoff          `date` is on or after the cutoff: the model cannot have seen the theorem, and no memorised library helps
  cross-domain         its dependencies lie in two or more libraries: it needs the union Tengoku makes
  dependency-ablation  it depends on 2 to 12 other theorems of its own library: the library's lemmas are what a prover has to find
Every candidate must be non-trivial (`hyps` >= 1 and `size` >= 5, which is 32 or more expression nodes) and state something no other record states (`aliases` == 0): a selected statement is removed from the library
in both arms of the campaign (invariant I8), and a statement that has an alias would still be there under the alias's name.
Within a stratum the order is the sha256 of `seed + id`, so the same candidates and seed always give the same problems; no library gets more than `--max-library-share` of a stratum.
The result lists the ids per stratum, the ids to remove from the library in every arm (`exclude`), the rules and the split hash (campaign.py split-hash) the registration needs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
import campaign  # noqa: E402
from util import read_jsonl  # noqa: E402

STRATA = ("post-cutoff", "cross-domain", "dependency-ablation")
MIN_SIZE, MIN_HYPS = 5, 1
ABLATION_DEPS = (2, 12)


def nontrivial(c: dict) -> bool:
    return c.get("hyps", 0) >= MIN_HYPS and c.get("size", 0) >= MIN_SIZE and c.get("aliases", 0) == 0 and bool(c.get("id"))


def stratum_of(c: dict, cutoff: str, library_of: dict[str, str]) -> str | None:
    if c.get("date") and c["date"] >= cutoff:
        return "post-cutoff"
    libs = {library_of[d] for d in c.get("deps", []) if d in library_of}
    if len(libs) >= 2:
        return "cross-domain"
    own = [d for d in c.get("deps", []) if library_of.get(d) == c["library"]]
    if ABLATION_DEPS[0] <= len(set(own)) <= ABLATION_DEPS[1]:
        return "dependency-ablation"
    return None


def rank(seed: str, ident: str) -> str:
    return hashlib.sha256(f"{seed}\n{ident}".encode()).hexdigest()


def select(candidates: list[dict], cutoff: str, per_stratum: int, seed: str, max_share: float) -> dict:
    library_of = {c["id"]: c["library"] for c in candidates if c.get("id")}
    pools: dict[str, list[dict]] = {s: [] for s in STRATA}
    for c in candidates:
        if nontrivial(c):
            s = stratum_of(c, cutoff, library_of)
            if s:
                pools[s].append(c)
    chosen: dict[str, list[dict]] = {}
    taken: set[str] = set()
    for s in STRATA:
        cap = max(1, int(per_stratum * max_share))
        per_library: dict[str, int] = {}
        picked: list[dict] = []
        for c in sorted(pools[s], key=lambda c: rank(seed, c["id"])):
            if len(picked) >= per_stratum:
                break
            if c["id"] in taken or per_library.get(c["library"], 0) >= cap:
                continue
            picked.append(c)
            taken.add(c["id"])
            per_library[c["library"]] = per_library.get(c["library"], 0) + 1
        chosen[s] = picked
    ids = {s: [c["id"] for c in chosen[s]] for s in STRATA}
    every = sorted(i for s in STRATA for i in ids[s])
    return {
        "rules": {
            "cutoff": cutoff,
            "per_stratum": per_stratum,
            "seed": seed,
            "max_library_share": max_share,
            "nontrivial": f"hyps >= {MIN_HYPS}, size >= {MIN_SIZE}, no alias",
            "ablation_deps": list(ABLATION_DEPS),
        },
        "strata": ids,
        "counts": {s: len(ids[s]) for s in STRATA},
        "available": {s: len(pools[s]) for s in STRATA},
        "libraries": {
            s: dict(sorted({lib: sum(1 for c in chosen[s] if c["library"] == lib) for lib in {c["library"] for c in chosen[s]}}.items()))
            for s in STRATA
        },
        "exclude": every,
        "split_hash": campaign.split_hash(every),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("candidates")
    ap.add_argument("--cutoff", required=True)
    ap.add_argument("--per-stratum", type=int, default=100)
    ap.add_argument("--seed", default="tenro-heldout-1")
    ap.add_argument("--max-library-share", type=float, default=0.2)
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    result = select(read_jsonl(Path(a.candidates)), a.cutoff, a.per_stratum, a.seed, a.max_library_share)
    text = json.dumps(result, indent=1, sort_keys=True) + "\n"
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("counts", "available", "split_hash")}, sort_keys=True))
    short = [s for s in STRATA if result["counts"][s] < a.per_stratum]
    if short:
        print(f"heldout: fewer than {a.per_stratum} found in {short}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
