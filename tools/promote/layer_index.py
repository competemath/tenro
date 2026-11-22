#!/usr/bin/env python3
"""layer_index.py - which layer holds the statement of each theorem of a layered snapshot. Standard library only.

  layer_index.py --layers DIR --sample SAMPLE.jsonl --out INDEX_DIR

DIR is what `layers.py` wrote (`layers.json` and the `<module>.names.jsonl` of every layer), SAMPLE.jsonl the sample the layers were planned for (one JSON object a line with `name` and `library`).
A session that wants a theorem imports the layer that holds it, and that layer imports the foundation (`layers.json`, "imports"): this is the table that says which layer that is, without opening an olean.
A theorem's statement is one unit of its own, so its layer is the layer of the unit that starts with its name: the foundation when two libraries or more need it, the layer of its library when only that
library does. A sampled name that no layer starts with (a name the exporter did not find was already taken out of the sample by `missing.py`) is counted as `unplaced`, never guessed.

Writes, in INDEX_DIR (deterministic: sorted, one JSON object a line):
  layers.jsonl        {"name": theorem name, "library": its library, "layer": the module that holds its statement}
  layers-stats.json   the counts: theorems, placed, unplaced, per layer, how many statements are in the foundation, and the sha256 of layers.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path


def dotted(components: list) -> str:
    """the name as closure.py writes it: the components joined by dots, a numeric component as its digits"""
    return ".".join(str(c) for c in components)


def layer_of_names(layers_dir: Path) -> tuple[dict[str, str], list[str]]:
    """the layer of every unit, by the name the unit starts with, and the modules in the order of layers.json"""
    plan = json.loads((layers_dir / "layers.json").read_text(encoding="utf-8"))
    owner: dict[str, str] = {}
    modules: list[str] = []
    for layer in plan["layers"]:
        modules.append(layer["module"])
        path = layers_dir / layer["file"]
        for ln in path.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                name = dotted(json.loads(ln))
                if name in owner:
                    raise SystemExit(f"layer_index: {name} starts a unit in {owner[name]} and in {layer['module']}")
                owner[name] = layer["module"]
    return owner, modules


def build(layers_dir: Path, sample: list[dict]) -> tuple[list[dict], dict]:
    owner, modules = layer_of_names(layers_dir)
    plan = json.loads((layers_dir / "layers.json").read_text(encoding="utf-8"))
    foundation = next((x["module"] for x in plan["layers"] if x["topic"] is None), None)
    rows: list[dict] = []
    unplaced: list[str] = []
    for r in sample:
        layer = owner.get(r["name"])
        if layer is None:
            unplaced.append(r["name"])
        else:
            rows.append({"name": r["name"], "library": r["library"], "layer": layer})
    rows.sort(key=lambda r: r["name"])
    per_layer = Counter(r["layer"] for r in rows)
    stats = {
        "theorems": len(sample),
        "placed": len(rows),
        "unplaced": len(unplaced),
        "unplaced_examples": sorted(unplaced)[:10],
        "in_foundation": per_layer.get(foundation, 0) if foundation else 0,
        "layers_with_theorems": len(per_layer),
        "per_layer": {m: per_layer[m] for m in modules if per_layer.get(m)},
    }
    return rows, stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--layers", required=True, type=Path)
    ap.add_argument("--sample", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)
    sample = [json.loads(ln) for ln in a.sample.read_text(encoding="utf-8").splitlines() if ln.strip()]
    rows, stats = build(a.layers, sample)
    a.out.mkdir(parents=True, exist_ok=True)
    body = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows)
    (a.out / "layers.jsonl").write_text(body, encoding="utf-8")
    stats["sha256"] = {"layers.jsonl": hashlib.sha256(body.encode("utf-8")).hexdigest()}
    (a.out / "layers-stats.json").write_text(json.dumps(stats, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"layer index: {stats['placed']:,} of {stats['theorems']:,} theorems placed ({stats['unplaced']:,} unplaced), "
        f"{stats['in_foundation']:,} statements in the foundation, {stats['layers_with_theorems']:,} layers hold theorems"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
