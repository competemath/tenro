#!/usr/bin/env python3
"""tree_topics.py - the topics of a layered snapshot of a whole tree, by module path. Standard library only.

  tree_topics.py MODULES.jsonl --out TOPICS.json [--sample-out SAMPLE.jsonl] [--root Tengoku] [--seed Seed] [--seed-depth 1]

MODULES.jsonl is `Modules.lean` run in the tree's environment: one line `{"m": module, "n": [components]}` for every theorem a module declares. Every theorem becomes a root of a topic, so that the layers hold
everything the theorems' statements reach (`layers.py` places only what some topic reaches), **except an internal one**: a name with a string component that starts with an underscore (`_proof_4`, `_simp_1`, `_unary`,
everything under `_private`). `lean4export` without names, the export of a whole tree, skips exactly those (`Name.isInternal`) unless a statement reaches them, and `layers.py` refuses a topic whose theorem is not in
the export; a layer places an internal theorem that a statement does reach by reachability, like any constant. The topic is read off the module path below the root of the tree:

  Tengoku.Seed.Algebra.Group.Basic     -> Seed/Algebra               (the first `--seed-depth` components below the seed: an area of the reseeded Mathlib; depth 2 is Seed/Algebra/Group)
  Tengoku.AddCombi.AddCombi.Mathlib.X  -> Intake/AddCombi            (anything else: the library, the first component below the root)
  Tengoku.Seed                         -> Seed/Misc                   (a module of the seed with no area below it)

so that the tree of `layers.py` is: the foundation, the group `Seed` with its areas, the group `Intake` with its libraries; a constant that two areas need is in the layer of the group `Seed`, one that two libraries
need in the layer of the group `Intake`, and one that a library and an area need in the foundation. `--sample-out` writes one line `{"name": theorem name, "library": its topic}` for each theorem, the file the layers index
(`layer_index.py`) and the manifest read. A name is its components joined by dots, as the export's reader writes it.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


def topic_of(module: str, root: str, seed: str, seed_depth: int) -> str:
    parts = module.split(".")
    if parts[0] != root:
        raise SystemExit(f"tree_topics: the module {module} is not below {root}")
    below = parts[1:]
    if not below:
        return "Intake/Misc"
    if below[0] == seed:
        area = below[1 : 1 + seed_depth]
        return "/".join([seed, *area]) if area else f"{seed}/Misc"
    return f"Intake/{below[0]}"


def is_internal(components) -> bool:
    """Lean's `Name.isInternal`, on the components of a name: a string component that starts with an underscore (a number never makes a name internal)"""
    return any(isinstance(c, str) and c.startswith("_") for c in components)


def build_counting(lines, root: str = "Tengoku", seed: str = "Seed", seed_depth: int = 1) -> tuple[dict[str, list[str]], int]:
    """the topics, and how many internal theorems were left out"""
    topics: dict[str, list[str]] = {}
    left_out = 0
    for ln in lines:
        if not ln.strip():
            continue
        r = json.loads(ln)
        topic = topic_of(r["m"], root, seed, seed_depth)  # a module outside the root is refused whatever the theorem
        if is_internal(r["n"]):
            left_out += 1
            continue
        topics.setdefault(topic, []).append(".".join(str(c) for c in r["n"]))
    return {t: sorted(names) for t, names in sorted(topics.items())}, left_out


def build(lines, root: str = "Tengoku", seed: str = "Seed", seed_depth: int = 1) -> dict[str, list[str]]:
    return build_counting(lines, root, seed, seed_depth)[0]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("modules", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--sample-out", type=Path)
    ap.add_argument("--root", default="Tengoku")
    ap.add_argument("--seed", default="Seed")
    ap.add_argument("--seed-depth", type=int, default=1)
    a = ap.parse_args(argv)
    with open(a.modules, encoding="utf-8") as f:
        topics, left_out = build_counting(f, a.root, a.seed, a.seed_depth)
    a.out.write_text(json.dumps(topics), encoding="utf-8")
    if a.sample_out:
        with open(a.sample_out, "w", encoding="utf-8") as f:
            for t, names in topics.items():
                for n in names:
                    f.write(json.dumps({"name": n, "library": t}, ensure_ascii=False) + "\n")
    sizes = Counter({t: len(v) for t, v in topics.items()})
    seed_topics = {t: n for t, n in sizes.items() if t.split("/")[0] == a.seed}
    print(
        f"{len(topics)} topics ({len(seed_topics)} in the seed, {len(topics) - len(seed_topics)} libraries), {sum(sizes.values()):,} theorems "
        f"({sum(seed_topics.values()):,} in the seed), {left_out:,} internal theorems left out (the export of a whole tree does not write them); largest: "
        + ", ".join(f"{t} {n:,}" for t, n in sizes.most_common(5))
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
