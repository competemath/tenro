#!/usr/bin/env python3
"""compare_exports.py - whether a statements export says the same as the full export about every declaration it holds. Standard library only.

  compare_exports.py FULL.ndjson STATEMENTS.ndjson [--out REPORT.json]

`lean4export --statements` (tools/export/lean4export-statements.patch) writes a theorem as an AXIOM of the same name, level parameters and type, and does not visit its proof, so the constants that only proofs use
are not written at all. Nothing else may change. This checks that, on two exports of the same environment (the full one and the one with `--statements`), without trusting the numbering of either:

  * every declaration is reduced to a digest of what the export says about it, with every reference to a name, a universe level or a term replaced by what it stands for (the numbering of terms depends on
    which proofs were visited before them, so two exports of one declaration number it differently);
  * a declaration in both exports must have the same digest, except a THEOREM of the full export that is an axiom in the statements export: it must have the same name, level parameters and type;
  * the statements export holds no theorem, and nothing the full export lacks.

Exit 0 when all of that holds, 1 otherwise; the report says what was compared, how many theorems stand as axioms and how many declarations dropped out with the proofs. The names, levels and terms of a file are held in
64-bit digests (8 bytes a term): a 40-million-line export takes about 400 MB and a few minutes.
"""

from __future__ import annotations

import argparse
import json
import sys
from array import array
from hashlib import blake2b
from pathlib import Path

try:
    import orjson

    loads = orjson.loads
except ImportError:  # slower, same result
    loads = json.loads

NAME_KEYS = frozenset({"name", "induct", "typeName", "ctor"})
NAME_LIST_KEYS = frozenset({"levelParams", "all", "ctors"})
TERM_KEYS = frozenset({"type", "value", "rhs"})
DECLS = ("axiom", "def", "thm", "opaque", "quot", "inductive")


def digest(*parts: object) -> int:
    return int.from_bytes(blake2b(repr(parts).encode("utf-8"), digest_size=8).digest(), "big")


class Reader:
    """one export, reduced to {declared name: (kind, digest of everything, digest of name, level parameters and type)}"""

    def __init__(self) -> None:
        self.names: list[str] = [""]
        self.levels = array("Q", [digest("zero")])
        self.terms = array("Q")
        self.decls: dict[str, tuple[str, int, int]] = {}

    def read(self, path: Path) -> None:
        with open(path, "rb") as f:
            for n, line in enumerate(f, 1):
                if not line.strip():
                    continue
                self.line(loads(line), n)

    def line(self, o: dict, n: int) -> None:
        if "ie" in o:
            self.term(o, n)
        elif "in" in o:
            if o["in"] != len(self.names):
                raise SystemExit(f"compare_exports: name {o['in']} out of order at line {n}")
            if "str" in o:
                part, pre = o["str"]["str"], o["str"]["pre"]
            else:
                part, pre = f"#{o['num']['i']}", o["num"]["pre"]
            self.names.append(f"{self.names[pre]}.{part}" if pre else part)
        elif "il" in o:
            if o["il"] != len(self.levels):
                raise SystemExit(f"compare_exports: level {o['il']} out of order at line {n}")
            if "succ" in o:
                self.levels.append(digest("succ", self.levels[o["succ"]]))
            elif "max" in o:
                self.levels.append(digest("max", *(self.levels[x] for x in o["max"])))
            elif "imax" in o:
                self.levels.append(digest("imax", *(self.levels[x] for x in o["imax"])))
            else:
                self.levels.append(digest("param", self.names[o["param"]]))
        elif "meta" in o:
            version = o["meta"]["format"]["version"]
            if not version.startswith("3."):
                raise SystemExit(f"compare_exports: export format {version}, this reads 3.x")
        elif any(k in o for k in DECLS):
            self.declaration(o, n)
        else:
            raise SystemExit(f"compare_exports: unknown line {n}: {str(o)[:120]}")

    def term(self, o: dict, n: int) -> None:
        i = o["ie"]
        if i != len(self.terms):
            raise SystemExit(f"compare_exports: term {i} out of order at line {n}")
        t = self.terms
        if "app" in o:
            v = o["app"]
            d = digest("app", t[v["fn"]], t[v["arg"]])
        elif "const" in o:
            v = o["const"]
            d = digest("const", self.names[v["name"]], tuple(self.levels[u] for u in v["us"]))
        elif "bvar" in o:
            d = digest("bvar", o["bvar"])
        elif "sort" in o:
            d = digest("sort", self.levels[o["sort"]])
        elif "lam" in o or "forallE" in o:
            kind = "lam" if "lam" in o else "forallE"
            v = o[kind]
            d = digest(kind, self.names[v["name"]], v["binderInfo"], t[v["type"]], t[v["body"]])
        elif "letE" in o:
            v = o["letE"]
            d = digest("letE", self.names[v["name"]], t[v["type"]], t[v["value"]], t[v["body"]], v["nondep"])
        elif "proj" in o:
            v = o["proj"]
            d = digest("proj", self.names[v["typeName"]], v["idx"], t[v["struct"]])
        elif "natVal" in o:
            d = digest("natVal", o["natVal"])
        elif "strVal" in o:
            d = digest("strVal", o["strVal"])
        elif "mdata" in o:
            v = o["mdata"]
            d = digest("mdata", t[v["expr"]], json.dumps(v.get("data"), sort_keys=True))
        else:
            raise SystemExit(f"compare_exports: unknown term at line {n}: {str(o)[:120]}")
        self.terms.append(d)

    def resolve(self, v: object, key: str = "") -> object:
        """a field of a declaration with every reference replaced by what it stands for"""
        if isinstance(v, dict):
            return {k: self.resolve(x, k) for k, x in sorted(v.items())}
        if isinstance(v, list):
            if key in NAME_LIST_KEYS and all(isinstance(x, int) for x in v):
                return [self.names[x] for x in v]
            return [self.resolve(x, key) for x in v]
        if isinstance(v, bool) or not isinstance(v, int):
            return v
        if key in NAME_KEYS:
            return self.names[v]
        if key in TERM_KEYS:
            return self.terms[v]
        return v

    def declaration(self, o: dict, n: int) -> None:
        kind = next(k for k in DECLS if k in o)
        v = o[kind]
        members = (
            [(m, "inductive") for m in v["types"]] + [(m, "ctor") for m in v["ctors"]] + [(m, "rec") for m in v["recs"]]
            if kind == "inductive"
            else [(v, kind)]
        )
        for m, k in members:
            name = self.names[m["name"]]
            if name in self.decls:
                raise SystemExit(f"compare_exports: {name} declared twice (line {n})")
            whole = digest(k, json.dumps(self.resolve(m), sort_keys=True))
            head = digest(name, tuple(self.names[x] for x in m["levelParams"]), self.terms[m["type"]])
            self.decls[name] = (k, whole, head)


