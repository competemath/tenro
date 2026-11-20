#!/usr/bin/env python3
"""compare_ids.py - the promotion lens, checked: every transplanted theorem states in tengai exactly what it stated in Tengoku. Standard library only (Tengoku's isnad.py is loaded, never copied).

  compare_ids.py --isnad-py TOOLS/scripts/isnad.py --names NAMES.txt --source ISNAD_TENGOKU.tsv --replayed ISNAD_REPLAYED.tsv [--out REPORT.json]

SOURCE is `tengoku-isnad` over the Tengoku modules the sample came from; REPLAYED is `tengoku-isnad` over the replayed module, run in an environment that holds the replayed constants and Lean core alone.
For each name in NAMES the statement id (`kind.<hyps>h<vars>v.s<size>.<sha of the canonical statement>`) must be the same in both: the id is the canonical elaborated statement, so equal ids mean the
replayed theorem says what the Tengoku one said. The report has the counts and every name that is missing or differs; the exit code is 1 if there is one.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from tengoku_isnad import load_module  # noqa: E402


def ids_of(isnad, lines: list[str], wanted: set[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for ln in lines:
        if ln.startswith(f"isnad{isnad.VERSION}\t"):
            r = isnad.Record(ln)
            if r.name in wanted and r.name not in out:
                out[r.name] = r.id
    return out


def compare(names: list[str], source: dict[str, str], replayed: dict[str, str]) -> dict:
    missing_source = [n for n in names if n not in source]
    missing_replayed = [n for n in names if n in source and n not in replayed]
    different = [
        {"name": n, "source": source[n], "replayed": replayed[n]}
        for n in names
        if n in source and n in replayed and source[n] != replayed[n]
    ]
    equal = sum(1 for n in names if n in source and n in replayed and source[n] == replayed[n])
    return {
        "names": len(names),
        "equal": equal,
        "missing_in_source": missing_source,
        "missing_in_replayed": missing_replayed,
        "different": different,
        "ok": equal == len(names),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--isnad-py", required=True)
    ap.add_argument("--names", required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--replayed", required=True)
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    isnad = load_module(Path(a.isnad_py))
    names = [n for n in Path(a.names).read_text(encoding="utf-8").splitlines() if n.strip()]
    wanted = set(names)
    source = ids_of(isnad, Path(a.source).read_text(encoding="utf-8").splitlines(), wanted)
    replayed = ids_of(isnad, Path(a.replayed).read_text(encoding="utf-8").splitlines(), wanted)
    report = compare(names, source, replayed)
    text = json.dumps(report, sort_keys=True)
    if a.out:
        Path(a.out).write_text(text + "\n", encoding="utf-8")
    print(text[:2000])
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
