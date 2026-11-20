#!/usr/bin/env python3
"""candidates.py - the candidate theorems of a held-out selection, from what `tengoku-isnad` says about libraries (docs/heldout-selection.md). Standard library only.

  candidates.py --isnad-py TENGOKU/scripts/isnad.py --library NAME ISNAD.tsv DEPS.tsv DEPMODULES.tsv [--library NAME2 ISNAD2.tsv DEPS2.tsv DEPMODULES2.tsv ...] [--dates DATES.tsv] --out CANDIDATES.jsonl

For each library: ISNAD.tsv is `tengoku-isnad` over its modules, DEPS.tsv is `tengoku-isnad --deps`, DEPMODULES.tsv is `DepModules.lean` over the dependency names that are not the library's own (`name<TAB>module`).
DATES.tsv (optional) is `module<TAB>YYYY-MM-DD`: the day the module's source was first added upstream (a theorem of a module with no date has no date and cannot be post-cutoff).

One line a theorem (see heldout.py): its statement id, how many other records state the same thing across all the libraries read (`aliases`), its hypotheses and size from the record, the distinct theorems of its own library
its proofs use (`own_deps`), and the distinct areas of everything they use (`dep_domains`: `Algebra`, `NumberTheory`, a library's name ...; the plumbing in NEUTRAL is not an area).
A theorem named twice in a library has one line, the first.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from tengoku_isnad import load_module  # noqa: E402

# areas that are plumbing, not mathematics: using them says nothing about which areas a theorem combines
NEUTRAL = frozenset(
    {"core", "Data", "Order", "Logic", "Tactic", "Lean", "Meta", "Control", "Deprecated", "Init", "Std", "Mathport", "Util"}
)


def domain_of(module: str) -> str:
    """the area of a module: `Tengoku.Algebra.Group.Basic` is Algebra, `Tengoku.Seed.NumberTheory.X` is NumberTheory, `Tengoku.Aintlib.X` is Aintlib, anything outside Tengoku is core"""
    parts = module.split(".")
    if parts[0] != "Tengoku" or len(parts) < 2:
        return "core"
    if parts[1] == "Seed":
        return parts[2] if len(parts) > 2 else "Seed"
    return parts[1]


def read_tsv(path: Path | None) -> list[list[str]]:
    return [ln.split("\t") for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()] if path else []


def library_candidates(
    isnad, library: str, record_lines: list[str], dep_lines: list[str], dep_module: dict[str, str], dates: dict[str, str]
) -> list[dict]:
    records = []
    seen: set[str] = set()
    for ln in record_lines:
        if ln.startswith("isnad1\t"):
            r = isnad.Record(ln)
            if r.name not in seen:
                seen.add(r.name)
                records.append(r)
    id_of = {r.name: r.id for r in records}
    module_of = {r.name: r.module for r in records}
    deps: dict[str, list[str]] = {}
    for ln in dep_lines:
        if ln.startswith(isnad.DEPS_TAG + "\t"):
            name, _, ds = isnad.parse_deps_line(ln)
            deps.setdefault(name, ds)
    out = []
    for r in records:
        own = {id_of[d] for d in deps.get(r.name, []) if d in id_of and id_of[d] != r.id}
        areas = set()
        for d in deps.get(r.name, []):
            module = module_of.get(d) or dep_module.get(d)
            if module:
                areas.add(domain_of(module))
        out.append(
            {
                "id": r.id,
                "name": r.name,
                "library": library,
                "module": r.module,
                "date": dates.get(r.module),
                "hyps": r.hyps,
                "size": max(r.nodes, 1).bit_length() - 1,
                "own_deps": len(own),
                "dep_domains": sorted(areas - NEUTRAL),
            }
        )
    return out


def with_aliases(rows: list[dict]) -> list[dict]:
    """how many other records (any library) state the same thing"""
    counts = Counter(r["id"] for r in rows)
    return [{**r, "aliases": counts[r["id"]] - 1} for r in rows]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--isnad-py", required=True)
    ap.add_argument("--library", nargs=4, action="append", metavar=("NAME", "ISNAD", "DEPS", "DEPMODULES"), required=True)
    ap.add_argument("--dates")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    isnad = load_module(Path(a.isnad_py))
    dates = {m: d for m, d in (r[:2] for r in read_tsv(Path(a.dates) if a.dates else None) if len(r) >= 2)}
    rows: list[dict] = []
    for name, isnad_tsv, deps_tsv, depmod_tsv in a.library:
        dep_module = {r[0]: r[1] for r in read_tsv(Path(depmod_tsv)) if len(r) >= 2}
        rows += library_candidates(
            isnad,
            name,
            Path(isnad_tsv).read_text(encoding="utf-8").splitlines(),
            Path(deps_tsv).read_text(encoding="utf-8").splitlines(),
            dep_module,
            dates,
        )
    rows = with_aliases(rows)
    Path(a.out).write_text("".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(
        json.dumps(
            {
                "candidates": len(rows),
                "libraries": len(a.library),
                "with_date": sum(1 for r in rows if r["date"]),
                "aliased": sum(1 for r in rows if r["aliases"]),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
