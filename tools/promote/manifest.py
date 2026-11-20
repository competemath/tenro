#!/usr/bin/env python3
"""manifest.py - the record of one transplant: what went in, from which pins, and what was checked. Standard library only.

  manifest.py --dir DIR --out MANIFEST.json --export EXPORT.ndjson --olean MODULE.olean [--pin KEY=VALUE ...]

DIR holds what `.github/workflows/transplant.yml` leaves behind: sample.jsonl (name, id, library, module of every theorem), replay-stats.json, import-empty.json, import-sample.json, nanoda.out,
nanoda.status, statement-ids.json, axioms.txt. The manifest has no clock: the same inputs give the same file, so it can be committed and diffed. It states the pins (Tengoku commit, tengai tag,
exporter and checker commits), the sample, the sizes and hashes of the export and the built module (plain and compressed), and the verdict of every check. A check that did not run is `null`, never `true`.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import sys
from pathlib import Path

ALLOWED_AXIOMS = ("Classical.choice", "Quot.sound", "propext")


def sha256_and_sizes(path: Path) -> dict:
    """bytes, sha256 and the gzip size, in one pass over the file"""
    h = hashlib.sha256()
    n = 0
    gz = 0

    class Count:
        def write(self, b: bytes) -> int:
            nonlocal gz
            gz += len(b)
            return len(b)

        def flush(self) -> None:
            pass

    with open(path, "rb") as f, gzip.GzipFile(fileobj=Count(), mode="wb", compresslevel=6) as z:
        while chunk := f.read(1 << 20):
            h.update(chunk)
            z.write(chunk)
            n += len(chunk)
    return {"bytes": n, "sha256": h.hexdigest(), "gzip_bytes": gz}


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def axioms_check(text: str, names: list[str]) -> dict | None:
    """what `#print axioms` said of every sampled theorem: None when there is no output, else the union and whether it stays inside the standard three"""
    if not text.strip():
        return None
    seen: dict[str, set[str]] = {}
    # a name may contain `'` and Lean wraps a long line: the name runs to the last quote before `depends`/`does`, and the gap may be a newline
    for m in re.finditer(r"'(.+?)'\s+(?:depends on axioms:\s*\[([^\]]*)\]|does not depend on any axioms)", text, re.S):
        seen[m.group(1).strip()] = {a.strip() for a in (m.group(2) or "").replace("\n", " ").split(",") if a.strip()}
    union = sorted(set().union(*seen.values())) if seen else []
    return {
        "theorems": len(seen),
        "all_printed": set(seen) == set(names),
        "axioms": union,
        "standard_only": set(union) <= set(ALLOWED_AXIOMS),
    }


def build(d: Path, export: Path | None, olean: Path | None, pins: dict[str, str]) -> dict:
    sample = (
        [json.loads(ln) for ln in (d / "sample.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
        if (d / "sample.jsonl").exists()
        else []
    )
    names = [r["name"] for r in sample]
    stats = read_json(d / "replay-stats.json")
    empty, with_sample = read_json(d / "import-empty.json"), read_json(d / "import-sample.json")
    ids = read_json(d / "statement-ids.json")
    nanoda_status = (d / "nanoda.status").read_text(encoding="utf-8").strip() if (d / "nanoda.status").exists() else None
    declared = (
        re.findall(r"Checked (\d+) declarations with no errors", (d / "nanoda.out").read_text(encoding="utf-8"))
        if (d / "nanoda.out").exists()
        else []
    )
    axioms_text = (d / "axioms.txt").read_text(encoding="utf-8") if (d / "axioms.txt").exists() else ""
    return {
        "schema": 1,
        "pins": dict(sorted(pins.items())),
        "libraries": sorted({r["library"] for r in sample}),
        "theorems": sorted(sample, key=lambda r: r["name"]),
        "replay": stats,
        "artifact": {
            "export": sha256_and_sizes(export) if export else None,
            "olean": sha256_and_sizes(olean) if olean else None,
        },
        "checks": {
            "kernel": "accepted" if stats else None,
            "nanoda": {"status": nanoda_status, "declarations": int(declared[-1])}
            if nanoda_status and declared
            else ({"status": nanoda_status, "declarations": None} if nanoda_status else None),
            "statement_ids": None
            if ids is None
            else {"names": ids["names"], "equal": ids["equal"], "drift": [d["name"] for d in ids.get("drift", [])], "ok": ids["ok"]},
            "axioms": axioms_check(axioms_text, names),
            "cold_import_s": None
            if not (empty and with_sample)
            else {
                "empty_median": empty["median"],
                "sample_median": with_sample["median"],
                "net": round(with_sample["median"] - empty["median"], 4),
            },
        },
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--export")
    ap.add_argument("--olean")
    ap.add_argument("--pin", action="append", default=[], help="KEY=VALUE")
    a = ap.parse_args(argv)
    pins = dict(p.split("=", 1) for p in a.pin)
    m = build(Path(a.dir), Path(a.export) if a.export else None, Path(a.olean) if a.olean else None, pins)
    Path(a.out).write_text(json.dumps(m, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "theorems": len(m["theorems"]),
                "libraries": m["libraries"],
                "checks": {k: (v if not isinstance(v, dict) else "…") for k, v in m["checks"].items()},
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
