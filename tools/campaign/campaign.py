#!/usr/bin/env python3
"""campaign.py - register a campaign before it runs, and read its result once, after every problem of both arms is complete (eval/protocol.md sections 2-4). Standard library only.

  campaign.py split-hash IDS.txt            sha256 of the held-out id list (one id per line; sorted and de-duplicated first): the `split` of every run record and of the registration
  campaign.py register SPEC.json [--out DIR]  the registration is complete and consistent; DIR/campaign.json is what readiness gate 5 reads. Exit 1 with the problems otherwise
  campaign.py analyse SPEC.json RUNS.jsonl    the paired result of the baseline arm against the hypothesis arm: b, c, n, psi, D, the exact McNemar p-value, the primary verdict

Nothing here runs a prover (the owner's runs write RUNS.jsonl, tools/harness/records.py). A SPEC is:

  {"id": "...", "protocol": sha256 of eval/protocol.md, "split": sha256 of the id list, "n": number of held-out problems,
   "strata": ["post-cutoff", "dependency-ablation", "cross-domain"], "psi": discordant fraction the size was chosen for (0.20 until a pilot measures it),
   "baseline": "arm name", "hypothesis": "arm name",
   "arms": {name: {"model", "turn_cap", "sample_budget"}},                       identical in every arm (gate 5)
   "primary": {"kind": "superiority", "expected_gain": 0.05} or {"kind": "noninferiority", "margin": 0.05}}

Decisions, fixed here and not in a campaign:
  - a problem is SOLVED in an arm if any attempt of that arm solved it (records.py already refuses a `solved` that failed a check), UNSOLVED if an attempt ran and none solved it, and has NO RESULT
    if every attempt was an infra_error. A problem with no result in either arm is dropped and counted; more than 1% dropped makes the campaign `invalid` (gate 4's error rate).
  - the result is read once: unless exactly `n` problems have a result in both arms the verdict is `incomplete` and no number is computed (no peeking, no stopping rule).
  - a campaign whose `n` is below what its registered claim needs (eval/power.py, at `psi`) is `underpowered`: it may be read to learn and can never promote.
  - superiority: D > 0 and the two-sided exact McNemar p < 0.05. Non-inferiority: the one-sided test of D > -margin at 0.05 with the normal approximation eval/power.py uses (variance (psi - D^2) / n).
  - `promotable_on_primary_alone` says nothing about the other axes: net Pareto improvement (protocol section 2) also needs the secondary axes, which this tool does not read.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eval"))
sys.path.insert(0, str(ROOT / "tools" / "harness"))
sys.path.insert(0, str(ROOT / "tools" / "common"))
import power  # noqa: E402
import records  # noqa: E402
from util import read_jsonl  # noqa: E402

REQUIRED_STRATA = ("post-cutoff", "dependency-ablation", "cross-domain")
ARM_KEYS = ("model", "turn_cap", "sample_budget")
MAX_DROPPED = 0.01
ALPHA = 0.05


def split_hash(ids: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted({i.strip() for i in ids if i.strip()})).encode()).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def needed_n(spec: dict) -> int | None:
    """the problems the registered claim needs at the registered `psi`, None if the claim is not well formed"""
    p, psi = spec.get("primary", {}), spec.get("psi")
    if not isinstance(psi, int | float) or not 0 < psi <= 1:
        return None
    if p.get("kind") == "superiority" and isinstance(p.get("expected_gain"), int | float) and 0 < p["expected_gain"] < psi:
        return power.n_superiority(p["expected_gain"], psi)
    if p.get("kind") == "noninferiority" and isinstance(p.get("margin"), int | float) and p["margin"] > 0:
        return power.n_noninferiority(p["margin"], psi)
    return None


def check_spec(spec: dict, protocol_hash: str | None = None) -> list[str]:
    p = []
    for k in ("id", "baseline", "hypothesis"):
        if not isinstance(spec.get(k), str) or not spec[k]:
            p.append(f"{k} must be a non-empty string")
    for k in ("protocol", "split"):
        s = spec.get(k)
        if not isinstance(s, str) or len(s) != 64 or any(c not in "0123456789abcdef" for c in s):
            p.append(f"{k} must be a sha256 (64 lower-case hex)")
    if protocol_hash and spec.get("protocol") != protocol_hash:
        p.append("protocol is not the hash of this repository's eval/protocol.md: a change to the protocol makes the registration stale")
    if not isinstance(spec.get("n"), int) or isinstance(spec.get("n"), bool) or spec["n"] <= 0:
        p.append("n must be a positive integer")
    missing = [s for s in REQUIRED_STRATA if s not in set(spec.get("strata", []))]
    if missing:
        p.append(f"strata must cover {REQUIRED_STRATA}; missing {missing}")
    arms = spec.get("arms", {})
    if not isinstance(arms, dict) or len(arms) < 2:
        p.append("arms needs at least two arms")
        arms = {}
    for name in (spec.get("baseline"), spec.get("hypothesis")):
        if name and name not in arms:
            p.append(f"arm {name!r} is not in arms")
    if spec.get("baseline") and spec.get("baseline") == spec.get("hypothesis"):
        p.append("baseline and hypothesis must be different arms")
    shapes = []
    for name, a in arms.items():
        if not isinstance(a, dict) or any(a.get(k) in (None, "") for k in ARM_KEYS):
            p.append(f"arm {name!r} needs {ARM_KEYS}")
        else:
            shapes.append({k: a[k] for k in ARM_KEYS})
    if shapes and any(s != shapes[0] for s in shapes):
        p.append("every arm must have the same model, turn_cap and sample_budget (gate 5)")
    need = needed_n(spec)
    if need is None:
        p.append(
            'primary needs {"kind": "superiority", "expected_gain": g < psi} or {"kind": "noninferiority", "margin": m > 0}, and psi in (0, 1]'
        )
    return p


def power_status(spec: dict) -> dict:
    need = needed_n(spec)
    return {"needed_n": need, "n": spec.get("n"), "underpowered": need is None or not isinstance(spec.get("n"), int) or spec["n"] < need}


def readiness_input(spec: dict) -> dict:
    """what tools/readiness/report.py reads as campaign.json (gate 5)"""
    return {"arms": {n: {k: a.get(k) for k in ARM_KEYS} for n, a in spec["arms"].items()}, "strata": sorted(set(spec["strata"]))}


def outcomes(runs: list[dict], spec: dict) -> dict[str, dict[str, str]]:
    """arm -> task -> solved | unsolved | no_result, over the runs of this campaign's model and split only"""
    res: dict[str, dict[str, str]] = {spec["baseline"]: {}, spec["hypothesis"]: {}}
    for r in runs:
        arm, task = r["arm"]["name"], r["task"]["id"]
        if arm not in res or r["key"]["split"] != spec["split"] or r["key"]["model"] != spec["arms"][arm]["model"]:
            continue
        cur = res[arm].get(task, "no_result")
        new = {"solved": "solved", "unsolved": "unsolved", "infra_error": "no_result"}[r["outcome"]]
        res[arm][task] = "solved" if "solved" in (cur, new) else "unsolved" if "unsolved" in (cur, new) else "no_result"
    return res


