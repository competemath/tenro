#!/usr/bin/env python3
"""records.py - the run records of the eval harness and the numbers gates 4 and 5 read from them. Standard library only.

  records.py validate RUNS.jsonl                      every line is a complete, consistent run record
  records.py summarise RUNS.jsonl --out DIR           DIR/harness.json ({"runs", "infra_errors"}) and DIR/validity.json ({"tasks", "two_sided_valid"}) for tools/readiness/gather.py

A RUN is one attempt of one system on one problem (eval/protocol.md): the harness writes one JSON line per run, and only the owner's runs write them. Fields:
  key       core_tree (40 hex), hypothesis (id or "baseline"), harness (sha256 of the harness spec), model, seed (int), split (sha256 of the held-out split's id list)
  task      the problem id (an id, never the problem text), stratum (post-cutoff | dependency-ablation | cross-domain | other)
  arm       the system the run belongs to (e.g. tengai, mathlib, baseline, a hypothesis id), turn_cap, sample_budget
  outcome   solved | unsolved | infra_error     (infra_error: the harness or the runner failed, not the prover; such a run says nothing about the system)
  checks    {"tamper": pass|fail, "kernel": pass|fail|n/a, "axioms": pass|fail|n/a}   a solved run needs all three pass; a tamper `fail` makes the outcome `unsolved`
  validity  the two-sided check of the TASK, written once per task by the harness, not per run: {"accepts_reference": bool, "rejects_mutant": bool}: the task's reference proof is accepted AND a
            known-wrong submission is rejected (a task that cannot tell right from wrong is invalid in one direction and does not count).
Parity (gate 5): all arms of one comparison share model, turn_cap and sample_budget; `summarise` reports differences instead of hiding them.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")
OUTCOMES = ("solved", "unsolved", "infra_error")
STRATA = ("post-cutoff", "dependency-ablation", "cross-domain", "other")
KEY = ("core_tree", "hypothesis", "harness", "model", "seed", "split")


def check_run(r: dict) -> list[str]:
    p = []
    key, task, arm = r.get("key", {}), r.get("task", {}), r.get("arm", {})
    if set(key) != set(KEY):
        p.append(f"key must have exactly {KEY}")
    else:
        if not HEX40.fullmatch(str(key["core_tree"])):
            p.append("key.core_tree is not a 40 hex tree id")
        if not HEX64.fullmatch(str(key["harness"])) or not HEX64.fullmatch(str(key["split"])):
            p.append("key.harness and key.split must be sha256 hex")
        if not isinstance(key["seed"], int) or isinstance(key["seed"], bool):
            p.append("key.seed must be an integer")
        if not key["model"] or not key["hypothesis"]:
            p.append("key.model and key.hypothesis must be non-empty")
    if not task.get("id") or task.get("stratum") not in STRATA:
        p.append(f"task needs an id and a stratum from {STRATA}")
    if not arm.get("name") or not isinstance(arm.get("turn_cap"), int) or not isinstance(arm.get("sample_budget"), int):
        p.append("arm needs a name, an integer turn_cap and an integer sample_budget")
    outcome, checks = r.get("outcome"), r.get("checks", {})
    if outcome not in OUTCOMES:
        p.append(f"outcome must be one of {OUTCOMES}")
    if outcome == "solved" and not (checks.get("tamper") == "pass" and checks.get("kernel") == "pass" and checks.get("axioms") == "pass"):
        p.append("a solved run needs the tamper, kernel and axioms checks to pass")
    if checks.get("tamper") == "fail" and outcome == "solved":
        p.append("a run that failed the tamper check is not solved")
    return p


def validate(runs: list[dict]) -> list[str]:
    problems = []
    seen = set()
    for i, r in enumerate(runs, 1):
        problems += [f"run {i}: {x}" for x in check_run(r)]
        k = (json.dumps(r.get("key"), sort_keys=True), r.get("task", {}).get("id"), r.get("arm", {}).get("name"))
        if k in seen:
            problems.append(f"run {i}: the same key, task and arm appear twice")
        seen.add(k)
    return problems


def summarise(runs: list[dict], validity: list[dict] | None = None) -> dict:
    """harness: runs and infra errors; validity: tasks and the ones valid in both directions; parity: the arms that differ in model, turn cap or sample budget"""
    infra = sum(1 for r in runs if r["outcome"] == "infra_error")
    tasks = {r["task"]["id"] for r in runs}
    v = {x["task"]: x for x in (validity or [])}
    two_sided = sum(1 for t in tasks if t in v and v[t].get("accepts_reference") is True and v[t].get("rejects_mutant") is True)
    arms: dict[str, dict] = {}
    for r in runs:
        arms.setdefault(
            r["arm"]["name"], {"model": r["key"]["model"], "turn_cap": r["arm"]["turn_cap"], "sample_budget": r["arm"]["sample_budget"]}
        )
    first = next(iter(arms.values()), None)
    differing = sorted(n for n, a in arms.items() if first is not None and a != first)
    return {
        "harness": {"runs": len(runs), "infra_errors": infra},
        "validity": {"tasks": len(tasks), "two_sided_valid": two_sided},
        "parity": {"arms": arms, "differing_from_the_first": differing},
    }


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) >= 2 and argv[0] == "validate":
        problems = validate(read_jsonl(Path(argv[1])))
        for x in problems:
            print(x)
        print(f"records: {len(problems)} problem(s)" if problems else "records: ok")
        return 1 if problems else 0
    if len(argv) >= 4 and argv[0] == "summarise" and argv[2] == "--out":
        runs = read_jsonl(Path(argv[1]))
        validity = (
            read_jsonl(Path(argv[1]).with_name("task-validity.jsonl")) if Path(argv[1]).with_name("task-validity.jsonl").is_file() else []
        )
        s = summarise(runs, validity)
        out = Path(argv[3])
        out.mkdir(parents=True, exist_ok=True)
        (out / "harness.json").write_text(json.dumps(s["harness"], indent=1) + "\n", encoding="utf-8")
        (out / "validity.json").write_text(json.dumps(s["validity"], indent=1) + "\n", encoding="utf-8")
        print(json.dumps(s, indent=1, sort_keys=True))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
