#!/usr/bin/env python3
"""notes.py - the release notes and the attribution file of a statements snapshot, and the gates a release must pass. Standard library only.

  notes.py MANIFEST.json --tag TAG --run RUN_ID --archive-bytes N --archive-sha256 H --out-notes NOTES.md --out-attribution ATTRIBUTION.md

Reads the manifest of a snapshot (`manifest.py layers --flavor statements`, packed by `pack.py`) and writes what a release says about it: what it is, what it holds, the pins it was made from, what was checked (and what was
not), and where its content comes from. **A snapshot is not released** (exit status 1, nothing written) unless: its flavor is `statements` (this tool states what a statements snapshot is and is not); its kernel check
accepted every layer; the comparison with Tengoku's environment ran and found no problem (`checks.faithful.ok`); and every library has a repository, a commit and a licence (`attribution.unknown` is empty). There is no
option to release without them.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

TAG = re.compile(r"^snapshot-[A-Za-z0-9._-]{1,60}$")


def gates(m: dict) -> list[str]:
    """why this manifest may not be released: the empty list when it may"""
    problems: list[str] = []
    if m.get("flavor") != "statements":
        problems.append(f"the flavor is {m.get('flavor')!r}, not 'statements'")
    checks = m.get("checks") or {}
    if checks.get("kernel") != "accepted":
        problems.append("the kernel check did not accept every layer")
    faithful = checks.get("faithful")
    if faithful is None:
        problems.append("the comparison with Tengoku's environment did not run")
    elif not faithful.get("ok"):
        problems.append(f"the comparison with Tengoku's environment found problems: {faithful.get('problems')}")
    ext = checks.get("extensions")
    if ext is not None and not ext.get("ok"):
        problems.append(f"Lean refused {ext.get('failed')} extension entries the snapshot was to carry")
    legal = m.get("legal")
    if legal is None:
        problems.append(
            "the snapshot carries no licence texts (legal/): MIT and Apache-2.0 want the licence and the notices to travel with copies"
        )
    elif legal.get("problems") is None or legal["problems"]:
        problems.append(
            f"{legal.get('problems') if legal.get('problems') is not None else 'an unknown number of'} sources without a licence text that stands behind the registry's licence (legal/LICENSES/INDEX.json says which)"
        )
    nanoda = checks.get("nanoda")
    if nanoda is not None and nanoda.get("status") != "ok":
        problems.append(f"the independent kernel (nanoda) did not accept the layers: {nanoda.get('status')!r}")
    attribution = m.get("attribution")
    if attribution is None:
        problems.append("the manifest has no attribution")
    elif attribution.get("unknown"):
        problems.append(f"libraries without a repository, a commit or a licence: {attribution['unknown'][:10]}")
    return problems


def attribution_md(att: dict, tag: str | None) -> str:
    rows = []
    for key, lib in sorted(att["libraries"].items()):
        for s in lib["sources"]:
            rows.append(
                f"| {key} | [{s['repo'].removeprefix('https://github.com/')}]({s['repo']}) | `{s['commit'][:12]}` | {s['licence']} | {lib['records']:,} |"
            )
    licences = ", ".join(f"{k}: {v}" for k, v in sorted(att["licences"].items()))
    return (
        (f"# Where the content of `{tag}` comes from\n\n" if tag else "# Where the content of this snapshot comes from\n\n")
        + "The statements and definitions in this snapshot are taken, through [Tengoku](https://github.com/competemath/tengoku), from the libraries below, each at the commit shown. "
        "Each library is under the licence shown; the licence and the notices of the library apply to its content, and the credit is the library's authors'. "
        "The tools of Tenro and Tengai that built the snapshot are Apache-2.0.\n\n"
        f"Libraries per licence: {licences}.\n\n"
        "| library | repository | commit | licence | records |\n|---|---|---|---|---:|\n" + "\n".join(rows) + "\n"
    )


def notes_md(m: dict, tag: str, run: str, archive_bytes: int, archive_sha256: str) -> str:
    t, checks, pins = m["totals"], m["checks"], m["pins"]
    layers = m["layers"]
    load = (checks.get("session_load") or {}).get("sets") or {}
    singles = {k: v for k, v in load.items() if not k.startswith("Combo_") and "net_median" in v}
    worst = max(singles.items(), key=lambda kv: kv[1]["net_median"]) if singles else None
    cap = (checks.get("session_load") or {}).get("cap")
    f = checks["faithful"]
    att = m["attribution"]
    ext = checks.get("extensions")
    carries = (
        "It carries the constants and, from Tengoku, the extension entries Lean keeps about them "
        f"({ext['instances']:,} instances, {ext['classes']:,} classes, {ext['structures']:,} structures, {ext['projections']:,} projection functions, {ext['reducibility']:,} reducibility attributes; `tengai-replay --ext`), "
        "and no simp sets, notation, macros or tactics."
        if ext
        else "It carries constants only, no instances, simp sets, notation or tactics."
    )
    lines = [
        f"# {tag}: Tengoku's statements as a layered snapshot (experimental)",
        "",
        f"**What it is.** {t['theorems']:,} theorem statements of {len(m['libraries'])} libraries, as a foundation and one layer per library of built `.olean` files "
        f"({t['olean_bytes'] / 1e9:.2f} GB; {archive_bytes / 1e6:,.0f} MB as the archive below). A theorem stands as an **axiom of its type**: its proof is not in it, except the proofs a definition computes through. "
        "It is a base for search and for applying statements, not a proof library: a result found in it must be checked in an environment that has the real proofs (invariant I1, untrusted search and trusted checking). "
        + carries
        + " It is Tengoku **at the pin** named below, and it is **experimental**: no version promise, no stability, not a v1.",
        "",
        "**What was checked.**",
        f"- the kernel accepted every declaration of every layer ({t.get('refused', 0)} refused of {t['constants_added']:,} constants added);",
        f"- **faithful to Tengoku**: {f['compared']:,} constants compared by `tengai-typeinfo --hashes` against Tengoku's environment (the hash and the size of the type, the hash of the value): "
        f"{f['statement_stubs']:,} theorems stand as axioms of their type, {f['kept_with_value']:,} are kept with their proof, {f['same_with_value'] + f['same_without_value']:,} definitions and other declarations agree, "
        f"{f['refused_and_stubbed']:,} were stubbed after a refusal; problems: {f['problems'] or 'none'}. The hash is Lean's 32 bits: a difference is certain, an agreement makes one very unlikely and is not a proof;",
    ]
    nanoda = checks.get("nanoda")
    if nanoda:
        lines.append(
            f"- **an independent kernel** (nanoda, which shares no code with Lean) accepted the layers read back out of their `.olean` files and exported again: {nanoda['declarations']:,} declarations. "
            "A theorem stands as an axiom of its type there, so what it checks is every other declaration (the definitions, the inductive types, Lean core's) given those statements;"
        )
    if ext:
        lines.append(
            f"- extension entries put back in {ext['layers']} layers: {ext['instances']:,} instances, {ext['classes']:,} classes, {ext['structures']:,} structures, {ext['projections']:,} projection functions, "
            f"{ext['reducibility']:,} reducibility attributes; refused by Lean: {ext['failed']};"
        )
    if worst and cap:
        lines.append(
            f"- every session (the foundation and one library) over an empty module, paired medians: the slowest is {worst[0]} at +{worst[1]['net_median']:.3f} s; the cap is {cap} s;"
        )
    lines += [
        "",
        "**What was not checked.** "
        + ("" if nanoda else "An independent kernel over the layers; ")
        + "a prover or a Leak environment on it; it holds the statements the libraries' statements reach, not the seed's (Mathlib's) other lemmas.",
        "",
        "**Made from.** " + ", ".join(f"{k} `{v}`" for k, v in sorted(pins.items())) + f" (workflow run {run}).",
        "",
        "**Use.**",
        "```bash",
        "sha256sum -c SHA256SUMS                        # the archive and the manifest",
        "python3 tools/release/pack.py verify snapshot.tar.zst --sha256 <the archive's> --into snapshot   # tenro's tools/release/pack.py",
        'LEAN_PATH="snapshot:$(lake env printenv LEAN_PATH)" lake env lean problem.lean   # import TengaiData.Topic.<Library>',
        "```",
        "`indexes/layers.jsonl` in the archive says which layer holds each theorem. docs/consuming.md of Tenro says the rest.",
        "",
        f"**Where the content comes from.** {len(att['libraries'])} libraries, each at a commit and under a licence ({', '.join(f'{k}: {v}' for k, v in sorted(att['licences'].items()))}): see `ATTRIBUTION.md`. "
        f"Each library's licence text and notices, as its repository holds them at that commit ({m['legal']['licence_files']:,} files of {m['legal']['sources']:,} repositories), are in the archive under `legal/LICENSES/`, and they apply to its content.",
        "",
        f"Layers: {len(layers)}. Archive sha256 `{archive_sha256}`.",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("manifest", type=Path)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--run", required=True)
    ap.add_argument("--archive-bytes", required=True, type=int)
    ap.add_argument("--archive-sha256", required=True)
    ap.add_argument("--out-notes", required=True, type=Path)
    ap.add_argument("--out-attribution", required=True, type=Path)
    a = ap.parse_args(argv)
    if not TAG.match(a.tag) or re.match(r"^v[1-9]", a.tag):
        print(
            f"notes: the tag {a.tag!r} must be snapshot-<name> (letters, digits, dot, dash, underscore) and not a version", file=sys.stderr
        )
        return 1
    if not re.fullmatch(r"[0-9a-f]{64}", a.archive_sha256):
        print("notes: the archive's sha256 is not 64 hex digits", file=sys.stderr)
        return 1
    m = json.loads(a.manifest.read_text(encoding="utf-8"))
    problems = gates(m)
    if problems:
        print("notes: this snapshot is NOT released:\n  - " + "\n  - ".join(problems), file=sys.stderr)
        return 1
    a.out_notes.write_text(notes_md(m, a.tag, a.run, a.archive_bytes, a.archive_sha256), encoding="utf-8")
    a.out_attribution.write_text(attribution_md(m["attribution"], a.tag), encoding="utf-8")
    print(f"notes: {a.tag}: the gates passed; notes and attribution written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
