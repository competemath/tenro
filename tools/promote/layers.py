#!/usr/bin/env python3
"""layers.py - the layers of a promotion, from the dependency closures of an export. Standard library only (closure.py's reader is loaded, never copied).

  layers.py EXPORT.ndjson --topics TOPICS.json [--added ADDED.jsonl] --out DIR [--prefix TengaiData] [--foundation Foundation]

A promotion that is one module is loaded whole by every session. A promotion in LAYERS is a foundation layer, holding the constants more than one topic needs, and one layer per topic, holding the constants only
that topic needs; every layer imports the layers it depends on, and a session imports the layers of its topic and nothing else (tengai ADR-0005, "Layers"; `tengai-replay --import` and `--only` are the
mechanism). TOPICS.json is `{"<topic>": ["a.theorem.name", ...]}`. The CLOSURE of a topic is every constant its theorems reach, transitively, through types and values (the whole closure the kernel needs, not the
reduced one of closure.py: padding that a proof does not use is still in the term the kernel checks). A constant's layer is decided by the set of topics whose closure holds it:

  one topic            that topic's layer
  two topics or more   the foundation

A constant is used by at least the topics that use anything depending on it, so the foundation never depends on a topic layer, and a topic layer depends only on itself and the foundation. That is checked
for every constant, not assumed. An inductive type with its constructors and recursors is one unit (the kernel derives the recursors with the type): its users are the union over its members, and `--only`
names it by its first type. `--added` is the list of names a one-module replay added (what Lean core did not already hold): only those are placed, so core constants are left to `Init`.

Writes DIR/<layer>.names.jsonl (one JSON array of name components a line, the input of `--only`) and DIR/layers.json (the layers in the order they must be replayed, what each imports, and the sizes).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "closure"))
import closure as cl  # noqa: E402


class Full(cl.Export):
    """closure.py's reader, with the constants of a declaration as they stand (nothing reduced away) and the units the kernel adds together"""

    def __init__(self) -> None:
        super().__init__()
        self.name_is_num: set[int] = set()
        self.unit_of: dict[int, int] = {}  # declared constant -> the first name of its unit
        self.members: dict[int, list[int]] = {}  # first name of a unit -> every constant of it
        self.direct_full: dict[int, frozenset[int]] = {}

    def line(self, o: dict) -> None:
        if "in" in o and "num" in o:
            self.name_is_num.add(len(self.name_part))
        super().line(o)

    def declaration(self, o: dict) -> None:
        super().declaration(o)
        kind = next(k for k in cl.DECLS if k in o)
        v = o[kind]
        if kind == "inductive":
            names = [x["name"] for x in v["types"] + v["ctors"] + v["recs"]]
            first = v["types"][0]["name"]
        else:
            names, first = [v["name"]], v["name"]
        self.members[first] = names
        for n in names:
            self.unit_of[n] = first

    def components(self, i: int) -> list[str | int]:
        parts: list[str | int] = []
        while i:
            parts.append(int(self.name_part[i]) if i in self.name_is_num else self.name_part[i])
            i = self.name_pre[i]
        return parts[::-1]

    def unit_direct(self, first: int) -> frozenset[int]:
        """the units one unit's constants mention (itself left out), from their types, values and recursor rules.

        One walk of the terms below the unit's declarations, with a set of the terms already seen in that walk: the memory is the size of one declaration's term, never of the export (a set of constants for
        every term of a 2 GB export would hold, for the large proofs, more constants than there are terms). A term shared with another declaration is walked again for that one: the cost is the sum of
        the declarations' own term sizes."""
        d = self.direct_full.get(first)
        if d is None:
            kind, a, b, c = self.kind, self.a, self.b, self.c
            consts: set[int] = set()
            seen: set[int] = set()
            stack: list[int] = []
            for m in self.members[first]:
                ty, val, extra = self.decl[m]
                stack.extend([ty, *extra] + ([val] if val >= 0 else []))
            while stack:
                t = stack.pop()
                if t in seen:
                    continue
                seen.add(t)
                k = kind[t]
                if k == cl.CONST:
                    consts.add(a[t])
                elif k == cl.PROJ:
                    consts.add(b[t])
                    stack.append(a[t])
                elif k in (cl.APP, cl.LAM, cl.PI):
                    stack.append(a[t])
                    stack.append(b[t])
                elif k == cl.LET:
                    stack.extend((a[t], b[t], c[t]))
                elif k == cl.MDATA:
                    stack.append(a[t])
            d = frozenset(self.unit_of[x] for x in consts if x in self.unit_of) - {first}
            self.direct_full[first] = d
        return d

    def unit_closure(self, roots: set[int]) -> set[int]:
        seen: set[int] = set()
        stack = list(roots)
        while stack:
            u = stack.pop()
            if u in seen:
                continue
            seen.add(u)
            stack.extend(self.unit_direct(u) - seen)
        return seen


