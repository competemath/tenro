#!/usr/bin/env python3
"""canon_report.py - what `tengai-canon` finds in the layers of a promotion: a measurement of the canonical form (invariant I2) and of the rules the design puts on exported content (I4, I5). Standard library only.

  canon_report.py CANON.tsv [--layers LAYERS.json --layer-stats LAYER_STATS.jsonl] [--out REPORT.json]

CANON.tsv is the output of `lake exe tengai-canon --module <layer> ...`: one line `violation<TAB>rule<TAB>declaration<TAB>module` for every declaration that breaks a rule of Tengai's `conventions.toml`.
A promotion by replay carries the statements of Tengoku as they are, so this says how far the promoted content is from the canonical form (`>` and `≥`, `¬ a = b`, `Nat.succ n`), from the naming rules, and
from the rules of visibility (global instances, definitions that are not irreducible). It measures; it never fails a run. With the plan of the layers and the statistics `tengai-replay` printed for them, each layer's
violations are set against the constants it added.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

EXAMPLES = 3


def summarize(lines: list[str]) -> dict:
    """counts of the violation lines: in all, by rule (how many declarations break it), by module (layer), the number of declarations that break at least one rule, and a few examples of each rule"""
    by_rule: Counter[str] = Counter()
    by_module: Counter[str] = Counter()
    declarations: set[tuple[str, str]] = set()
    examples: dict[str, list[str]] = {}
    for ln in lines:
        p = ln.rstrip("\n").split("\t")
        if len(p) < 4 or p[0] != "violation":
            continue
        _, rule, decl, module = p[:4]
        by_rule[rule] += 1
        by_module[module] += 1
        declarations.add((module, decl))
        if len(examples.setdefault(rule, [])) < EXAMPLES:
            examples[rule].append(decl)
    return {
        "violations": sum(by_rule.values()),
        "declarations_with_a_violation": len(declarations),
        "by_rule": dict(sorted(by_rule.items())),
        "by_module": dict(sorted(by_module.items())),
        "examples": dict(sorted(examples.items())),
    }


def added_by_module(layers: dict, stats: list[dict]) -> dict[str, int]:
    """module -> constants it added (the statistics of tengai-replay come one line a layer, in the order of the plan)"""
    modules = [x["module"] for x in layers["layers"]]
    if len(modules) != len(stats):
        raise SystemExit(f"{len(modules)} layers in the plan, {len(stats)} lines of statistics")
    return {m: int(s["replay"]["added"]) for m, s in zip(modules, stats, strict=True)}


def markdown(report: dict, added: dict[str, int] | None = None) -> str:
    out = ["## the canonical form of what was promoted (tengai-canon; a measurement, not a gate)", ""]
    out.append(
        f"{report['violations']} violations of {len(report['by_rule'])} rules in {report['declarations_with_a_violation']} declarations."
    )
    if added:
        total = sum(added.values())
        out[-1] += (
            f" The layers added {total} constants: {100 * report['declarations_with_a_violation'] / max(total, 1):.1f} % of them break a rule."
        )
    out += ["", "| rule | declarations | examples |", "|---|---:|---|"]
    for rule, n in report["by_rule"].items():
        out.append(f"| `{rule}` | {n} | {', '.join(f'`{e}`' for e in report['examples'].get(rule, []))} |")
    if added:
        out += ["", "| layer | constants added | declarations breaking a rule |", "|---|---:|---:|"]
        for module, n in added.items():
            out.append(f"| {module} | {n} | {report['by_module'].get(module, 0)} |")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("canon")
    ap.add_argument("--layers")
    ap.add_argument("--layer-stats")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    report = summarize(Path(a.canon).read_text(encoding="utf-8").splitlines())
    added = None
    if a.layers and a.layer_stats:
        stats = [json.loads(ln) for ln in Path(a.layer_stats).read_text(encoding="utf-8").splitlines() if ln.strip()]
        added = added_by_module(json.loads(Path(a.layers).read_text(encoding="utf-8")), stats)
        report["constants_added"] = added
    if a.out:
        Path(a.out).write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")
    print(markdown(report, added), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
