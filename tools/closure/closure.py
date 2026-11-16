#!/usr/bin/env python3
"""closure.py - the dependency closure of declarations, computed from a lean4export file alone.

  closure.py EXPORT.ndjson --names N1 N2 ... [--names-file FILE] [--meta META.tsv] [--include-self] > CLOSURES.jsonl

The closure of a declaration is every constant its proof term (or definition body) reaches, transitively. This is the input of the tawatur independence
test (Tengoku's `scripts/tawatur.py`, docs/tawatur.md), and the footprint of tengai's alternate routes (ADR-0002). One line per requested name:

  {"id": ..., "name": ..., "lib": ..., "closure": [...], "statement_closure": [...], "modules": {...}}

`closure` is the transitive closure of the REDUCED value; `statement_closure` is the transitive closure of the constants of the type. `id`, `lib` and `modules` come from
`--meta` (tab separated: name, isnad id, library, module; the module may be empty). Without a row for a name, `id` is `stmt:<index of the type term>` (two theorems with
one statement share it inside one export, because lean4export writes equal terms once), `lib` is `unknown` and `modules` is left out.

REDUCED means: a binder whose variable the body never uses is removed together with the term bound to it, repeatedly (a `have` that nothing uses, then the `have`
that only that one used, ...). Without this a proof could be made to look different from another by padding it with lemmas it never applies. The three ways Lean
writes such a binder are all handled: `letE` (with or without `nondep`), a beta-redex `(fun x => b) a`, and `letFun a (fun x => b)`. A binder that IS used keeps
everything it brings. Nothing else is rewritten: no beta, no delta, no eta, no proof irrelevance (a padding that is really applied is a different proof, and the
other axes of the divergence measure see it).

Reads format 3.x of lean4export (the pin Tengoku's independent check uses). No Lean code runs here. lean4export writes every sub-term before the terms that use it, so
the index of a term is larger than the indices of its children: the evaluation below goes in index order and never recurses.
"""

from __future__ import annotations

import argparse
import json
import sys
from array import array
from pathlib import Path

try:
    import orjson

    loads = orjson.loads
except ImportError:  # slower, same result
    loads = json.loads

BVAR, SORT, CONST, APP, LAM, PI, LET, PROJ, LIT, MDATA = range(10)
DECLS = ("axiom", "def", "thm", "opaque", "quot", "inductive")
EMPTY = 0