def read(path: Path) -> Reader:
    r = Reader()
    r.read(path)
    return r


def compare(full: Reader, stmt: Reader) -> dict:
    """what the two readers' declarations say about each other"""
    problems: dict[str, list[str]] = {"changed": [], "only_in_statements": [], "theorems_left": []}
    stubbed = same = 0
    for name, (kind, whole, head) in stmt.decls.items():
        if kind == "thm":
            problems["theorems_left"].append(name)
        other = full.decls.get(name)
        if other is None:
            problems["only_in_statements"].append(name)
        elif other[0] == "thm" and kind == "axiom":
            if other[2] == head:
                stubbed += 1
            else:
                problems["changed"].append(name)
        elif other[0] == kind and other[1] == whole:
            same += 1
        else:
            problems["changed"].append(name)
    dropped = {n for n in full.decls if n not in stmt.decls}

    def kinds(r: Reader) -> dict[str, int]:
        out: dict[str, int] = {}
        for k, _, _ in r.decls.values():
            out[k] = out.get(k, 0) + 1
        return dict(sorted(out.items()))

    return {
        "full": {"declarations": len(full.decls), "terms": len(full.terms), "kinds": kinds(full)},
        "statements": {"declarations": len(stmt.decls), "terms": len(stmt.terms), "kinds": kinds(stmt)},
        "theorems_as_axioms": stubbed,
        "unchanged": same,
        "dropped_with_the_proofs": len(dropped),
        "problems": {k: v[:20] for k, v in problems.items()},
        "problem_counts": {k: len(v) for k, v in problems.items()},
        "passed": not any(problems.values()),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("full", type=Path)
    ap.add_argument("statements", type=Path)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    report = compare(read(a.full), read(a.statements))
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(json.dumps(report, indent=1, sort_keys=True) + "\n")
    f, s = report["full"], report["statements"]
    print(
        f"full: {f['declarations']:,} declarations, {f['terms']:,} terms; statements: {s['declarations']:,} declarations, {s['terms']:,} terms "
        f"({100 * s['terms'] / max(f['terms'], 1):.1f} % of the terms); {report['theorems_as_axioms']:,} theorems stand as axioms, "
        f"{report['unchanged']:,} declarations are the same, {report['dropped_with_the_proofs']:,} dropped out with the proofs"
    )
    for k, n in report["problem_counts"].items():
        if n:
            print(f"PROBLEM {k}: {n}, for example {report['problems'][k][:3]}")
    print("passed" if report["passed"] else "FAILED")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
