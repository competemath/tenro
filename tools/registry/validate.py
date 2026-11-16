#!/usr/bin/env python3
"""validate.py - the hypothesis registry and the harvest quarantine (Tengai docs/design.md, invariants I6, I7, I8). Standard library only; run from the repository root.

  validate.py hyp [--base-ref REF]                  every hyp/<id>/manifest.json is complete, consistent with core.lock, eval/protocol.md and its patch; with --base-ref, a manifest
                                                    that already existed there did not change except its `status` (a hypothesis is registered BEFORE it runs: I7)
  validate.py harvest [--heldout FILE]              every harvest record comes from a NON-evaluation intake run and from no held-out problem (I8); FILE lists the held-out problem
                                                    ids, one a line (ids only: the text of a held-out problem never reaches this repository). Records and no FILE is an error:
                                                    an unchecked harvest is not a clean one.

hyp/<id>/manifest.json: id (= the directory), title, change, metric, expected_effect, direction (improve | non-inferior), sample_size (> 0), margin (>= 0, the non-inferiority margin),
protocol_sha256 (sha256 of eval/protocol.md: the file must exist, so no hypothesis exists before the protocol does), core_patch_sha256 (sha256 of hyp/<id>/core.patch, or null for an
overlay-only hypothesis), mirror_hash (core.lock's tree), registered (YYYY-MM-DD), status (registered | running | rejected | promoted).
harvest/records/*.jsonl, a line: statement_id (an isnad id), problem_id, run_id, run_kind (must be "intake"), kernel_checked (must be true), intake_commit (40 hex).
harvest/quarantine.jsonl, a line: problem_id, run_id, reason: ids and a reason, never a statement, a proof or any text of the problem.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ID_RE = re.compile(r"[a-z0-9]{1,8}\.\d+h\d+v\.s\d+\.[0-9a-f]{12}")
HYP_ID = re.compile(r"[a-z0-9][a-z0-9-]{2,39}")
HEX64 = re.compile(r"[0-9a-f]{64}")
HEX40 = re.compile(r"[0-9a-f]{40}")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
STATUSES = ("registered", "running", "rejected", "promoted")
FIELDS = (
    "id", "title", "change", "metric", "expected_effect", "direction", "sample_size", "margin",
    "protocol_sha256", "core_patch_sha256", "mirror_hash", "registered", "status",
)  # fmt: skip
FROZEN = tuple(f for f in FIELDS if f != "status")  # fixed at registration
QUARANTINE_KEYS = {"problem_id", "run_id", "reason"}
RECORD_KEYS = {"statement_id", "problem_id", "run_id", "run_kind", "kernel_checked", "intake_commit"}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_manifest(m: dict, dirname: str, root: Path) -> list[str]:
    p = []
    missing = [f for f in FIELDS if f not in m]
    if missing:
        return [f"hyp/{dirname}: missing {missing}"]
    if extra := sorted(set(m) - set(FIELDS)):
        p.append(f"hyp/{dirname}: unknown fields {extra}")
    if m["id"] != dirname or not HYP_ID.fullmatch(str(m["id"])):
        p.append(f"hyp/{dirname}: id {m['id']!r} must be the directory name, lower case words joined by dashes")
    for f in ("title", "change", "metric", "expected_effect"):
        if not isinstance(m[f], str) or not m[f].strip():
            p.append(f"hyp/{dirname}: {f} must be a non-empty text")
    if m["direction"] not in ("improve", "non-inferior"):
        p.append(f"hyp/{dirname}: direction must be improve or non-inferior")
    if not isinstance(m["sample_size"], int) or isinstance(m["sample_size"], bool) or m["sample_size"] <= 0:
        p.append(f"hyp/{dirname}: sample_size must be a positive integer")
    if not isinstance(m["margin"], int | float) or isinstance(m["margin"], bool) or m["margin"] < 0:
        p.append(f"hyp/{dirname}: margin must be a number >= 0")
    if not DATE.fullmatch(str(m["registered"])):
        p.append(f"hyp/{dirname}: registered must be YYYY-MM-DD")
    if m["status"] not in STATUSES:
        p.append(f"hyp/{dirname}: status must be one of {STATUSES}")
    protocol = root / "eval" / "protocol.md"
    if not protocol.is_file():
        p.append(f"hyp/{dirname}: eval/protocol.md does not exist: no hypothesis can be registered before the protocol (I7)")
    elif m["protocol_sha256"] != sha256_file(protocol):
        p.append(f"hyp/{dirname}: protocol_sha256 is not the hash of eval/protocol.md as it is now")
    patch = root / "hyp" / dirname / "core.patch"
    if m["core_patch_sha256"] is None:
        if patch.is_file():
            p.append(f"hyp/{dirname}: core.patch exists and core_patch_sha256 is null")
    elif not patch.is_file() or m["core_patch_sha256"] != sha256_file(patch):
        p.append(f"hyp/{dirname}: core_patch_sha256 is not the hash of hyp/{dirname}/core.patch")
    lock = root / "core.lock"
    if lock.is_file() and m["mirror_hash"] != json.loads(lock.read_text(encoding="utf-8")).get("tree"):
        p.append(f"hyp/{dirname}: mirror_hash is not core.lock's tree")
    return p


def check_frozen(new: dict, old: dict, dirname: str) -> list[str]:
    return [f"hyp/{dirname}: {f} was changed after registration (only status may change)" for f in FROZEN if new.get(f) != old.get(f)]


def base_manifest(ref: str, dirname: str) -> dict | None:
    r = subprocess.run(["git", "show", f"{ref}:hyp/{dirname}/manifest.json"], capture_output=True, text=True, check=False)
    return json.loads(r.stdout) if r.returncode == 0 else None


def check_hyp(root: Path, base_ref: str | None = None) -> list[str]:
    problems: list[str] = []
    for d in sorted(p for p in (root / "hyp").iterdir() if p.is_dir()) if (root / "hyp").is_dir() else []:
        mf = d / "manifest.json"
        if not mf.is_file():
            problems.append(f"hyp/{d.name}: no manifest.json")
            continue
        try:
            m = json.loads(mf.read_text(encoding="utf-8"))
        except ValueError:
            problems.append(f"hyp/{d.name}: manifest.json is not JSON")
            continue
        problems += check_manifest(m, d.name, root)
        old = base_manifest(base_ref, d.name) if base_ref else None
        if old is not None:
            problems += check_frozen(m, old, d.name)
    return problems


def read_lines(path: Path) -> list[tuple[int, dict | None]]:
    out = []
    for i, ln in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if ln.strip():
            try:
                out.append((i, json.loads(ln)))
            except ValueError:
                out.append((i, None))
    return out


def check_record(rec: dict, heldout: set[str]) -> list[str]:
    p = []
    if set(rec) != RECORD_KEYS:
        return [f"keys must be exactly {sorted(RECORD_KEYS)}"]
    if rec["run_kind"] != "intake":
        p.append(f"run_kind is {rec['run_kind']!r}: only non-evaluation intake runs are harvested (I8)")
    if rec["kernel_checked"] is not True:
        p.append("kernel_checked is not true")
    if rec["problem_id"] in heldout:
        p.append(f"problem {rec['problem_id']} is held out (I8)")
    if not ID_RE.fullmatch(str(rec["statement_id"])):
        p.append("statement_id is not an isnad id")
    if not HEX40.fullmatch(str(rec["intake_commit"])):
        p.append("intake_commit is not a 40 hex commit")
    return p


def check_harvest(root: Path, heldout: set[str] | None) -> list[str]:
    problems: list[str] = []
    files = sorted((root / "harvest" / "records").glob("*.jsonl")) if (root / "harvest" / "records").is_dir() else []
    seen: set[tuple] = set()
    n = 0
    for f in files:
        for i, rec in read_lines(f):
            n += 1
            where = f"harvest/records/{f.name}:{i}"
            if rec is None or not isinstance(rec, dict):
                problems.append(f"{where}: not a JSON object")
                continue
            problems += [f"{where}: {x}" for x in check_record(rec, heldout or set())]
            key = (rec.get("statement_id"), rec.get("problem_id"), rec.get("run_id"))
            if key in seen:
                problems.append(f"{where}: duplicate record {key}")
            seen.add(key)
    if n and heldout is None:
        problems.append(f"{n} harvest record(s) and no held-out list to check them against: an unchecked harvest is not a clean one")
    q = root / "harvest" / "quarantine.jsonl"
    for i, rec in read_lines(q) if q.is_file() else []:
        if not isinstance(rec, dict) or set(rec) != QUARANTINE_KEYS:
            problems.append(
                f"harvest/quarantine.jsonl:{i}: keys must be exactly {sorted(QUARANTINE_KEYS)} (ids and a reason, never text of a problem)"
            )
    return problems


def main(argv: list[str]) -> int:
    root = Path(".")
    if not argv or argv[0] not in ("hyp", "harvest"):
        print(__doc__)
        return 2
    opts = dict(zip(argv[1::2], argv[2::2], strict=False))
    if argv[0] == "hyp":
        problems = check_hyp(root, opts.get("--base-ref"))
    else:
        heldout = None
        if "--heldout" in opts:
            heldout = {ln.strip() for ln in Path(opts["--heldout"]).read_text(encoding="utf-8").splitlines() if ln.strip()}
        problems = check_harvest(root, heldout)
    for x in problems:
        print(x)
    print(f"{argv[0]}: {len(problems)} problem(s)" if problems else f"{argv[0]}: ok")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
