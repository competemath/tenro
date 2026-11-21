#!/usr/bin/env python3
"""missing.py - the sampled names that are not constants of the tree, taken out of the sample. Standard library only.

  missing.py --err EXPORT.err --names NAMES.txt [--sample SAMPLE.jsonl] [--out MISSING.txt]

`lean4export ... -- NAMES` of a name that is not a constant of the environment prints `PANIC at dumpConstant ...: Constant X not found in environment.` on stderr and goes on, so the export is whole and the name is simply
not in it (a sample of the intake manifests, `pick.py --manifests`, can name a theorem whose manifest name is not the name the tree gave the constant: 38 of 8,000 in the first run of 16 libraries, almost all of Physlib).
The names are taken out of NAMES.txt and SAMPLE.jsonl, written to MISSING.txt, and counted by library; a panic of any other kind is an error, not something to drop. Nothing is dropped silently: the count and the libraries are printed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

NOT_FOUND = re.compile(r"^PANIC at dumpConstant [^:]+:\d+:\d+: Constant (.+) not found in environment\.$")
ANY_PANIC = re.compile(r"^PANIC\b")


def read_missing(text: str) -> tuple[list[str], list[str]]:
    """(the names the exporter did not find, in order and once; the other panic lines)"""
    missing: list[str] = []
    other: list[str] = []
    for ln in text.splitlines():
        m = NOT_FOUND.match(ln)
        if m:
            if m.group(1) not in missing:
                missing.append(m.group(1))
        elif ANY_PANIC.match(ln):
            other.append(ln)
    return missing, other


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--err", required=True)
    ap.add_argument("--names", required=True)
    ap.add_argument("--sample")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    missing, other = read_missing(Path(a.err).read_text(encoding="utf-8", errors="replace"))
    if other:
        print(f"missing: the exporter panicked for another reason ({len(other)} lines), first: {other[0]}", file=sys.stderr)
        return 1
    gone = set(missing)
    names = [n for n in Path(a.names).read_text(encoding="utf-8").splitlines() if n.strip()]
    kept = [n for n in names if n not in gone]
    Path(a.names).write_text("".join(f"{n}\n" for n in kept), encoding="utf-8")
    by_library: Counter[str] = Counter()
    if a.sample:
        rows = [json.loads(ln) for ln in Path(a.sample).read_text(encoding="utf-8").splitlines() if ln.strip()]
        for r in rows:
            if r["name"] in gone:
                by_library[r["library"]] += 1
        Path(a.sample).write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows if r["name"] not in gone), encoding="utf-8")
    if a.out:
        Path(a.out).write_text("".join(f"{n}\n" for n in missing), encoding="utf-8")
    print(
        f"missing: {len(missing)} of {len(names)} sampled names are not constants of the tree, taken out of the sample"
        + (f"; by library {dict(by_library)}" if by_library else "")
    )
    return 1 if names and not kept else 0


if __name__ == "__main__":
    sys.exit(main())