class Export:
    """A lean4export file held in arrays, and the closures computed from it."""

    def __init__(self) -> None:
        self.name_pre = array("I", [0])
        self.name_part: list[str] = [""]
        self.kind = array("B")
        self.a = array("I")
        self.b = array("I")
        self.c = array("I")
        # declared constant (name index) -> (type term, value term or -1, other terms its dependencies come from)
        self.decl: dict[int, tuple[int, int, tuple[int, ...]]] = {}
        self.decl_kind: dict[int, str] = {}
        self.lines = 0
        self._letfun: frozenset[int] | None = None
        # interned sets of constants: id 0 is the empty set
        self.sets: list[frozenset[int]] = [frozenset()]
        self.set_id: dict[frozenset[int], int] = {frozenset(): EMPTY}
        self.union_cache: dict[tuple[int, int], int] = {}
        self.single_cache: dict[int, int] = {}
        self.red: dict[int, tuple[int, int]] = {}  # term -> (set id of its constants, mask of its loose bound variables), once reduced
        self.direct_cache: dict[int, frozenset[int]] = {}

    # ----- reading

    def name(self, i: int) -> str:
        parts = []
        while i:
            parts.append(self.name_part[i])
            i = self.name_pre[i]
        return ".".join(reversed(parts))

    def read(self, path: Path) -> None:
        with open(path, "rb") as f:
            for line in f:
                self.lines += 1
                self.line(loads(line))

    def line(self, o: dict) -> None:
        if "ie" in o:
            self.term(o)
        elif "in" in o:
            if o["in"] != len(self.name_part):
                raise SystemExit(f"closure: name {o['in']} out of order at line {self.lines}")
            v = o.get("str") or o["num"]
            self.name_pre.append(v["pre"])
            self.name_part.append(v["str"] if "str" in v else str(v["i"]))
        elif "il" in o:
            return  # a universe level: it carries no constant
        elif "meta" in o:
            version = o["meta"]["format"]["version"]
            if not version.startswith("3."):
                raise SystemExit(f"closure: export format {version}, this reads 3.x")
        elif any(k in o for k in DECLS):
            self.declaration(o)
        else:
            raise SystemExit(f"closure: unknown line {self.lines}: {str(o)[:120]}")

    def term(self, o: dict) -> None:
        i = o["ie"]
        if i != len(self.kind):
            raise SystemExit(f"closure: term {i} out of order at line {self.lines}")
        k, a, b, c = LIT, 0, 0, 0
        if "app" in o:
            k, a, b = APP, o["app"]["fn"], o["app"]["arg"]
        elif "const" in o:
            k, a = CONST, o["const"]["name"]
        elif "bvar" in o:
            k, a = BVAR, o["bvar"]
        elif "lam" in o:
            k, a, b = LAM, o["lam"]["type"], o["lam"]["body"]
        elif "forallE" in o:
            k, a, b = PI, o["forallE"]["type"], o["forallE"]["body"]
        elif "letE" in o:
            v = o["letE"]
            k, a, b, c = LET, v["type"], v["value"], v["body"]
        elif "proj" in o:
            k, a, b = PROJ, o["proj"]["struct"], o["proj"]["typeName"]
        elif "mdata" in o:
            k, a = MDATA, o["mdata"]["expr"]
        elif "sort" in o:
            k = SORT
        elif "natVal" in o or "strVal" in o:
            k = LIT
        else:
            raise SystemExit(f"closure: unknown term at line {self.lines}: {str(o)[:120]}")
        for child in self.children_of(k, a, b, c):
            if child >= i:
                raise SystemExit(f"closure: term {i} uses term {child}, which is not before it (line {self.lines})")
        self.kind.append(k)
        self.a.append(a)
        self.b.append(b)
        self.c.append(c)

    @staticmethod
    def children_of(k: int, a: int, b: int, c: int) -> tuple[int, ...]:
        if k in (APP, LAM, PI):
            return (a, b)
        if k == LET:
            return (a, b, c)
        if k in (PROJ, MDATA):
            return (a,)
        return ()

    def declaration(self, o: dict) -> None:
        kind = next(k for k in DECLS if k in o)
        v = o[kind]
        if kind == "inductive":
            for x in v["types"] + v["ctors"]:
                self.decl[x["name"]] = (x["type"], -1, ())
                self.decl_kind[x["name"]] = "inductive" if x in v["types"] else "ctor"
            for r in v["recs"]:
                self.decl[r["name"]] = (r["type"], -1, tuple(rule["rhs"] for rule in r["rules"]))
                self.decl_kind[r["name"]] = "rec"
            return
        self.decl[v["name"]] = (v["type"], v.get("value", -1), ())
        self.decl_kind[v["name"]] = kind

    # ----- sets of constants

    def single(self, n: int) -> int:
        s = self.single_cache.get(n)
        if s is None:
            s = self.single_cache[n] = self.intern(frozenset([n]))
        return s

    def intern(self, s: frozenset[int]) -> int:
        i = self.set_id.get(s)
        if i is None:
            i = self.set_id[s] = len(self.sets)
            self.sets.append(s)
        return i

    def union(self, x: int, y: int) -> int:
        if x == y or y == EMPTY:
            return x
        if x == EMPTY:
            return y
        k = (x, y) if x < y else (y, x)
        r = self.union_cache.get(k)
        if r is None:
            r = self.union_cache[k] = self.intern(self.sets[x] | self.sets[y])
        return r

    # ----- reduction

    def letfun_names(self) -> frozenset[int]:
        if self._letfun is None:
            self._letfun = frozenset(i for i, p in enumerate(self.name_part) if p == "letFun" and self.name_pre[i] == 0 and i)
        return self._letfun

    def is_letfun_spine(self, f: int) -> bool:
        """f is `letFun alpha beta v`: three applications on the constant letFun"""
        for _ in range(3):
            if self.kind[f] != APP:
                return False
            f = self.a[f]
        return self.kind[f] == CONST and self.a[f] in self.letfun_names()

    def reachable(self, roots: list[int]) -> list[int]:
        """the terms below `roots` that are not reduced yet, in increasing index order (children before parents)"""
        seen: set[int] = set()
        stack = [r for r in roots if r not in self.red]
        while stack:
            t = stack.pop()
            if t in seen or t in self.red:
                continue
            seen.add(t)
            stack.extend(self.children_of(self.kind[t], self.a[t], self.b[t], self.c[t]))
        return sorted(seen)

    def reduce_terms(self, roots: list[int]) -> None:
        """fill self.red for every term below `roots`"""
        red, kind, a, b, c = self.red, self.kind, self.a, self.b, self.c
        for t in self.reachable(roots):
            k = kind[t]
            if k == CONST:
                red[t] = (self.single(a[t]), 0)
            elif k == BVAR:
                red[t] = (EMPTY, 1 << a[t])
            elif k in (SORT, LIT):
                red[t] = (EMPTY, 0)
            elif k == MDATA:
                red[t] = red[a[t]]
            elif k == PROJ:
                s, m = red[a[t]]
                red[t] = (self.union(s, self.single(b[t])), m)
            elif k in (LAM, PI):
                (st, mt), (sb, mb) = red[a[t]], red[b[t]]
                red[t] = (self.union(st, sb), mt | (mb >> 1))
            elif k == LET:
                (st, mt), (sv, mv), (sb, mb) = red[a[t]], red[b[t]], red[c[t]]
                if not mb & 1:  # nothing uses the variable: the binder and the term bound to it go
                    red[t] = (sb, mb >> 1)
                else:
                    red[t] = (self.union(self.union(st, sv), sb), mt | mv | (mb >> 1))
            else:  # APP
                f, x = a[t], b[t]
                dead = None
                if kind[f] == LAM:  # (fun x => body) arg
                    dead = red[b[f]]
                elif kind[x] == LAM and self.is_letfun_spine(f):  # letFun alpha beta v (fun x => body)
                    dead = red[b[x]]
                if dead is not None and not dead[1] & 1:
                    red[t] = (dead[0], dead[1] >> 1)
                else:
                    (sf, mf), (sx, mx) = red[f], red[x]
                    red[t] = (self.union(sf, sx), mf | mx)

    def terms_set(self, term: int) -> frozenset[int]:
        self.reduce_terms([term])
        return self.sets[self.red[term][0]]

    # ----- closures

    def direct(self, n: int) -> frozenset[int]:
        """the constants one declaration mentions: its type, its reduced value, the right-hand sides of a recursor's rules"""
        d = self.direct_cache.get(n)
        if d is None:
            entry = self.decl.get(n)
            if entry is None:
                d = frozenset()
            else:
                ty, val, extra = entry
                terms = [ty, *extra] + ([val] if val >= 0 else [])
                self.reduce_terms(terms)
                s = EMPTY
                for t in terms:
                    s = self.union(s, self.red[t][0])
                d = self.sets[s]
            self.direct_cache[n] = d
        return d

    def closure(self, roots: set[int]) -> set[int]:
        """every constant reachable from the constants in `roots`, the roots themselves included"""
        seen: set[int] = set()
        stack = list(roots)
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            stack.extend(self.direct(n) - seen)
        return seen

    def names_to_index(self) -> dict[str, int]:
        return {self.name(i): i for i in self.decl}

    def record(self, n: int, include_self: bool = False) -> dict:
        """the closure of one declaration, as the tawatur input line (without id, lib and modules)"""
        ty, _, _ = self.decl[n]
        proof = self.closure(set(self.direct(n)))
        stmt = self.closure(set(self.terms_set(ty)))
        if not include_self:
            proof.discard(n)
            stmt.discard(n)
        return {
            "name": self.name(n),
            "closure": sorted(self.name(i) for i in proof),
            "statement_closure": sorted(self.name(i) for i in stmt),
            "type_term": ty,
        }


