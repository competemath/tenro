#!/usr/bin/env python3
"""dates.py - when a module of a Tengoku library first appeared upstream (the `date` of docs/heldout-selection.md). Standard library and `git` only.

  dates.py --sources SOURCES.json --library LIB --modules MODULES.txt --out DATES.tsv [--workdir DIR]

LIB is the library directory under Tengoku/ (`Aintlib`); its upstream repository and pinned commit are the `corpora` entry of SOURCES.json (Tengoku's schemas/sources.json) whose key is the library name in lower case
(a library with no such entry has no dates).
MODULES.txt has one Tengoku module a line (`Tengoku.Aintlib.Foo.Bar`). DATES.tsv has `module<TAB>YYYY-MM-DD` for each module whose date is known.

The date of a module is the author date of the commit that first ADDED its file upstream, in the history up to the pinned commit. The Tengoku intake date is not used: it is when we copied the file, not when it was written.
Every doubt leaves the module without a date (and so out of the post-cutoff stratum): a file that only ever appears as the target of a rename, a module that matches several upstream files, a file added by a root commit (a squashed
import carries the date of the import, not of the work). A theorem added later to an old file keeps the file's old date: that
only loses candidates, it never lets an old theorem pass as new.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SLUG = re.compile(r"[^a-z0-9]")


def corpus_of(sources: dict, library: str) -> dict | None:
    """the corpora entry of a library: its key is the library name in lower case (punctuation ignored); None when there is none (its modules then have no date)"""
    want = SLUG.sub("", library.lower())
    found = [v for k, v in sources.get("corpora", {}).items() if SLUG.sub("", k.lower()) == want and v.get("repo") and v.get("commit")]
    if len(found) > 1:
        raise SystemExit(f"dates: {len(found)} corpora entries for {library!r} (need exactly one)")
    return found[0] if found else None


def parse_log(text: str) -> dict[str, str]:
    """`git log -M --diff-filter=A --name-only --format=@%H%x09%aI%x09%P` -> {path: earliest date of a commit that added it}

    a commit with no parent is a root commit: what it adds has no known date, so it is left out
    """
    dates: dict[str, str] = {}
    date, root = "", False
    for line in text.splitlines():
        if line.startswith("@"):
            parts = line[1:].split("\t")
            date, root = parts[1][:10], len(parts) < 3 or not parts[2].strip()
        elif line.strip() and line.endswith(".lean"):
            if not root and (line not in dates or date < dates[line]):
                dates[line] = date
    return dates


def file_of(module: str, library: str, files: set[str]) -> str | None:
    """the upstream file of a Tengoku module: the longest path suffix of the module (under `Tengoku.LIB.`) that exactly one upstream file ends with"""
    prefix = f"Tengoku.{library}."
    if not module.startswith(prefix):
        return None
    rest = module[len(prefix) :].split(".")
    for i in range(len(rest)):
        tail = "/".join(rest[i:]) + ".lean"
        hits = [f for f in files if f == tail or f.endswith("/" + tail)]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            return None
    return None


def module_dates(modules: list[str], library: str, log_text: str, all_files: set[str]) -> dict[str, str]:
    added = parse_log(log_text)
    out: dict[str, str] = {}
    for m in modules:
        f = file_of(m, library, all_files)
        if f is not None and f in added:
            out[m] = added[f]
    return out


def git(*args: str, cwd: Path | None = None) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    if r.returncode:
        raise SystemExit(f"dates: git {' '.join(args[:2])} failed: {r.stderr.strip()[-300:]}")
    return r.stdout


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sources", required=True)
    ap.add_argument("--library", required=True)
    ap.add_argument("--modules", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workdir", default=".dates-work")
    a = ap.parse_args(argv)
    corpus = corpus_of(json.loads(Path(a.sources).read_text(encoding="utf-8")), a.library)
    if corpus is None:
        Path(a.out).write_text("", encoding="utf-8")
        print(json.dumps({"library": a.library, "dated": 0, "note": "no corpora entry with a repo and a commit: no dates"}, sort_keys=True))
        return 0
    work = Path(a.workdir) / a.library
    if not (work / ".git").exists():
        work.parent.mkdir(parents=True, exist_ok=True)
        git("clone", "-q", "--filter=blob:none", "--no-checkout", corpus["repo"], str(work))
    commit = corpus["commit"]
    log = git("log", commit, "-M", "--diff-filter=A", "--name-only", "--format=@%H%x09%aI%x09%P", cwd=work)
    files = {f for f in git("ls-tree", "-r", "--name-only", commit, cwd=work).splitlines() if f.endswith(".lean")}
    modules = [m for m in Path(a.modules).read_text(encoding="utf-8").splitlines() if m.strip()]
    out = module_dates(modules, a.library, log, files)
    Path(a.out).write_text("".join(f"{m}\t{d}\n" for m, d in sorted(out.items())), encoding="utf-8")
    print(
        json.dumps(
            {
                "library": a.library,
                "modules": len(modules),
                "dated": len(out),
                "earliest": min(out.values(), default=None),
                "latest": max(out.values(), default=None),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
