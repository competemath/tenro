#!/usr/bin/env python3
"""groups.py - find the statement groups of the tree (theorems sharing one isnad id) without compiling it.

  groups.py scan TENGOKU_DIR > dup.json        # tag lines `@isnad1 id=...` in the sources: ids that occur twice or more, and the modules that hold them
  groups.py select --max-groups N --stats stats.json < meta.tsv > meta-selected.tsv    # the groups that need a closure: cross-library ones, a deterministic sample
  groups.py meta --dup dup.json --isnad-py TENGOKU_DIR/scripts/isnad.py < tengoku-isnad.tsv > meta.tsv
                                                # raw `tengoku-isnad` records of those modules: keep the theorems whose recomputed id is a duplicate one

`meta.tsv` is the `--meta` table of tools/closure/closure.py: name, isnad id, library, module (tab separated). A group found this way is a LOWER BOUND of the real one:
a theorem the sweep has not tagged yet is not seen. The sweep's progress is therefore part of every calibration run's output (`dup.json` says how many tags were read).
The library of a module is the component after `Tengoku.` (the top-level directories of the tree are the libraries).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from tengoku_isnad import load_module  # noqa: E402

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


def select_groups(
    rows: list[tuple[str, str, str, str]], max_groups: int, max_members: int = 4
) -> tuple[list[tuple[str, str, str, str]], dict]:
    """Which groups need a closure at all. A group whose theorems all come from ONE library is an alias by the protocol's first rule (same chain), with no closure computed; only groups
    with theorems from at least two libraries can be anything else. Of those, a deterministic sample (by the hash of the id, so a rerun picks the same ones) of `max_groups`, each cut to
    at most `max_members` theorems, one per library first. rows: (name, id, lib, module). Returns the selected rows and the counts."""
    by_id: dict[str, list[tuple[str, str, str, str]]] = {}
    for r in rows:
        by_id.setdefault(r[1], []).append(r)
    cross = {i: g for i, g in by_id.items() if len({r[2] for r in g}) >= 2}
    order = sorted(cross, key=lambda i: hashlib.sha256(i.encode()).hexdigest())[:max_groups]
    out: list[tuple[str, str, str, str]] = []
    for i in order:
        g = sorted(cross[i], key=lambda r: (r[2], r[0]))
        firsts = [next(r for r in g if r[2] == lib) for lib in sorted({r[2] for r in g})]
        rest = [r for r in g if r not in firsts]
        out += sorted((firsts + rest)[:max_members])
    stats = {
        "groups": len(by_id),
        "single_library_groups": len(by_id) - len(cross),
        "cross_library_groups": len(cross),
        "selected_groups": len(order),
        "selected_theorems": len(out),
    }
    return out, stats


def _load_record(isnad_py: Path):
    return load_module(isnad_py).Record


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scan").add_argument("root")
    sel = sub.add_parser("select")
    sel.add_argument("--max-groups", type=int, default=150)
    sel.add_argument("--stats", type=Path, required=True)
    for name in ("counts", "modules", "tags"):  # read dup.json on stdin: a one-line summary, the module list, the number of tags read
        sub.add_parser(name)
    m = sub.add_parser("meta")
    m.add_argument("--dup", required=True)
    m.add_argument("--isnad-py", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "scan":
        print(json.dumps(scan(Path(a.root)), sort_keys=True, indent=1))
        return 0
    if a.cmd == "select":
        rows = [tuple(ln.rstrip("\n").split("\t")[:4]) for ln in sys.stdin if ln.strip()]
        chosen, stats = select_groups(rows, a.max_groups)
        a.stats.write_text(json.dumps(stats, sort_keys=True, indent=1) + "\n", encoding="utf-8")
        for r in chosen:
            print("\t".join(r))
        return 0
    if a.cmd in ("counts", "modules", "tags"):
        d = json.load(sys.stdin)
        if a.cmd == "counts":
            print(f"tags {d['tags_read']}, ids {d['distinct_ids']}, duplicate ids {len(d['dup'])}, modules {len(d['modules'])}")
        elif a.cmd == "modules":
            print("\n".join(d["modules"]))
        else:
            print(d["tags_read"])
        return 0
    dup_ids = set(json.loads(Path(a.dup).read_text())["dup"])
    for row in meta_rows(sys.stdin, dup_ids, _load_record(Path(a.isnad_py))):
        print("\t".join(row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