def one_sided_noninferior_p(b: int, c: int, n: int, margin: float) -> float:
    """p of H0: D <= -margin against D > -margin, normal approximation with variance (psi - D^2) / n"""
    d, psi = (b - c) / n, (b + c) / n
    se = math.sqrt(max(psi - d * d, 0.0) / n)
    z = (d + margin) / se if se > 0 else (math.inf if d > -margin else -math.inf)
    return 1 - 0.5 * (1 + math.erf(z / math.sqrt(2)))


def analyse(spec: dict, runs: list[dict]) -> dict:
    problems = check_spec(spec) + records.validate(runs)
    if problems:
        return {"verdict": "invalid-input", "problems": problems}
    res = outcomes(runs, spec)
    base, hyp = res[spec["baseline"]], res[spec["hypothesis"]]
    tasks = set(base) | set(hyp)
    determinate = {t for t in tasks if base.get(t, "no_result") != "no_result" and hyp.get(t, "no_result") != "no_result"}
    dropped = len(tasks) - len(determinate)
    out = {"n_registered": spec["n"], "n_paired": len(determinate), "dropped": dropped, **power_status(spec)}
    if tasks and dropped / len(tasks) > MAX_DROPPED:
        return {
            **out,
            "verdict": "invalid",
            "reason": f"{dropped} of {len(tasks)} problems have no result in an arm (more than {MAX_DROPPED:.0%}): the harness, not the systems, is being measured",
        }
    if len(determinate) != spec["n"]:
        return {
            **out,
            "verdict": "incomplete",
            "reason": f"{len(determinate)} problems have a result in both arms, {spec['n']} were registered: the result is read once, when all are complete",
        }
    b = sum(1 for t in determinate if hyp[t] == "solved" and base[t] == "unsolved")
    c = sum(1 for t in determinate if base[t] == "solved" and hyp[t] == "unsolved")
    n = spec["n"]
    out |= {"b": b, "c": c, "psi": (b + c) / n, "D": (b - c) / n, "mcnemar_p": power.mcnemar_exact(b, c)}
    prim = spec["primary"]
    if prim["kind"] == "superiority":
        ok = out["D"] > 0 and out["mcnemar_p"] < ALPHA
        out["verdict"] = "superior" if ok else "not-demonstrated"
    else:
        out["noninferiority_p"] = one_sided_noninferior_p(b, c, n, prim["margin"])
        out["verdict"] = "non-inferior" if out["noninferiority_p"] < ALPHA else "not-demonstrated"
    out["promotable_on_primary_alone"] = out["verdict"] in ("superior", "non-inferior") and not out["underpowered"]
    return out


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) == 2 and argv[0] == "split-hash":
        print(split_hash(Path(argv[1]).read_text(encoding="utf-8").splitlines()))
        return 0
    if len(argv) >= 2 and argv[0] == "register":
        spec = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        problems = check_spec(spec, sha256_file(ROOT / "eval" / "protocol.md"))
        for x in problems:
            print(x)
        if problems:
            return 1
        st = power_status(spec)
        print(
            f"campaign {spec['id']}: registered; n = {st['n']}, the claim needs {st['needed_n']}"
            + (" (UNDERPOWERED: may be read to learn, never to decide)" if st["underpowered"] else "")
        )
        if len(argv) == 4 and argv[2] == "--out":
            out = Path(argv[3])
            out.mkdir(parents=True, exist_ok=True)
            (out / "campaign.json").write_text(json.dumps(readiness_input(spec), indent=1, sort_keys=True) + "\n", encoding="utf-8")
        return 0
    if len(argv) == 3 and argv[0] == "analyse":
        spec = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        res = analyse(spec, read_jsonl(Path(argv[2])))
        print(json.dumps(res, indent=1, sort_keys=True))
        return 0 if res["verdict"] in ("superior", "non-inferior", "not-demonstrated") else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
