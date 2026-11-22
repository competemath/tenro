#!/usr/bin/env python3
"""use.py - which layers of an unpacked snapshot a problem needs, and the header that imports them. Standard library only.

  use.py SNAPSHOT_DIR --theorem NAME [--theorem NAME ...] [--topic LIBRARY ...] [--header FILE]
  use.py SNAPSHOT_DIR --list-topics

SNAPSHOT_DIR is what `pack.py verify --into DIR` unpacked: `manifest.json`, `TengaiData/**.olean` and `indexes/layers.jsonl` (the layer that holds each theorem's statement). A layer imports the layers
above it (the foundation, its group), so importing the layer of a theorem is enough: a session loads that layer and what it imports, not the rest. This prints, for what was asked, the `import` lines (one per layer,
sorted) and the `LEAN_PATH` entry that makes them resolve; `--header FILE` writes the import lines to a file that a problem can be appended to. A theorem the index does not know is an error that names the closest names;
a layer whose `.olean` is not in the directory is an error too (`pack.py verify` is what says the files are the manifest's).
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path


def load(snapshot: Path) -> tuple[dict, dict[str, dict]]:
    manifest_path = snapshot / "manifest.json"
    if not manifest_path.is_file():
        raise SystemExit(f"use: {manifest_path} is not there: SNAPSHOT_DIR is what `pack.py verify --into DIR` unpacked")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    layers = {x["module"]: x for x in manifest.get("layers", [])}
    if not layers:
        raise SystemExit("use: the manifest lists no layer")
    return manifest, layers


def olean_of(module: str) -> str:
    return "/".join(module.split(".")) + ".olean"


def theorem_layers(snapshot: Path, names: list[str]) -> dict[str, str]:
    """the layer of each theorem name, from indexes/layers.jsonl; an unknown name is an error that names the closest ones"""
    index = snapshot / "indexes" / "layers.jsonl"
    if not index.is_file():
        raise SystemExit(f"use: {index} is not there (a snapshot packed without the layers index cannot say which layer holds a theorem)")
    wanted = set(names)
    found: dict[str, str] = {}
    known: list[str] = []
    with open(index, encoding="utf-8") as f:
        for ln in f:
            if not ln.strip():
                continue
            row = json.loads(ln)
            if row["name"] in wanted:
                found[row["name"]] = row["layer"]
            elif len(wanted) > len(found):
                known.append(row["name"])  # only kept while something is still missing: the names to suggest from
    missing = [n for n in names if n not in found]
    if missing:
        hints = {n: difflib.get_close_matches(n, known, n=3, cutoff=0.6) for n in missing}
        raise SystemExit(
            "use: not in the layers index: " + "; ".join(f"{n!r}" + (f" (closest: {', '.join(h)})" if h else "") for n, h in hints.items())
        )
    return found


def topic_layers(layers: dict[str, dict], topics: list[str]) -> dict[str, str]:
    by_topic = {x["topic"]: m for m, x in layers.items() if x.get("topic")}
    by_suffix = {m.rsplit(".", 1)[-1].lower(): m for m, x in layers.items() if x.get("topic")}
    out: dict[str, str] = {}
    for t in topics:
        module = by_topic.get(t) or by_suffix.get(t.lower().replace("-", "").replace("_", "")) or by_suffix.get(t.lower())
        if module is None:
            close = difflib.get_close_matches(t, sorted(by_topic), n=3, cutoff=0.5)
            raise SystemExit(f"use: no topic {t!r}" + (f" (closest: {', '.join(close)})" if close else ""))
        out[t] = module
    return out


def plan(snapshot: Path, theorems: list[str], topics: list[str]) -> dict:
    manifest, layers = load(snapshot)
    modules: dict[str, list[str]] = {}
    if theorems:
        for name, module in theorem_layers(snapshot, theorems).items():
            modules.setdefault(module, []).append(name)
    if topics:
        for t, module in topic_layers(layers, topics).items():
            modules.setdefault(module, []).append(f"topic {t}")
    for module in modules:
        if module not in layers:
            raise SystemExit(f"use: the index puts a theorem in {module}, which the manifest does not list")
        if not (snapshot / olean_of(module)).is_file():
            raise SystemExit(f"use: {olean_of(module)} is not in {snapshot} (the snapshot is not unpacked whole)")
    # what an import loads: the layer and everything it imports, the manifest's own `imports`
    loaded: set[str] = set()
    stack = list(modules)
    while stack:
        m = stack.pop()
        if m not in loaded:
            loaded.add(m)
            stack += layers[m]["imports"]
    return {
        "imports": sorted(modules),
        "because": {m: sorted(v) for m, v in sorted(modules.items())},
        "loads": sorted(loaded),
        "constants_loaded": sum(layers[m]["constants"] for m in loaded),
        "lean_path": str(snapshot.resolve()),
        "pins": manifest.get("pins", {}),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("snapshot", type=Path)
    ap.add_argument("--theorem", action="append", default=[], help="a theorem name; its layer is imported")
    ap.add_argument("--topic", action="append", default=[], help="a topic (library) name; its layer is imported")
    ap.add_argument("--list-topics", action="store_true")
    ap.add_argument("--header", type=Path, help="write the import lines to this file")
    a = ap.parse_args(argv)
    if a.list_topics:
        _, layers = load(a.snapshot)
        for module, x in sorted(layers.items()):
            print(f"{x.get('topic') or '-':40} {module}  ({x['constants']:,} constants)")
        return 0
    if not a.theorem and not a.topic:
        ap.error("ask for a --theorem or a --topic (or --list-topics)")
    p = plan(a.snapshot, a.theorem, a.topic)
    header = "".join(f"import {m}\n" for m in p["imports"])
    if a.header:
        a.header.write_text(header, encoding="utf-8")
    print(header, end="")
    print(f"-- {len(p['loads'])} layers, {p['constants_loaded']:,} constants loaded: {', '.join(p['loads'])}")
    print(f'-- LEAN_PATH="{p["lean_path"]}:$(lake env printenv LEAN_PATH)" lake env lean problem.lean')
    return 0


if __name__ == "__main__":
    sys.exit(main())