def read_names(path: Path) -> set[tuple]:
    out: set[tuple] = set()
    for ln in path.read_text(encoding="utf-8").splitlines():
        if ln.strip():
            out.add(tuple(json.loads(ln)))
    return out


def module_component(topic: str) -> str:
    """a topic's name as one component of a module name: `equational-theories` -> `EquationalTheories`"""
    parts = "".join(w[:1].upper() + w[1:] for w in topic.replace("_", "-").replace(".", "-").split("-") if w)
    if not parts or not parts[0].isalpha() or not parts.isalnum():
        raise SystemExit(f"layers: the topic {topic!r} does not make a module name")
    return parts


def plan(
    ex: Full, topics: dict[str, list[str]], universe: set[tuple] | None, prefix: str = "TengaiData", foundation: str = "Foundation"
) -> dict:
    index = {ex.name(i): i for i in ex.decl}
    modules: dict[str, str] = {}
    for t in topics:
        m = module_component(t)
        if m == foundation or m in modules.values():
            raise SystemExit(f"layers: the topic {t!r} makes the module name {m}, which another topic or the foundation has")
        modules[t] = m
    placed = {u for u in ex.members if universe is None or tuple(ex.components(u)) in universe}
    roots: dict[str, set[int]] = {}
    for t, names in topics.items():
        missing = [n for n in names if n not in index]
        if missing:
            raise SystemExit(f"layers: {len(missing)} theorems of the topic {t!r} are not in the export: {missing[:5]}")
        roots[t] = {ex.unit_of[index[n]] for n in names}
    users: dict[int, int] = {}
    for bit, t in enumerate(topics):
        for u in ex.unit_closure(roots[t]):
            if u in placed:
                users[u] = users.get(u, 0) | (1 << bit)
    layer_of: dict[int, str] = {}
    order = list(topics)
    for u, mask in users.items():
        layer_of[u] = foundation if mask & (mask - 1) else order[mask.bit_length() - 1]
    for u, layer in layer_of.items():  # the property the layers stand on, checked for every constant
        for d in ex.unit_direct(u) & placed:
            if layer_of.get(d) not in (foundation, layer):
                raise SystemExit(f"layers: {ex.name(u)} is in layer {layer} but depends on {ex.name(d)}, which is in {layer_of.get(d)}")
    out_layers: list[dict] = []
    names_out: dict[str, list[list]] = {}
    for layer in [foundation, *order]:
        units = sorted((u for u, name in layer_of.items() if name == layer), key=lambda u: ex.name(u))
        if not units:
            continue
        module = f"{prefix}.{foundation if layer == foundation else modules[layer]}"
        names_out[module] = [ex.components(u) for u in units]
        out_layers.append(
            {
                "module": module,
                "topic": None if layer == foundation else layer,
                "imports": []
                if layer == foundation
                else ([f"{prefix}.{foundation}"] if any(x == foundation for x in layer_of.values()) else []),
                "units": len(units),
                "constants": sum(len(ex.members[u]) for u in units),
                "file": f"{module}.names.jsonl",
            }
        )
    per_topic = {}
    for t in order:
        own = sum(1 for u, name in layer_of.items() if name == t)
        shared = sum(1 for u, name in layer_of.items() if name == foundation and users[u] >> order.index(t) & 1)
        per_topic[t] = {
            "module": f"{prefix}.{modules[t]}",
            "theorems": len(topics[t]),
            "own_units": own,
            "foundation_units_used": shared,
            "units_loaded": own + shared,
        }
    total = len(layer_of)
    return {
        "layers": out_layers,
        "topics": per_topic,
        "totals": {
            "units": total,
            "foundation_units": sum(1 for x in layer_of.values() if x == foundation),
            "constants": sum(len(ex.members[u]) for u in layer_of),
        },
        "names": names_out,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("export", type=Path)
    ap.add_argument("--topics", required=True, type=Path)
    ap.add_argument("--added", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--prefix", default="TengaiData")
    ap.add_argument("--foundation", default="Foundation")
    a = ap.parse_args(argv)
    ex = Full()
    ex.read(a.export)
    topics = json.loads(a.topics.read_text(encoding="utf-8"))
    p = plan(ex, topics, read_names(a.added) if a.added else None, a.prefix, a.foundation)
    a.out.mkdir(parents=True, exist_ok=True)
    for module, names in p.pop("names").items():
        (a.out / f"{module}.names.jsonl").write_text("".join(json.dumps(n, ensure_ascii=False) + "\n" for n in names), encoding="utf-8")
    (a.out / "layers.json").write_text(json.dumps(p, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    t = p["totals"]
    print(
        f"{len(p['layers'])} layers, {t['units']} units ({t['constants']} constants), {t['foundation_units']} of the units in the foundation"
    )
    for name, x in p["topics"].items():
        print(
            f"  {name}: {x['theorems']} theorems, {x['units_loaded']} units loaded ({x['own_units']} its own + {x['foundation_units_used']} of the foundation)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
