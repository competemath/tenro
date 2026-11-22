#!/usr/bin/env python3
"""licences.py - the licence texts and notices of the libraries a snapshot is made from, fetched at the commit each one was taken from. Standard library only (`gh` for the network).

  licences.py ATTRIBUTION.json --out LEGAL_DIR

ATTRIBUTION.json is `attribution.py`'s report (per library: the repository, the commit and the licence the registry records). MIT and Apache-2.0 ask for the licence text and the copyright notices to travel with
copies of the work, and a snapshot is a copy of statements taken from those libraries, so the snapshot carries them. For every (repository, commit) this reads the root of the repository AT THAT COMMIT and keeps
every file named like a licence or a notice (LICENSE, LICENSE.md, LICENCE, COPYING, NOTICE, LICENSE-MIT, ...), exactly as the repository holds it, in two GraphQL rounds of up to 40 repositories each (the REST API of
`GITHUB_TOKEN` allows 1,000 calls an hour; this needs a few).

Writes, in LEGAL_DIR:
  ATTRIBUTION.md                         where the content comes from (the table of notes.py, not tied to a release tag)
  LICENSES/<owner>/<repo>@<commit>/<file>  the files, byte for byte (the commit is the first 12 characters)
  LICENSES/INDEX.json                    per library: its sources and their files (size and sha256), what the registry says the licence is, and `problems`

`problems` lists every source for which the texts cannot be stood behind: **no licence file at the root** at that commit, or **none of the files reads as the licence the registry records** (a crude reading of the
text: the Apache-2.0 text, the MIT permission notice, the BSD 3-Clause conditions: a registry that says MIT over a GPL text is caught, a text this does not recognise is a problem too, never a guess). The exit
status is 0 whatever the problems are: they are in INDEX.json and in the manifest, and the release gate (notes.py) refuses a snapshot that has any.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import notes  # noqa: E402

REPO = re.compile(r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
# a root file that holds a licence or a notice; the charset is also what keeps a name out of the query as text
LICENCE_FILE = re.compile(r"^(?=[A-Za-z0-9._-]+$)(licen[cs]e|copying|notice|unlicense)([-_.].*)?$", re.IGNORECASE)
MAX_FILES_PER_SOURCE = 8
BATCH = 40


def classify(text: str) -> set[str]:
    """which licences a text reads as: a crude reading of the standard texts, enough to catch a registry that names another licence"""
    t = " ".join(text.split()).lower()
    found: set[str] = set()
    if "apache license" in t and "version 2.0" in t:
        found.add("Apache-2.0")
    if "permission is hereby granted, free of charge" in t and "the above copyright notice and this permission notice" in t:
        found.add("MIT")
    if "redistribution and use in source and binary forms" in t and "neither the name" in t:
        found.add("BSD-3-Clause")
    return found


def sources_of(att: dict) -> dict[tuple[str, str], dict]:
    """every (repository, commit) of the attribution, with the libraries that come from it and the licence the registry records"""
    out: dict[tuple[str, str], dict] = {}
    for key, lib in sorted(att["libraries"].items()):
        for s in lib["sources"]:
            if not REPO.match(s["repo"]) or not COMMIT.match(s["commit"]):
                raise SystemExit(f"licences: {key}: {s['repo']!r} at {s['commit']!r} is not a GitHub repository at a full commit")
            e = out.setdefault((s["repo"], s["commit"]), {"libraries": [], "licence": s["licence"]})
            e["libraries"].append(key)
            if e["licence"] != s["licence"]:
                raise SystemExit(
                    f"licences: {s['repo']} at {s['commit'][:12]} is recorded under two licences ({e['licence']}, {s['licence']})"
                )
    return out


class GitHub:
    """the two GraphQL rounds, through `gh api graphql` (a failed call is tried again, a few seconds later each time)"""

    def __init__(self, runner=None, sleep=time.sleep) -> None:
        self.runner = runner or self._gh
        self.sleep = sleep

    @staticmethod
    def _gh(query: str) -> str:
        r = subprocess.run(["gh", "api", "graphql", "-f", f"query={query}"], capture_output=True, text=True, timeout=180)
        # `gh` exits 1 when the answer has errors but still prints the answer: a repository that is gone is an error beside the others' data
        if r.returncode != 0 and not r.stdout.strip():
            raise RuntimeError(r.stderr.strip()[:300])
        return r.stdout

    def call(self, query: str) -> dict:
        err = ""
        for wait in (0, 5, 20, 60):
            self.sleep(wait)
            try:
                reply = json.loads(self.runner(query))
            except (RuntimeError, ValueError, subprocess.TimeoutExpired) as e:
                err = str(e)
                continue
            # a repository or a commit that is not found is an answer (None); any other error (rate limit, timeout, a malformed query) is tried again
            other = [e for e in reply.get("errors") or [] if e.get("type") != "NOT_FOUND"]
            if reply.get("data") is None or other:
                err = str(reply.get("errors"))[:300]
                continue
            return reply["data"]
        raise SystemExit(f"licences: the GitHub API did not answer: {err}")

    @staticmethod
    def _repo(alias: str, repo: str, body: str) -> str:
        owner, name = REPO.match(repo).groups()  # type: ignore[union-attr]
        return f'{alias}: repository(owner: "{owner}", name: "{name}") {{ {body} }}'

    def root_files(self, pairs: list[tuple[str, str]]) -> dict[tuple[str, str], list[str] | None]:
        """the names of the files at the root of each repository at its commit (None: the repository or the commit was not found)"""
        out: dict[tuple[str, str], list[str] | None] = {}
        for i in range(0, len(pairs), BATCH):
            chunk = pairs[i : i + BATCH]
            q = (
                "query { "
                + " ".join(
                    self._repo(f"r{j}", repo, f'object(expression: "{commit}:") {{ ... on Tree {{ entries {{ name type }} }} }}')
                    for j, (repo, commit) in enumerate(chunk)
                )
                + " }"
            )
            data = self.call(q)
            for j, pair in enumerate(chunk):
                obj = ((data.get(f"r{j}") or {}).get("object")) or None
                out[pair] = None if obj is None else [e["name"] for e in obj.get("entries", []) if e.get("type") == "blob"]
        return out

    def read(self, wanted: list[tuple[str, str, str]]) -> dict[tuple[str, str, str], bytes | None]:
        """the text of each (repository, commit, file) (None: not text, or truncated, or not found)"""
        out: dict[tuple[str, str, str], bytes | None] = {}
        for i in range(0, len(wanted), BATCH):
            chunk = wanted[i : i + BATCH]
            q = (
                "query { "
                + " ".join(
                    self._repo(f"b{j}", repo, f'object(expression: "{commit}:{name}") {{ ... on Blob {{ text isBinary isTruncated }} }}')
                    for j, (repo, commit, name) in enumerate(chunk)
                )
                + " }"
            )
            data = self.call(q)
            for j, key in enumerate(chunk):
                obj = ((data.get(f"b{j}") or {}).get("object")) or {}
                ok = obj.get("text") is not None and not obj.get("isBinary") and not obj.get("isTruncated")
                out[key] = obj["text"].encode("utf-8") if ok else None
        return out


def fetch(att: dict, hub) -> dict[tuple[str, str], dict[str, bytes]]:
    """every licence-like file at the root of each source, by (repository, commit) and file name"""
    pairs = sorted(sources_of(att))
    listing = hub.root_files(pairs)
    wanted: list[tuple[str, str, str]] = []
    for pair in pairs:
        names = sorted(n for n in (listing.get(pair) or []) if LICENCE_FILE.match(n))[:MAX_FILES_PER_SOURCE]
        wanted += [(pair[0], pair[1], n) for n in names]
    texts = hub.read(wanted) if wanted else {}
    # None: the repository or the commit was not found (not the same as a repository with no licence file)
    found: dict[tuple[str, str], dict[str, bytes] | None] = {pair: (None if listing.get(pair) is None else {}) for pair in pairs}
    for (repo, commit, name), data in texts.items():
        if data is not None:
            found[(repo, commit)][name] = data  # type: ignore[index]
    return found  # type: ignore[return-value]


def problems_of(att: dict, found: dict[tuple[str, str], dict[str, bytes]]) -> list[dict]:
    out: list[dict] = []
    for (repo, commit), e in sources_of(att).items():
        files = found.get((repo, commit))
        where = {"repo": repo, "commit": commit, "libraries": e["libraries"], "registry_licence": e["licence"]}
        if files is None:
            out.append({**where, "problem": "the repository or the commit was not found"})
        elif not files:
            out.append({**where, "problem": "no licence file at the root of the repository at this commit"})
        elif not any(e["licence"] in classify(data.decode("utf-8", "replace")) for data in files.values()):
            out.append(
                {
                    **where,
                    "problem": "no file reads as the licence the registry records",
                    "reads_as": sorted({c for d in files.values() for c in classify(d.decode("utf-8", "replace"))}),
                }
            )
    return out


def write(out: Path, att: dict, found: dict[tuple[str, str], dict[str, bytes]]) -> dict:
    """the files, the attribution and INDEX.json; returns INDEX.json's content"""
    base = out / "LICENSES"
    index_sources: dict[tuple[str, str], list[dict]] = {}
    for (repo, commit), files in sorted(found.items()):
        owner, name = REPO.match(repo).groups()  # type: ignore[union-attr]
        folder = base / owner / f"{name}@{commit[:12]}"
        recs = []
        for fname, data in sorted((files or {}).items()):
            folder.mkdir(parents=True, exist_ok=True)
            (folder / fname).write_bytes(data)
            recs.append({"file": f"{owner}/{name}@{commit[:12]}/{fname}", "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        index_sources[(repo, commit)] = recs
    libraries = {
        key: {
            "licence": lib["sources"][0]["licence"] if lib["sources"] else None,
            "sources": [
                {"repo": s["repo"], "commit": s["commit"], "files": index_sources.get((s["repo"], s["commit"]), [])} for s in lib["sources"]
            ],
        }
        for key, lib in sorted(att["libraries"].items())
    }
    problems = problems_of(att, found)
    index = {"libraries": libraries, "sources": len(found), "files": sum(len(v) for v in index_sources.values()), "problems": problems}
    base.mkdir(parents=True, exist_ok=True)
    (base / "INDEX.json").write_text(json.dumps(index, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "ATTRIBUTION.md").write_text(notes.attribution_md(att, None), encoding="utf-8")
    return index


def main(argv: list[str] | None = None, hub=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("attribution", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)
    att = json.loads(a.attribution.read_text(encoding="utf-8"))
    if att.get("unknown"):
        print(f"licences: libraries without a repository, a commit or a licence in the registry: {att['unknown'][:10]}", file=sys.stderr)
    found = fetch(att, hub or GitHub())
    index = write(a.out, att, found)
    print(
        f"licences: {index['sources']} sources, {index['files']} licence and notice files kept, {len(index['problems'])} sources without a text that stands behind the registry's licence"
        + "".join(
            f"\n  {p['repo']} at {p['commit'][:12]}: {p['problem']}" + (f" (reads as {p['reads_as']})" if p.get("reads_as") else "")
            for p in index["problems"][:30]
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
