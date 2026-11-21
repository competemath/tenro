#!/usr/bin/env python3
"""export_stats.py - the size of a lean4export file by kind of line, and what the export cost. Standard library, with `grep` (a count of a 10 GB file in seconds) and `zstd` when they are there.

  export_stats.py EXPORT.ndjson [--time-log ERR] [--label NAME] [--out STATS.json]

Counts the lines of each kind (names, universe levels, terms, and each kind of declaration), the bytes, the size with zstd -3, and, from the stderr of `/usr/bin/time -v lake env lean4export ...` (`--time-log`), the wall time and
the peak resident memory. Prints a markdown paragraph for a step summary and writes the figures as JSON. The kinds are read from the line itself: lean4export writes compressed JSON with the keys in order, so a name
line begins `{"in":`, a level `{"il":`, a declaration `{"axiom":`, `{"def":` ... and a term has `"ie":` in it (the key comes first or last, whichever sorts first).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

DECLARATIONS = ("axiom", "def", "inductive", "opaque", "quot", "thm")


def grep_count(path: Path, pattern: str) -> int:
    """the number of lines of the file that match the extended regular expression"""
    if shutil.which("grep") is None:
        rx = re.compile(pattern)
        with open(path, "rb") as f:
            return sum(1 for ln in f if rx.search(ln.decode("utf-8", errors="replace")))
    r = subprocess.run(["grep", "-c", "-E", pattern, str(path)], capture_output=True, text=True)
    return int(r.stdout.strip() or 0)  # exit 1 with 0 matches is not an error


def parse_time_log(text: str) -> dict:
    """wall seconds and peak resident kilobytes from the output of `/usr/bin/time -v`"""
    wall = re.search(r"Elapsed \(wall clock\) time \(h:mm:ss or m:ss\): ([0-9:.]+)", text)
    rss = re.search(r"Maximum resident set size \(kbytes\): (\d+)", text)
    seconds = None
    if wall:
        seconds = 0.0
        for part in wall.group(1).split(":"):
            seconds = seconds * 60 + float(part)
    return {"wall_seconds": seconds, "max_rss_kb": int(rss.group(1)) if rss else None}


def compressed_bytes(path: Path) -> int | None:
    if shutil.which("zstd") is None:
        return None
    p1 = subprocess.Popen(["zstd", "-3", "-T0", "-c", str(path)], stdout=subprocess.PIPE)
    assert p1.stdout is not None
    size = sum(len(chunk) for chunk in iter(lambda: p1.stdout.read(1 << 20), b""))
    p1.wait()
    return size


def stats(path: Path, time_log: Path | None = None, label: str = "") -> dict:
    out = {
        "label": label,
        "bytes": path.stat().st_size,
        "lines": grep_count(path, "^"),
        "names": grep_count(path, r'^\{"in":'),
        "levels": grep_count(path, r'^\{"il":'),
        "terms": grep_count(path, r'"ie":'),
        "declarations": {k: grep_count(path, rf'^\{{"{k}":') for k in DECLARATIONS},
        "zstd3_bytes": compressed_bytes(path),
    }
    if time_log is not None:
        out.update(parse_time_log(time_log.read_text(encoding="utf-8", errors="replace")))
    return out


def markdown(s: dict) -> str:
    d = s["declarations"]
    cost = ""
    if s.get("wall_seconds") is not None:
        cost = f"; export {s['wall_seconds'] / 60:.1f} min" + (f", peak {s['max_rss_kb'] / 1e6:.1f} GB" if s.get("max_rss_kb") else "")
    zst = f" ({s['zstd3_bytes'] / 1e6:,.0f} MB with zstd -3)" if s.get("zstd3_bytes") else ""
    return (
        f"### {s['label'] or 'an export'}\n\n"
        f"{s['lines']:,} lines, {s['bytes'] / 1e6:,.0f} MB{zst}{cost}.\n\n"
        "| names | levels | terms | axioms | definitions | inductive groups | opaque | quot | theorems |\n"
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n"
        f"| {s['names']:,} | {s['levels']:,} | {s['terms']:,} | {d['axiom']:,} | {d['def']:,} | {d['inductive']:,} | {d['opaque']:,} | {d['quot']:,} | {d['thm']:,} |\n"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("export", type=Path)
    ap.add_argument("--time-log", type=Path)
    ap.add_argument("--label", default="")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    s = stats(a.export, a.time_log, a.label)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(json.dumps(s, indent=1, sort_keys=True) + "\n")
    print(markdown(s), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
