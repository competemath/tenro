#!/usr/bin/env python3
"""attribution.py - where the content of a snapshot comes from, and under which licence. Standard library only.

  attribution.py --intake TENGOKU/data/intake --sources TENGOKU/schemas/sources.json [--sample SAMPLE.jsonl] --out attribution.json

A snapshot holds statements that Tengoku took from other people's libraries. Each record of Tengoku's intake carries the URL of its source file at a commit (`source_url`, a GitHub blob URL), and Tengoku's registry
(`schemas/sources.json`) holds the licence of each repository: this joins the two, per library, so that what a snapshot is made of can be named: the repository, the commit, the licence. A library whose repository the
registry has no licence for is listed as `unknown` and is not guessed. With `--sample` only the libraries the sample names (its `library` field) are listed.

Writes `{"libraries": {key: {"sources": [{"repo", "commit", "licence"}], "records": n}}, "licences": {licence: number of libraries}, "unknown": [libraries without a licence]}`; the manifest of a snapshot records it.

  attribution.py --filter ATTRIBUTION.json --exclude-report TREE-ROOTS.json --out ATTRIBUTION.json

A whole-tree export that leaves libraries out (`exclude_libraries`, tools/promote/tree_roots.py) holds none of their content, so the attribution must not name them: a library the snapshot does not hold, whose repository has no
licence text at the pinned commit, would block a release for nothing, and a notice for content that is not there is a false statement. The report of the roots says which roots were left out; a root `Tengoku.LanaBelyi` is
the registry library `lana-belyi` (the names are compared with everything but letters and digits dropped and the case folded). A root that matches two libraries is an error (what was left out could not be told apart from
what was kept); a root that matches none is reported, not an error (it is already gone, or it is not a library of the registry). The counts of libraries per licence and the list of unknown ones are made again.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

BLOB = re.compile(r"^(https://github\.com/[^/]+/[^/]+)/blob/([0-9a-f]{40})/")


def licence_of(repo: str, licences: dict[str, str]) -> str | None:
    if repo in licences:
        return licences[repo]
    lower = repo.lower()
    for k, v in licences.items():  # GitHub names are not case sensitive
        if k.lower() == lower:
            return v
    return None


def library_sources(manifest: Path) -> tuple[dict[tuple[str, str], int], int]:
    """the (repository, commit) pairs the records of one manifest name, with how many records each, and the number of records"""
    pairs: Counter[tuple[str, str]] = Counter()
    n = 0
    with open(manifest, encoding="utf-8") as f:
        for ln in f:
            if not ln.strip():
                continue
            n += 1
            m = BLOB.match(str(json.loads(ln).get("source_url", "")))
            if m:
                pairs[(m.group(1), m.group(2))] += 1
    return dict(pairs), n


def build(intake: Path, licences: dict[str, str], only: set[str] | None = None) -> dict:
    libraries: dict[str, dict] = {}
    unknown: list[str] = []
    for d in sorted(p for p in intake.iterdir() if p.is_dir()):
        manifest = d / "manifest.jsonl"
        if not manifest.is_file() or (only is not None and d.name not in only):
            continue
        pairs, n = library_sources(manifest)
        sources = [{"repo": repo, "commit": commit, "licence": licence_of(repo, licences)} for (repo, commit) in sorted(pairs)]
        libraries[d.name] = {"sources": sources, "records": n}
        if not sources or any(s["licence"] is None for s in sources):
            unknown.append(d.name)
    counts: Counter[str] = Counter()
    for key, lib in libraries.items():
        for lic in sorted({s["licence"] for s in lib["sources"] if s["licence"] is not None}):
            counts[lic] += 1
    return {"libraries": libraries, "licences": dict(sorted(counts.items())), "unknown": unknown}


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def drop_excluded(att: dict, report: dict) -> tuple[dict, list[str], list[str]]:
    """the attribution without the libraries the report of the roots says were left out; returns it, the libraries dropped and the roots that matched no library"""
    libs = att["libraries"]
    by: dict[str, list[str]] = {}
    for key in libs:
        by.setdefault(norm(key), []).append(key)
    gone: list[str] = []
    unmatched: list[str] = []
    for e in report.get("excluded", []):
        root = e["root"]
        hit = by.get(norm(root.split(".", 1)[-1]), [])
        if len(hit) > 1:
            raise SystemExit(
                f"attribution: the library left out, {root}, matches {len(hit)} libraries of the registry ({', '.join(hit)}): what it no longer holds cannot be told from what was kept"
            )
        if hit:
            gone.append(hit[0])
        else:
            unmatched.append(root)
    kept = {k: v for k, v in libs.items() if k not in gone}
    counts: Counter[str] = Counter()
    for lib in kept.values():
        for lic in sorted({s["licence"] for s in lib["sources"] if s["licence"] is not None}):
            counts[lic] += 1
    return (
        {"libraries": kept, "licences": dict(sorted(counts.items())), "unknown": [u for u in att["unknown"] if u in kept]},
        sorted(gone),
        unmatched,
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--intake", type=Path)
    ap.add_argument("--sources", type=Path)
    ap.add_argument("--sample", type=Path)
    ap.add_argument(
        "--filter", type=Path, help="an attribution.json to leave libraries out of (with --exclude-report), instead of making one"
    )
    ap.add_argument("--exclude-report", type=Path, help="tree-roots.json of tools/promote/tree_roots.py: the roots that were left out")
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)
    if a.filter is not None:
        if a.exclude_report is None:
            ap.error("--filter needs --exclude-report")
        att, gone, unmatched = drop_excluded(
            json.loads(a.filter.read_text(encoding="utf-8")), json.loads(a.exclude_report.read_text(encoding="utf-8"))
        )
        a.out.write_text(json.dumps(att, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(
            f"attribution: {len(gone)} libraries left out ({', '.join(gone)}), {len(att['libraries'])} remain; licences {att['licences']}"
            + (f"; {len(unmatched)} roots matched no library (already gone, or not in the registry): {unmatched}" if unmatched else "")
        )
        return 0
    if a.intake is None or a.sources is None:
        ap.error("--intake and --sources are needed to make the attribution")
    licences = json.loads(a.sources.read_text(encoding="utf-8")).get("licences", {})
    only = None
    if a.sample:
        only = set()
        with open(a.sample, encoding="utf-8") as f:
            for ln in f:
                if ln.strip():
                    only.add(json.loads(ln)["library"])
    report = build(a.intake, licences, only)
    a.out.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"attribution: {len(report['libraries'])} libraries; licences {report['licences']}; "
        + (f"UNKNOWN for {len(report['unknown'])}: {report['unknown'][:8]}" if report["unknown"] else "every library has a licence")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
