#!/usr/bin/env python3
"""pick.py - a seeded sample of theorems of one library, for the transplant measurement (.github/workflows/transplant.yml). Standard library only.

  pick.py ISNAD.tsv --n 30 --seed S --names NAMES.txt --modules MODULES.txt

ISNAD.tsv is `tengoku-isnad` over a library's modules (`isnad1<TAB>name<TAB>module<TAB>hyps<TAB>nodes<TAB>id...`). A theorem qualifies when it has a hypothesis and at least 32 nodes (docs/heldout-selection.md: no
one-liner counts), and a name is taken once. The order is sha256(seed + name): the same file and seed give the same sample. NAMES.txt has one name a line, MODULES.txt the modules those names live in.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

MIN_NODES = 32


def qualifying(lines: list[str]) -> list[tuple[str, str]]:
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for ln in lines:
        p = ln.rstrip("\n").split("\t")
        if len(p) < 6 or p[0] != "isnad1":
            continue
        name, module = p[1], p[2]
        if name in seen or int(p[3]) < 1 or int(p[4]) < MIN_NODES:
            continue
        seen.add(name)
        out.append((name, module))
    return out


def pick(rows: list[tuple[str, str]], n: int, seed: str) -> list[tuple[str, str]]:
    return sorted(rows, key=lambda r: hashlib.sha256(f"{seed}\n{r[0]}".encode()).hexdigest())[:n]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("isnad")
    ap.add_argument("--n", type=int, required=True)
    ap.add_argument("--seed", required=True)
    ap.add_argument("--names", required=True)
    ap.add_argument("--modules", required=True)
    a = ap.parse_args(argv)
    rows = pick(qualifying(Path(a.isnad).read_text(encoding="utf-8").splitlines()), a.n, a.seed)
    if len(rows) < a.n:
        print(f"pick: only {len(rows)} theorems qualify, asked for {a.n}", file=sys.stderr)
    Path(a.names).write_text("".join(f"{r[0]}\n" for r in rows), encoding="utf-8")
    Path(a.modules).write_text("".join(f"{m}\n" for m in sorted({r[1] for r in rows})), encoding="utf-8")
    print(f"picked {len(rows)} theorems from {len({r[1] for r in rows})} modules")
    return 0


if __name__ == "__main__":
    sys.exit(main())