def read_meta(path: Path | None) -> dict[str, tuple[str, str, str]]:
    meta: dict[str, tuple[str, str, str]] = {}
    if path is None:
        return meta
    for ln in path.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        parts = ln.split("\t")
        if len(parts) < 3:
            raise SystemExit(f"closure: a meta line needs name, id, library: {ln[:80]!r}")
        meta[parts[0]] = (parts[1], parts[2], parts[3] if len(parts) > 3 else "")
    return meta


def records(ex: Export, names: list[str], meta: dict[str, tuple[str, str, str]], include_self: bool = False) -> list[dict]:
    index = ex.names_to_index()
    out = []
    for name in names:
        if name not in index:
            raise SystemExit(f"closure: {name} is not declared in the export")
        r = ex.record(index[name], include_self)
        ident, lib, module = meta.get(name, (f"stmt:{r['type_term']}", "unknown", ""))
        del r["type_term"]
        r = {"id": ident, "lib": lib, **r}
        if module:
            r["modules"] = {name: module}
        out.append(r)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("export", type=Path)
    ap.add_argument("--names", nargs="*", default=[])
    ap.add_argument("--names-file", type=Path, help="one declaration name a line")
    ap.add_argument("--meta", type=Path)
    ap.add_argument("--include-self", action="store_true")
    a = ap.parse_args(argv)
    names = list(a.names)
    if a.names_file:
        names += [ln.strip() for ln in a.names_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not names:
        raise SystemExit("closure: no names given (--names or --names-file)")
    ex = Export()
    ex.read(a.export)
    for r in records(ex, names, read_meta(a.meta), a.include_self):
        sys.stdout.write(json.dumps(r, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
