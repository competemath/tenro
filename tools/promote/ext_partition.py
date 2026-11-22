#!/usr/bin/env python3
"""ext_partition.py - the extension entries of Tengoku's constants, split by the layer that holds each constant. Standard library only.

  ext_partition.py EXT.jsonl --layers DIR --out OUT_DIR

EXT.jsonl is what `tengai-extinfo` printed in Tengoku's environment for every constant of the layers (one JSON object a line, `{"n": [name components], ...}` with `red`, `proj`, `class`, `st`, `inst` and `bi`, the
entries Lean keeps about a constant outside the kernel and the binder annotations of its type). DIR is what `layers.py` wrote (`layers.json` and the `<module>.constants.jsonl` of every layer). Each layer is
replayed by its own process (`tengai-replay --only ... --ext`): given the whole file, every one of the (hundreds of) processes would parse all of it, and Lean's JSON reader is slow, so each gets the rows of
the constants it adds and nothing else.

Writes, in OUT_DIR, `<module>.ext.jsonl` for each layer that has a row (the lines as they were read, in their order), and `ext-partition.json`: how many rows, how many were placed, and per layer and in all how many
of each kind. **A row of a constant that no layer holds is an error** (the names were asked of the layers, so a row outside them means the two disagree: nothing is dropped without a word), and so is a line that is
not a row.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

KINDS = ("red", "proj", "class", "st", "inst", "bi")


def owners(layers_dir: Path) -> tuple[dict[tuple, str], list[str]]:
    """the module that holds each constant, by the components of its name, and the modules in the order of layers.json"""
    plan = json.loads((layers_dir / "layers.json").read_text(encoding="utf-8"))
    owner: dict[tuple, str] = {}
    modules: list[str] = []
    for layer in plan["layers"]:
        modules.append(layer["module"])
        for ln in (layers_dir / layer["constants_file"]).read_text(encoding="utf-8").splitlines():
            if ln.strip():
                owner[tuple(json.loads(ln))] = layer["module"]
    return owner, modules


def partition(lines, owner: dict[tuple, str]) -> tuple[dict[str, list[str]], dict]:
    """the rows of each layer (the lines, untouched), and the counts"""
    rows: dict[str, list[str]] = {}
    kinds: dict[str, Counter] = {}
    total = 0
    for ln in lines:
        if not ln.strip():
            continue
        total += 1
        try:
            row = json.loads(ln)
            name = tuple(row["n"])
        except (ValueError, KeyError, TypeError) as e:
            raise SystemExit(f"ext_partition: line {total} is not a row of tengai-extinfo ({e!r}): {ln.strip()[:120]}") from e
        module = owner.get(name)
        if module is None:
            raise SystemExit(
                f"ext_partition: the row of {'.'.join(str(c) for c in name)} (line {total}) names a constant that no layer holds"
            )
        rows.setdefault(module, []).append(ln if ln.endswith("\n") else ln + "\n")
        kinds.setdefault(module, Counter()).update(k for k in KINDS if k in row)
    report = {
        "rows": total,
        "placed": sum(len(v) for v in rows.values()),
        "layers": {m: {"rows": len(rows[m]), "kinds": dict(sorted(kinds[m].items()))} for m in rows},
        "kinds": dict(sorted(sum(kinds.values(), Counter()).items())),
    }
    return rows, report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ext", type=Path)
    ap.add_argument("--layers", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)
    owner, modules = owners(a.layers)
    with open(a.ext, encoding="utf-8") as f:
        rows, report = partition(f, owner)
    a.out.mkdir(parents=True, exist_ok=True)
    for module, lines in rows.items():
        (a.out / f"{module}.ext.jsonl").write_text("".join(lines), encoding="utf-8")
    (a.out / "ext-partition.json").write_text(json.dumps(report, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"ext_partition: {report['rows']:,} rows, {report['placed']:,} placed in {len(rows)} of {len(modules)} layers; "
        + ", ".join(f"{k} {n:,}" for k, n in report["kinds"].items())
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
