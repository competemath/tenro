#!/usr/bin/env python3
"""build.py - the name-blind indexes (Tengai docs/design.md, "indexes/"): the pattern-shape index and the static dependency graph, by statement id.

  build.py --isnad ISNAD.tsv --deps DEPS.tsv --isnad-py TENGOKU/scripts/isnad.py --out DIR

ISNAD.tsv is the output of `tengoku-isnad` (one `isnad1` record per theorem), DEPS.tsv the output of `tengoku-isnad --deps` (`isnad1-deps` lines, Tengoku PR for the
`deps` hash). Records are parsed and ids computed by Tengoku's own isnad.py, so the recipe is not copied here. Output, in DIR, deterministic (sorted, one JSON object a line):

  shape.jsonl   {"shape": 8 hex, "ids": [statement ids]}       the cheap prefilter: a theorem of this pattern shape may state one of these (the full id decides, never the shape)
  graph.jsonl   {"id": statement id, "deps": [statement ids]}   what each statement's proofs lean on directly (union over the theorems that state it)
  names.jsonl   {"id": statement id, "names": [theorem names]}  the ONLY place names appear: the other files are name-blind by construction, so a prover or a scrambler
                                                                that reads the indexes cannot see what a theorem is called
  stats.json    counts, shape collisions (one shape, several ids), dependencies dropped because their statement has no id in the input, and the sha256 of each file (the manifest)

The `intent` (text) index is built from docstrings by a separate step: it needs the sources, not the compiled records.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from tengoku_isnad import load_isnad  # noqa: E402


def build(records: list[tuple[str, str, str]], deps: list[tuple[str, list[str]]]) -> dict:
    """records: (name, statement id, shape); deps: (theorem name, dependency names). Returns the three indexes and the statistics."""
    id_of = {name: ident for name, ident, _ in records}
    shapes: dict[str, set[str]] = {}
    names: dict[str, set[str]] = {}
    for name, ident, shape in records:
        shapes.setdefault(shape, set()).add(ident)
        names.setdefault(ident, set()).add(name)
    graph: dict[str, set[str]] = {ident: set() for ident in names}
    dropped = 0
    for name, dep_names in deps:
        ident = id_of.get(name)
        if ident is None:
            continue
        for d in dep_names:
            if d in id_of:
                graph[ident].add(id_of[d])
            else:
                dropped += 1
    return {
        "shape": [{"shape": s, "ids": sorted(ids)} for s, ids in sorted(shapes.items())],
        "graph": [{"id": i, "deps": sorted(d)} for i, d in sorted(graph.items())],
        "names": [{"id": i, "names": sorted(n)} for i, n in sorted(names.items())],
        "stats": {
            "theorems": len(records),
            "statements": len(names),
            "shapes": len(shapes),
            "shape_collisions": sum(1 for ids in shapes.values() if len(ids) > 1),
            "edges": sum(len(d) for d in graph.values()),
            "dropped_dependencies": dropped,
        },
    }


def write(out: Path, built: dict) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for key in ("shape", "graph", "names"):
        text = "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in built[key])
        (out / f"{key}.jsonl").write_text(text, encoding="utf-8")
        hashes[f"{key}.jsonl"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    stats = {**built["stats"], "sha256": hashes}
    (out / "stats.json").write_text(json.dumps(stats, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--isnad", type=Path, required=True)
    ap.add_argument("--deps", type=Path, required=True)
    ap.add_argument("--isnad-py", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    records, deps = load_isnad(
        a.isnad_py, a.isnad.read_text(encoding="utf-8").splitlines(), a.deps.read_text(encoding="utf-8").splitlines()
    )
    print(json.dumps(write(a.out, build(records, deps)), sort_keys=True, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
