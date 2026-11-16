#!/usr/bin/env python3
"""groups.py - find the statement groups of the tree (theorems sharing one isnad id) without compiling it.

  groups.py scan TENGOKU_DIR > dup.json        # tag lines `@isnad1 id=...` in the sources: ids that occur twice or more, and the modules that hold them
  groups.py meta --dup dup.json --isnad-py TENGOKU_DIR/scripts/isnad.py < tengoku-isnad.tsv > meta.tsv
                                                # raw `tengoku-isnad` records of those modules: keep the theorems whose recomputed id is a duplicate one

`meta.tsv` is the `--meta` table of tools/closure/closure.py: name, isnad id, library, module (tab separated). A group found this way is a LOWER BOUND of the real one:
a theorem the sweep has not tagged yet is not seen. The sweep's progress is therefore part of every calibration run's output (`dup.json` says how many tags were read).
The library of a module is the component after `Tengoku.` (the top-level directories of the tree are the libraries).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

TAG = re.compile(r"@isnad1 id=(\S+)")


def module_of(root: Path, path: Path) -> str:
    return ".".join(path.relative_to(root).with_suffix("").parts)


def lib_of(module: str) -> str:
    parts = module.split(".")
    return parts[1] if len(parts) > 1 and parts[0] == "Tengoku" else parts[0]


def scan(root: Path) -> dict:
    """ids -> modules, for the ids that occur at least twice (counting each tag line), and how many tags were read."""
    seen: dict[str, list[str]] = {}
    total = 0
    for f in sorted((root / "Tengoku").rglob("*.lean")):
        text = f.read_text(encoding="utf-8", errors="replace")
        if "@isnad1" not in text:
            continue
        mod = module_of(root, f)
        for tag_id in TAG.findall(text):
            total += 1
            seen.setdefault(tag_id, []).append(mod)
    dup = {i: sorted(m) for i, m in seen.items() if len(m) >= 2}
    return {"tags_read": total, "distinct_ids": len(seen), "dup": dup, "modules": sorted({m for ms in dup.values() for m in ms})}


def meta_rows(lines, dup_ids: set[str], record_cls) -> list[tuple[str, str, str, str]]:
    rows = []
    for line in lines:
        if not line.startswith("isnad"):
            continue
        r = record_cls(line)
        if r.id in dup_ids:
            rows.append((r.name, r.id, lib_of(r.module), r.module))
    return sorted(rows)


def _load_record(isnad_py: Path):
    spec = importlib.util.spec_from_file_location("tengoku_isnad_py", isnad_py)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod.Record


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scan").add_argument("root")
    m = sub.add_parser("meta")
    m.add_argument("--dup", required=True)
    m.add_argument("--isnad-py", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "scan":
        print(json.dumps(scan(Path(a.root)), sort_keys=True, indent=1))
        return 0
    dup_ids = set(json.loads(Path(a.dup).read_text())["dup"])
    for row in meta_rows(sys.stdin, dup_ids, _load_record(Path(a.isnad_py))):
        print("\t".join(row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
