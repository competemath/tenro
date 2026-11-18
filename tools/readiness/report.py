#!/usr/bin/env python3
"""report.py - the five readiness gates as one report (the brief, section 5; design P6). Standard library only.

  report.py INPUTS.json [--markdown]

No A/B campaign against Mathlib is launched until all five gates pass. This reads the measurements the other tools wrote (they are gathered into one INPUTS.json) and decides every criterion
as pass, fail or **unmeasured**; a gate passes only when every one of its criteria passes, so a criterion nobody has measured keeps its gate closed. The exit status is 0 only when all five pass.

INPUTS.json (every key optional):
  soundness        tools/soundness/verdict.py output ({"passed": bool, "checks": {...}})
  data             {"lemmas", "definitions", "structural_duplicates", "statements"}               the library's `data/`
  load, scale      tools/perf/perf_profile.py `load` / `scale` output; budget: perf-budget.toml as a dict; mathlib_load_net_median_s: context only
  retrieval        {"recall_at_10", "n"}                  blind signature recall on held-out goals with target names stripped
  obfuscation      {"pass_rate_plain", "pass_rate_scrambled", "n"}
  migration        tools/lens/lens.py `check` report ({"denominator", "accepted", "rate", "rejected"}) and migration_integrity_violations: int
  migration_corpus [{"library", "old", "survival", "fidelity"}, ...]   tools/lens/reseed.py classify, one per real re-cut (docs/migration-corpus/)
  tamper           {"cases", "undetected"}                                   frozen-prefix / `#print axioms` tamper tests
  harness          {"runs", "infra_errors"}; validity: {"tasks", "two_sided_valid"}
  campaign         {"arms": {name: {"model", "turn_cap", "sample_budget"}}, "strata": [...]}

Gate 1's load criterion is the ABSOLUTE cap of perf-budget.toml (approved design fix 1), not the brief's 5x ratio to Mathlib, which a small library meets trivially; the ratio is printed as context.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REQUIRED_STRATA = ("post-cutoff", "dependency-ablation", "cross-domain")


def crit(name: str, threshold: str, value, ok: bool | None, note: str = "") -> dict:
    status = "unmeasured" if ok is None else ("pass" if ok else "fail")
    return {"criterion": name, "threshold": threshold, "value": value, "status": status, "note": note}


def get(d: dict, *path):
    for p in path:
        if not isinstance(d, dict) or p not in d:
            return None
        d = d[p]
    return d


def gate1(i: dict) -> list[dict]:
    out = []
    passed = get(i, "soundness", "passed")
    out.append(crit("axiom, vacuity, rebuild and probe locks", "verdict passed", passed, None if passed is None else bool(passed)))
    data = i.get("data")
    if data and data.get("definitions"):
        ratio = data["lemmas"] / data["definitions"]
        out.append(crit("lemma-to-definition ratio in data/", "<= 4", round(ratio, 3), ratio <= 4))
    else:
        out.append(crit("lemma-to-definition ratio in data/", "<= 4", None, None))
    dup = get(i, "data", "structural_duplicates")
    out.append(crit("structural duplicates in data/", "0", dup, None if dup is None else dup == 0))
    load, scale, budget = i.get("load"), i.get("scale"), i.get("budget")
    if load and scale and budget:
        ok = load["net_median_s"] <= budget["load"]["cap_net_median_s"] and scale["ms_per_module"] <= budget["scale"]["cap_ms_per_module"]
        note = ""
        if i.get("mathlib_load_net_median_s") and load["net_median_s"] > 0:
            note = (
                f"context: Mathlib import is {i['mathlib_load_net_median_s'] / load['net_median_s']:.1f}x this library's (not a criterion)"
            )
        out.append(
            crit(
                "cold import and cost per module within the absolute caps",
                "perf-budget.toml",
                [load["net_median_s"], scale["ms_per_module"]],
                ok,
                note,
            )
        )
    else:
        out.append(crit("cold import and cost per module within the absolute caps", "perf-budget.toml", None, None))
    return out


def gate2(i: dict) -> list[dict]:
    r, o = i.get("retrieval"), i.get("obfuscation")
    out = [
        crit(
            "blind signature Recall@10 on held-out goals",
            ">= 0.85",
            r and r.get("recall_at_10"),
            None if not r else r["recall_at_10"] >= 0.85,
            f"n={r['n']}" if r else "",
        )
    ]
    if o:
        drop = o["pass_rate_plain"] - o["pass_rate_scrambled"]
        out.append(crit("pass-rate drop when identifiers are scrambled", "< 0.05", round(drop, 4), drop < 0.05, f"n={o['n']}"))
    else:
        out.append(crit("pass-rate drop when identifiers are scrambled", "< 0.05", None, None))
    return out


def gate3(i: dict) -> list[dict]:
    m = i.get("migration")
    out = []
    if m and m.get("denominator"):
        out.append(
            crit(
                "automatic bidirectional lens migration pass rate",
                ">= 0.98",
                m["rate"],
                m["rate"] >= 0.98,
                f"{m['accepted']} of {m['denominator']}",
            )
        )
    else:
        out.append(crit("automatic bidirectional lens migration pass rate", ">= 0.98", None, None, "no migrations measured"))
    v = i.get("migration_integrity_violations")
    out.append(crit("isnad meaning integrity of accepted migrations", "100%", v, None if v is None else v == 0))
    corpus = i.get("migration_corpus")
    if corpus:
        worst = min(c["fidelity"] for c in corpus)
        per = "; ".join(f"{c['library']}: survival {c['survival']:.2%}, fidelity {c['fidelity']:.2%} of {c['old']}" for c in corpus)
        out.append(
            crit(
                "fidelity of the survivors of real re-cuts (the gate's 98% read as fidelity, with survival reported beside it)",
                ">= 0.98",
                worst,
                worst >= 0.98,
                per + " (docs/migration-corpus.md: this reading is the owner's to accept)",
            )
        )
    else:
        out.append(
            crit(
                "fidelity of the survivors of real re-cuts (the gate's 98% read as fidelity, with survival reported beside it)",
                ">= 0.98",
                None,
                None,
                "no re-cut classified",
            )
        )
    return out


def gate4(i: dict) -> list[dict]:
    t, h, v = i.get("tamper"), i.get("harness"), i.get("validity")
    out = []
    if t and t.get("cases"):
        out.append(
            crit(
                "undetected statement/definition tampering",
                "0",
                t["undetected"],
                t["undetected"] == 0,
                f"of {t['cases']} cases (the checker's own mutation corpus unless real harness runs are added)",
            )
        )
    else:
        out.append(crit("undetected statement/definition tampering", "0", None, None, "no tamper cases run"))
    if h and h.get("runs"):
        rate = h["infra_errors"] / h["runs"]
        out.append(crit("harness infrastructure error rate", "< 0.01", round(rate, 4), rate < 0.01, f"{h['infra_errors']} of {h['runs']}"))
    else:
        out.append(crit("harness infrastructure error rate", "< 0.01", None, None))
    if v and v.get("tasks"):
        out.append(
            crit(
                "two-sided validity across eval tasks", "100%", v["two_sided_valid"], v["two_sided_valid"] == v["tasks"], f"of {v['tasks']}"
            )
        )
    else:
        out.append(crit("two-sided validity across eval tasks", "100%", None, None))
    return out


def gate5(i: dict) -> list[dict]:
    c = i.get("campaign")
    if not c:
        return [
            crit("strata cover post-cutoff, dependency-ablation and cross-domain", "all three", None, None),
            crit("identical model, turn cap and sample budget in every arm", "equal", None, None),
        ]
    strata = set(c.get("strata", []))
    arms = list(c.get("arms", {}).values())
    same = (
        len(arms) >= 2
        and all(
            {k: a.get(k) for k in ("model", "turn_cap", "sample_budget")}
            == {k: arms[0].get(k) for k in ("model", "turn_cap", "sample_budget")}
            for a in arms
        )
        and all(arms[0].get(k) is not None for k in ("model", "turn_cap", "sample_budget"))
    )
    return [
        crit("strata cover post-cutoff, dependency-ablation and cross-domain", "all three", sorted(strata), set(REQUIRED_STRATA) <= strata),
        crit("identical model, turn cap and sample budget in every arm", "equal", {k: v for k, v in c.get("arms", {}).items()}, same),
    ]


GATES = (
    ("1", "Library soundness and hygiene", gate1),
    ("2", "Zero-shot discoverability and retrieval parity", gate2),
    ("3", "Migration and isnad round-trip fidelity", gate3),
    ("4", "Anti-tampering and harness calibration", gate4),
    ("5", "Stratified eval and compute parity", gate5),
)


def report(inputs: dict) -> dict:
    gates = []
    for num, title, fn in GATES:
        criteria = fn(inputs)
        status = (
            "pass" if all(c["status"] == "pass" for c in criteria) else ("fail" if any(c["status"] == "fail" for c in criteria) else "open")
        )
        gates.append({"gate": num, "title": title, "status": status, "criteria": criteria})
    return {"all_pass": all(g["status"] == "pass" for g in gates), "ab_allowed": all(g["status"] == "pass" for g in gates), "gates": gates}


# where the measurement of a criterion comes from (matched on the criterion's name): what a person has to produce for an unmeasured one
SOURCES = (
    ("axiom, vacuity", "verdict.json: tools/soundness/verdict.py, fed by Tengoku's axiom_scan and vacuity checks, a clean rebuild, and the two probes (Probes.lean)"),
    ("lemma-to-definition", "data-stats.json: tools/readiness/data_stats.py over a library's `data/` (no `data/` in Tengai yet)"),
    ("structural duplicates", "data-stats.json: the same, from the isnad ids"),
    ("cold import", "load.json and scale.json: tools/perf/perf_profile.py (readiness.yml measures them)"),
    ("Recall@10", "retrieval.json: an owner's eval run on the held-out set (tenro-eval)"),
    ("scrambled", "obfuscation.json: an owner's eval run, identifiers scrambled by tools/scramble"),
    ("pass rate", "lens-report.json: tools/lens/lens.py check on a migration with isnad ids from built trees"),
    ("isnad meaning integrity", "lens-report.json with `integrity_violations`: the isnad round trip on built trees"),
    ("fidelity of the survivors", "migration-corpus/*.json: tools/lens/reseed.py classify on two manifests of a re-cut (docs/migration-corpus/)"),
    ("tampering", "tamper.json: tools/harness/tamper.py (selftest in readiness.yml; real runs are the owner's)"),
    ("infrastructure error", "harness.json: an owner's eval run"),
    ("two-sided validity", "validity.json: an owner's eval run"),
    ("strata", "campaign.json: the registered campaign"),
    ("identical model", "campaign.json: the registered campaign"),
)  # fmt: skip


def source_of(criterion: str) -> str:
    return next((s for key, s in SOURCES if key in criterion), "")


def markdown(rep: dict) -> str:
    out = [f"# Readiness: A/B against Mathlib is {'ALLOWED' if rep['ab_allowed'] else 'NOT allowed'}", ""]
    for g in rep["gates"]:
        out += [f"## Gate {g['gate']}: {g['title']} — {g['status'].upper()}", ""]
        for c in g["criteria"]:
            out.append(
                f"- [{c['status']}] {c['criterion']} (threshold {c['threshold']}; value {c['value']}){' — ' + c['note'] if c['note'] else ''}"
            )
        out.append("")
    missing = [(g["gate"], c["criterion"]) for g in rep["gates"] for c in g["criteria"] if c["status"] == "unmeasured"]
    if missing:
        out += ["## Not measured yet, and where it comes from", ""]
        out += [f"- gate {n}: {name} <- {source_of(name) or 'no source named'}" for n, name in missing]
        out.append("")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(__doc__)
        return 2
    rep = report(json.loads(Path(argv[0]).read_text(encoding="utf-8")))
    print(markdown(rep) if "--markdown" in argv else json.dumps(rep, indent=1))
    return 0 if rep["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
