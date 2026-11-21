#!/usr/bin/env python3
"""pick.py - a seeded sample of theorems of one library, for the transplant measurement (.github/workflows/transplant.yml). Standard library only.

  pick.py ISNAD.tsv --n 30 --seed S --names NAMES.txt --modules MODULES.txt
  pick.py --candidates CANDIDATES.jsonl --libraries "Aintlib Compfiles" --n 30 --seed S --names NAMES.txt --modules MODULES.txt --sample SAMPLE.jsonl
  pick.py --manifests TENGOKU/data/intake --libraries "all" --n 10000 --seed S --names NAMES.txt --modules MODULES.txt --sample SAMPLE.jsonl     (no isnad pass: many libraries, ids not compared)

ISNAD.tsv is `tengoku-isnad` over a library's modules: ten tab-separated columns, `isnad1 name module kind hyps vars nodes canonical shape vocab` (Tengoku's scripts/isnad.py, Record.FIELDS). A theorem qualifies when it has a hypothesis and at least 32 nodes (docs/heldout-selection.md: no
one-liner counts), and a name is taken once. The order is sha256(seed + name): the same file and seed give the same sample. NAMES.txt has one name a line, MODULES.txt the modules those names live in.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

MIN_NODES = 32
MIN_SIZE_LOG2 = 5  # candidates.jsonl stores floor(log2(nodes)): 5 is 32 nodes


def qualifying(lines: list[str]) -> list[tuple[str, str]]:
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for ln in lines:
        p = ln.rstrip("\n").split("\t")
        if len(p) != 10 or p[0] != "isnad1":
            continue
        name, module, hyps, nodes = p[1], p[2], int(p[4]), int(p[6])
        if name in seen or hyps < 1 or nodes < MIN_NODES:
            continue
        seen.add(name)
        out.append((name, module))
    return out


def pick(rows: list[tuple[str, str]], n: int, seed: str) -> list[tuple[str, str]]:
    return sorted(rows, key=lambda r: hashlib.sha256(f"{seed}\n{r[0]}".encode()).hexdigest())[:n]


def pick_candidates(rows: list[dict], libraries: list[str], n: int, seed: str) -> list[dict]:
    """a sample over several libraries from the lines of candidates.jsonl (tools/campaign/candidates.py): the qualifying theorems of each library in seeded order, taken in turn, so every library is in
    the sample until it runs out (a sample of one big library and none of the others would measure one library)"""
    seen: set[str] = set()
    by_lib: dict[str, list[dict]] = {lib: [] for lib in libraries}
    for r in rows:
        if r["library"] in by_lib and r["name"] not in seen and r["hyps"] >= 1 and r["size"] >= MIN_SIZE_LOG2:
            seen.add(r["name"])
            by_lib[r["library"]].append(r)
    for lib in by_lib:
        by_lib[lib].sort(key=lambda r: hashlib.sha256(f"{seed}\n{r['name']}".encode()).hexdigest())
    out: list[dict] = []
    i = 0
    while len(out) < n and any(by_lib.values()):
        for lib in libraries:
            if by_lib[lib] and len(out) < n:
                out.append(by_lib[lib].pop(0))
        i += 1
    return out


def pick_manifests(root: Path, libraries: list[str], n: int, seed: str) -> list[dict]:
    """a sample over the intake manifests of a Tengoku checkout (`data/intake/<library>/manifest.jsonl`, one line per theorem the tree holds): the libraries in turn (all of them, or the ones named), the theorems
    of each in seeded order, so a sample over many libraries is spread over all of them. No isnad pass, so no statement id (`id` is null) and no size filter. Left out: a name that begins `_root_` (the manifest
    keeps it as the source wrote it), a row without a module of the tree, and a name a library before has (the tree holds each root name once)."""
    keys = libraries if libraries and libraries != ["all"] else sorted(p.parent.name for p in root.glob("*/manifest.jsonl"))
    seen: set[str] = set()
    by_lib: dict[str, list[dict]] = {}
    for lib in keys:
        path = root / lib / "manifest.jsonl"
        if not path.is_file():
            raise SystemExit(f"pick: no manifest for the library {lib!r} under {root}")
        rows: list[dict] = []
        for ln in path.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            r = json.loads(ln)
            name, module = r.get("name"), r.get("module")
            if not name or not module or not module.startswith("Tengoku.") or name.startswith("_root_") or name in seen:
                continue
            seen.add(name)
            rows.append({"name": name, "id": None, "library": lib, "module": module})
        rows.sort(key=lambda r: hashlib.sha256(f"{seed}\n{r['name']}".encode()).hexdigest())
        if rows:
            by_lib[lib] = rows
    out: list[dict] = []
    while len(out) < n and any(by_lib.values()):
        for lib in by_lib:
            if by_lib[lib] and len(out) < n:
                out.append(by_lib[lib].pop(0))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("isnad", nargs="?")
    ap.add_argument(
        "--manifests", help="data/intake of a Tengoku checkout: sample its manifests (--libraries: intake library keys, or `all`)"
    )
    ap.add_argument("--candidates")
    ap.add_argument("--libraries", default="")
    ap.add_argument("--sample")
    ap.add_argument("--n", type=int, required=True)
    ap.add_argument("--seed", required=True)
    ap.add_argument("--names", required=True)
    ap.add_argument("--modules", required=True)
    a = ap.parse_args(argv)
    if a.manifests:
        chosen = pick_manifests(Path(a.manifests), a.libraries.split(), a.n, a.seed)
        rows = [(r["name"], r["module"]) for r in chosen]
        if a.sample:
            Path(a.sample).write_text(
                "".join(json.dumps({k: r[k] for k in ("name", "id", "library", "module")}, sort_keys=True) + "\n" for r in chosen),
                encoding="utf-8",
            )
    elif a.candidates:
        cands = [json.loads(ln) for ln in Path(a.candidates).read_text(encoding="utf-8").splitlines() if ln.strip()]
        chosen = pick_candidates(cands, a.libraries.split(), a.n, a.seed)
        rows = [(r["name"], r["module"]) for r in chosen]
        if a.sample:
            Path(a.sample).write_text(
                "".join(json.dumps({k: r[k] for k in ("name", "id", "library", "module")}, sort_keys=True) + "\n" for r in chosen),
                encoding="utf-8",
            )
    elif a.isnad:
        rows = pick(qualifying(Path(a.isnad).read_text(encoding="utf-8").splitlines()), a.n, a.seed)
    else:
        ap.error("give ISNAD.tsv or --candidates")
    if len(rows) < a.n:
        print(f"pick: only {len(rows)} theorems qualify, asked for {a.n}", file=sys.stderr)
    Path(a.names).write_text("".join(f"{r[0]}\n" for r in rows), encoding="utf-8")
    Path(a.modules).write_text("".join(f"{m}\n" for m in sorted({r[1] for r in rows})), encoding="utf-8")
    print(f"picked {len(rows)} theorems from {len({r[1] for r in rows})} modules")
    return 0


if __name__ == "__main__":
    sys.exit(main())
