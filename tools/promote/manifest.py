#!/usr/bin/env python3
"""manifest.py - the record of one transplant: what went in, from which pins, and what was checked. Standard library only.

  manifest.py --dir DIR --out MANIFEST.json --export EXPORT.ndjson --olean MODULE.olean [--pin KEY=VALUE ...]
  manifest.py layers --dir DIR --layered LAYERED_DIR --out MANIFEST.json [--pin KEY=VALUE ...]        schema 2: a promotion in layers (the foundation and one layer per topic)

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
    raw = read_json(d / "replay-stats.json")
    # tengai >= v0.0.10 writes {"replay": {...}, "ext": {...}|null}; before that the counters were the whole object
    stats = (raw.get("replay", raw) if raw else None) or None
    ext = raw.get("ext") if raw else None
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
        "extensions": ext,
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
            else {
                "names": ids["names"],
                "equal": ids["equal"],
                "drift": [d["name"] for d in ids.get("drift", [])],
                "no_source_id": ids.get("no_source_id", 0),
                "ok": ids["ok"],
            },
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


def layer_path(layered: Path, module: str) -> Path:
    return layered / (module.replace(".", "/") + ".olean")


def index_record(indexes: Path) -> dict:
    """the retrieval indexes of a promotion (`tools/index/build.py` and `intent.py`: the pattern shape, the static dependency graph, the names, the intent): every file with its size and sha256, and the counts the two
    builders wrote, so that the manifest says what is in them without opening them. Name-blind by construction except `names.jsonl`."""
    files = sorted(p for p in indexes.iterdir() if p.is_file())
    if not files:
        raise SystemExit(f"manifest: {indexes} holds no index file")
    rec: dict = {"files": {p.name: sha256_and_sizes(p) for p in files}}
    for key, stats in (("build", "stats.json"), ("intent", "intent-stats.json"), ("layers", "layers-stats.json")):
        data = read_json(indexes / stats)
        if data is not None:
            rec[key] = {k: v for k, v in data.items() if k != "sha256"}  # the hashes are in `files`
    return rec


def build_layers(d: Path, layered: Path, pins: dict[str, str], indexes: Path | None = None, flavor: str | None = None) -> dict:
    """the record of a promotion in layers (schema 2): every layer with what it imports, what it holds, what its replay added and the hash and size of its olean; the checks of the whole (independent kernel over all
    the layers, statement ids, axioms, what a session loads). A layer whose file is missing is an error, a check that did not run is null."""
    plan = json.loads((d / "layers" / "layers.json").read_text(encoding="utf-8"))
    sample = [json.loads(ln) for ln in (d / "sample.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
    names = [r["name"] for r in sample]
    stats_lines = (
        [json.loads(ln) for ln in (d / "layer-stats.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
        if (d / "layer-stats.jsonl").exists()
        else []
    )
    if stats_lines and len(stats_lines) != len(plan["layers"]):
        raise SystemExit(f"manifest: {len(plan['layers'])} layers planned, the replay left statistics for {len(stats_lines)}")
    layers = []
    for i, layer in enumerate(plan["layers"]):
        path = layer_path(layered, layer["module"])
        if not path.is_file():
            raise SystemExit(f"manifest: the olean of {layer['module']} is not at {path}")
        topic = layer["topic"]
        layers.append(
            {
                "module": layer["module"],
                "topic": topic,
                "imports": layer["imports"],
                "units": layer["units"],
                "constants": layer["constants"],
                "theorems": plan["topics"][topic]["theorems"] if topic else 0,
                "replay": stats_lines[i].get("replay") if stats_lines else None,
                "extensions": stats_lines[i].get("ext") if stats_lines else None,
                "olean": sha256_and_sizes(path),
            }
        )
    status = (d / "nanoda-layers.status").read_text(encoding="utf-8").strip() if (d / "nanoda-layers.status").exists() else None
    declared = (
        re.findall(r"Checked (\d+) declarations with no errors", (d / "nanoda-layers.out").read_text(encoding="utf-8"))
        if (d / "nanoda-layers.out").exists()
        else []
    )
    ids = read_json(d / "statement-ids-layers.json")
    load = read_json(d / "layers-load.json")
    faithful = read_json(d / "faithful.json")
    attribution = read_json(d / "attribution.json")
    axioms_text = (d / "layers-axioms.txt").read_text(encoding="utf-8") if (d / "layers-axioms.txt").exists() else ""
    return {
        "schema": 2,
        **({"flavor": flavor} if flavor else {}),
        # where the content comes from: per library the repository, the commit and the licence (tools/promote/attribution.py)
        **({"attribution": attribution} if attribution is not None else {}),
        **({"indexes": index_record(indexes)} if indexes is not None else {}),
        "pins": dict(sorted(pins.items())),
        "libraries": sorted({r["library"] for r in sample}),
        # a statements snapshot has hundreds of thousands of theorems: the table of which layer holds which is the layers index (tools/promote/layer_index.py), not a list in the manifest
        "theorems": [] if flavor == "statements" else sorted(sample, key=lambda r: r["name"]),
        "layers": layers,
        "totals": {
            "olean_bytes": sum(x["olean"]["bytes"] for x in layers),
            "constants_added": sum((x["replay"] or {}).get("added", 0) for x in layers) if stats_lines else None,
            "theorems": len(sample),
            # a statements snapshot: the declarations the kernel refused and that stand as axioms of their type (tengai-replay --stub-refused); None when no replay statistics were left
            **(
                {"refused": sum(len((x["replay"] or {}).get("refused") or []) for x in layers) if stats_lines else None}
                if flavor == "statements"
                else {}
            ),
        },
        "checks": {
            "kernel": "accepted" if stats_lines and all(x["replay"] for x in layers) else None,
            "nanoda": {"status": status, "declarations": int(declared[-1]) if declared else None} if status else None,
            "statement_ids": None
            if ids is None
            else {
                "names": ids["names"],
                "equal": ids["equal"],
                "drift": [x["name"] for x in ids.get("drift", [])],
                "no_source_id": ids.get("no_source_id", 0),
                "ok": ids["ok"],
            },
            "axioms": axioms_check(axioms_text, names),
            # a replay against the environment it was exported from (tengai-typeinfo --hashes, tools/promote/faithful.py): null when it did not run
            "faithful": None
            if faithful is None
            else {
                **{
                    k: faithful[k]
                    for k in (
                        "names",
                        "compared",
                        "statement_stubs",
                        "kept_with_value",
                        "same_with_value",
                        "same_without_value",
                        "refused_and_stubbed",
                        "absent_in_both",
                        "not_asked",
                    )
                },
                "problems": faithful["problem_counts"],
                "ok": faithful["passed"],
            },
            "session_load": None
            if load is None
            else {
                "baseline": load.get("empty"),
                **({"cap": load["cap"]} if "cap" in load else {}),  # the cap of perf-budget.toml the sessions were judged against
                "sets": {
                    row[0]: {
                        "olean_mb": round(row[1], 1),
                        **{k: row[2][k] for k in ("median", "net_median", "net_min", "constants") if k in row[2]},
                    }
                    for row in load["rows"]
                    if isinstance(row[2], dict)
                },
            },
        },
    }


def main_layers(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="manifest.py layers")
    ap.add_argument("--dir", required=True)
    ap.add_argument("--layered", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--pin", action="append", default=[], help="KEY=VALUE")
    ap.add_argument(
        "--indexes",
        help="the directory of the retrieval indexes (build.py and intent.py wrote it): recorded with its hashes, packed with the snapshot",
    )
    ap.add_argument(
        "--flavor",
        choices=["statements"],
        help="a snapshot of the statements flavor (docs/statements.md): recorded, and the declarations the kernel refused are counted",
    )
    a = ap.parse_args(argv)
    m = build_layers(Path(a.dir), Path(a.layered), dict(p.split("=", 1) for p in a.pin), Path(a.indexes) if a.indexes else None, a.flavor)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(json.dumps(m, indent=1, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "layers": [x["module"] for x in m["layers"]],
                "totals": m["totals"],
                "checks": {k: (v if not isinstance(v, dict) else "…") for k, v in m["checks"].items()},
            },
            sort_keys=True,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] == "layers":
        return main_layers(argv[1:])
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
