#!/usr/bin/env python3
"""verdict.py - one soundness verdict from the checks that already exist, and the ones that must not be skipped.

  verdict.py --axiom-report AXIOMS.json [--vacuity VACUITY.txt [--ack ACK.json]] [--clean-rebuild passed|failed]
             [--probe NAME=FINDINGS.json]... [--scope-prefix Tengai. ...] [--require NAME ...] > verdict.json

It runs nothing. It reads what the checks wrote and decides, with one rule above all: **a check that did not report is a failure, not a pass.** The checks:

  axioms          Tengoku's `scripts/ci/axiom_scan.py --report`: `passed` must be true; and, in addition to what that script allows Lean's prelude, no declaration in `--scope-prefix`
                  (the code this repository owns) may rest on sorryAx, Lean.ofReduceBool, Lean.ofReduceNat or Lean.trustCompiler: a native-code or compiler-trusting proof is not a
                  kernel-checked one (invariant I1).
  vacuity         Tengoku's `tools/vacuity/vacuity.lean` output: every `VACUOUS <theorem> ...` line needs the theorem's name in the acknowledgement list (`--ack`, a JSON list).
  clean-rebuild   `passed` only when the caller says the whole tree built from nothing (no cache) with warnings as errors.
  probes          `--probe hypothesis-dropping=FILE`, `--probe counterexample=FILE`: JSON `{"findings": [...]}`; any finding fails. The probes themselves are Lean runs of the harness.

`--require` names the checks that must be present (default: axioms, vacuity, clean-rebuild, hypothesis-dropping, counterexample). The exit status is 1 when the verdict is not `passed`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BANNED = ("sorryAx", "Lean.ofReduceBool", "Lean.ofReduceNat", "Lean.trustCompiler")
DEFAULT_REQUIRED = ("axioms", "vacuity", "clean-rebuild", "hypothesis-dropping", "counterexample")


def check_axioms(report: dict, scope: tuple[str, ...]) -> dict:
    details = []
    if not report.get("passed", False):
        details += [str(f)[:200] for f in report.get("failures", [])] or ["the axiom report did not pass"]
    resting = report.get("resting_on_other_axioms", {})
    for axiom in BANNED:
        users = [u for u in resting.get(axiom, []) if any(u.startswith(p) for p in scope)]
        if users:
            details.append(f"{len(users)} declaration(s) of this repository rest on {axiom}: {sorted(users)[:5]}")
    return {"status": "fail" if details else "pass", "details": details}


def check_vacuity(text: str, acks: set[str]) -> dict:
    vacuous = [ln.split()[1] for ln in text.splitlines() if ln.startswith("VACUOUS ") and len(ln.split()) > 1]
    loose = [n for n in vacuous if n not in acks]
    return {"status": "fail" if loose else "pass", "details": [f"{n}: hypotheses that can never all hold, not acknowledged" for n in loose]}


def check_findings(doc: dict) -> dict:
    findings = doc.get("findings")
    if not isinstance(findings, list):
        return {"status": "fail", "details": ['the file has no "findings" list']}
    return {"status": "fail" if findings else "pass", "details": [str(f)[:200] for f in findings[:50]]}


def decide(checks: dict[str, dict], required: tuple[str, ...]) -> dict:
    """The verdict: every required check is present and passes; a missing one is reported as `missing` and fails the whole."""
    out = dict(checks)
    for name in required:
        out.setdefault(name, {"status": "missing", "details": ["no report: a check that did not run is not a pass"]})
    return {
        "passed": all(c["status"] == "pass" for n, c in out.items() if n in required) and all(c["status"] != "fail" for c in out.values()),
        "checks": out,
    }


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--axiom-report", type=Path)
    ap.add_argument("--vacuity", type=Path)
    ap.add_argument("--ack", type=Path)
    ap.add_argument("--clean-rebuild", choices=("passed", "failed"))
    ap.add_argument("--probe", action="append", default=[], metavar="NAME=FILE")
    ap.add_argument("--scope-prefix", action="append", default=["Tengai.", "Tenro."])
    ap.add_argument("--require", nargs="*", default=list(DEFAULT_REQUIRED))
    a = ap.parse_args(argv)
    checks: dict[str, dict] = {}
    if a.axiom_report:
        checks["axioms"] = check_axioms(read_json(a.axiom_report), tuple(a.scope_prefix))
    if a.vacuity:
        acks = set(read_json(a.ack)) if a.ack else set()
        checks["vacuity"] = check_vacuity(a.vacuity.read_text(encoding="utf-8"), acks)
    if a.clean_rebuild:
        ok = a.clean_rebuild == "passed"
        checks["clean-rebuild"] = {"status": "pass" if ok else "fail", "details": [] if ok else ["the clean rebuild failed"]}
    for spec in a.probe:
        name, _, file = spec.partition("=")
        checks[name] = check_findings(read_json(Path(file)))
    verdict = decide(checks, tuple(a.require))
    print(json.dumps(verdict, indent=1, sort_keys=True))
    return 0 if verdict["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
