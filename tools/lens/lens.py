#!/usr/bin/env python3
"""lens.py - the lens model of ADR-0003 on statement ids: composition, inversion, skip-lenses, and the isnad round trip. Standard library only.

  lens.py check --old OLD.tsv --new NEW.tsv --lens LENS.json [--pairs PAIRS.tsv]      accept each migrated theorem only if the lens maps id(t') back to id(t)

A change between two versions is an isomorphism up to a complement (ADR-0003, 2): `D_old ~ D_new x R`. On statement ids it is a map `forward`: old id -> [new ids]. One new id is a
one-to-one change (a rename of a convention); several are a SPLIT, and what the split lost is not lost: `residual` keeps what is needed to recombine (opaque here: a name, a hash).
An id the map does not mention is unchanged. The BACKWARD map is derived and must be a function: two old statements may not become the same new statement, or the lift back would
have to guess (`inverse` refuses). An old statement the lens leaves alone that another one is mapped onto is caught by the acceptance check itself: its lift is not its own id. Acceptance (ADR-0003, 3): for a theorem t migrated to t', the lift of id(t') back through the lens equals id(t); anything else is rejected,
there is no silent weakening. A report always carries its denominator.

LENS.json: {"from": v_old, "to": v_new, "forward": {old_id: [new_id, ...]}, "residual": {old_id: anything}}
OLD.tsv / NEW.tsv: `name<TAB>statement id` (what `isnad.py id` prints); PAIRS.tsv: `old name<TAB>new name` (a name missing from it migrated under its own name).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

Lens = dict  # {"from": str, "to": str, "forward": {id: [id]}, "residual": {id: any}}


class LensError(ValueError):
    pass


def make(v_from: str, v_to: str, forward: dict[str, list[str]], residual: dict | None = None) -> Lens:
    return {"from": v_from, "to": v_to, "forward": {k: list(v) for k, v in forward.items() if v != [k]}, "residual": dict(residual or {})}


def apply(lens: Lens, ident: str) -> list[str]:
    return lens["forward"].get(ident, [ident])


def inverse(lens: Lens) -> dict[str, str]:
    """new id -> old id. An id that two different old ids lead to has no lift back: the lens is not invertible and is refused."""
    back: dict[str, str] = {}
    for old, news in lens["forward"].items():
        for new in news:
            if back.setdefault(new, old) != old:
                raise LensError(f"{new} is the image of both {back[new]} and {old}: the lift back would have to guess")
    return back


def lift(lens_inverse: dict[str, str], ident: str) -> str:
    return lens_inverse.get(ident, ident)


def compose(first: Lens, second: Lens) -> Lens:
    """first, then second: old -> new. Splits compose by mapping every part."""
    if first["to"] != second["from"]:
        raise LensError(f"cannot compose {first['from']}->{first['to']} with {second['from']}->{second['to']}")
    ids = set(first["forward"]) | {i for i in second["forward"] if i not in {n for news in first["forward"].values() for n in news}}
    forward = {i: [z for y in apply(first, i) for z in apply(second, y)] for i in ids}
    residual = {**second["residual"], **first["residual"]}
    return make(first["from"], second["to"], forward, residual)


class Chain:
    """A run of lenses l_0 .. l_{n-1} (version i to i+1) with skip-lenses on ALIGNED blocks: `power(k, i)`, for i a multiple of 2^k, is the composition of the 2^k lenses from i. They are
    built once and kept (about n compositions in all, like the nodes of a segment tree), and the lens from version i to version j is then the composition of at most 2 log2 n of them
    (`between`): a long migration costs O(log n) compositions, not one per commit (ADR-0003, 4)."""

    def __init__(self, lenses: list[Lens]):
        for a, b in zip(lenses, lenses[1:], strict=False):
            if a["to"] != b["from"]:
                raise LensError(f"the chain breaks between {a['to']} and {b['from']}")
        self.lenses = lenses
        self.blocks: dict[tuple[int, int], Lens] = {}
        self.build_compositions = 0
        self.query_compositions = 0

    def power(self, k: int, i: int) -> Lens:
        if k == 0:
            return self.lenses[i]
        if (k, i) not in self.blocks:
            self.build_compositions += 1
            self.blocks[(k, i)] = compose(self.power(k - 1, i), self.power(k - 1, i + (1 << (k - 1))))
        return self.blocks[(k, i)]

    def between(self, i: int, j: int) -> Lens:
        """the lens from version i to version j (i < j): the aligned blocks that tile [i, j), composed in order"""
        if not 0 <= i < j <= len(self.lenses):
            raise LensError("need 0 <= i < j <= the number of lenses")
        result: Lens | None = None
        pos = i
        while pos < j:
            k = 0
            while pos % (1 << (k + 1)) == 0 and pos + (1 << (k + 1)) <= j:
                k += 1
            piece = self.power(k, pos)
            if result is None:
                result = piece
            else:
                self.query_compositions += 1
                result = compose(result, piece)
            pos += 1 << k
        assert result is not None
        return result


def check_migration(pairs: list[tuple[str, str]], old_ids: dict[str, str], new_ids: dict[str, str], lens: Lens) -> dict:
    """Accept each (old name, new name) whose new id lifts back to the old id. The report has the denominator (every pair offered) and the reason of every rejection."""
    back = inverse(lens)
    accepted, rejected = 0, []
    for old_name, new_name in pairs:
        if old_name not in old_ids:
            rejected.append({"old": old_name, "new": new_name, "why": "the old theorem has no id"})
        elif new_name not in new_ids:
            rejected.append({"old": old_name, "new": new_name, "why": "not migrated: the new theorem has no id"})
        elif lift(back, new_ids[new_name]) != old_ids[old_name]:
            rejected.append(
                {
                    "old": old_name,
                    "new": new_name,
                    "why": f"id({new_name}) lifts back to {lift(back, new_ids[new_name])}, not to {old_ids[old_name]}",
                }
            )
        else:
            accepted += 1
    return {
        "denominator": len(pairs),
        "accepted": accepted,
        "rate": round(accepted / len(pairs), 4) if pairs else None,
        "rejected": rejected,
    }


def read_table(path: Path) -> dict[str, str]:
    table = {}
    for ln in path.read_text(encoding="utf-8").splitlines():
        parts = ln.split("\t")
        if len(parts) >= 2:
            table[parts[0]] = parts[1]
    return table


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--old", type=Path, required=True)
    c.add_argument("--new", type=Path, required=True)
    c.add_argument("--lens", type=Path, required=True)
    c.add_argument("--pairs", type=Path)
    a = ap.parse_args(argv)
    old, new = read_table(a.old), read_table(a.new)
    pairs = (
        [tuple(ln.split("\t")[:2]) for ln in a.pairs.read_text(encoding="utf-8").splitlines() if "\t" in ln]
        if a.pairs
        else [(n, n) for n in old]
    )
    report = check_migration(pairs, old, new, json.loads(a.lens.read_text(encoding="utf-8")))
    print(json.dumps(report, indent=1, sort_keys=True))
    return 0 if not report["rejected"] else 1


if __name__ == "__main__":
    sys.exit(main())
