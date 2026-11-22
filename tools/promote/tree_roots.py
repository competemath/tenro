#!/usr/bin/env python3
"""tree_roots.py - the root modules of a whole-tree export, with some libraries left out. Standard library only.

  tree_roots.py --tree .tengoku --roots-out ROOTS.txt --report REPORT.json [--all Tengoku/All.lean] [--exclude "Tengoku.LanaBelyi Tengoku.LanaGenl"]

Tengoku's tree is one aggregate module, `Tengoku/All.lean`, that imports the root module of every library (and the seed). A whole-tree export imports that aggregate (`lean4export Tengoku.All`), so it holds everything.
A release that cannot hold a library (its licence text is missing at the commit the tree pins, say) imports the roots of the other libraries instead: `lean4export Tengoku.A Tengoku.B ...` takes several modules, and so do
`Modules.lean`, `tengai-typeinfo` and `tengai-extinfo`.

Leaving a library out is not enough on its own: a library that imports it would carry its definitions into the export (a constant a statement reaches is in the export), so every library that imports an excluded one is
left out too, and so on until nothing kept imports anything left out. The libraries are the modules `Tengoku/All.lean` imports; a module belongs to the library whose root is the longest prefix of its name, and a library
imports another when a file under its root has an `import` of a module of the other. Only the header of a file is read (comments, `prelude` and the `import` lines, in any of the forms of Lean 4.34: `public import`,
`meta import`, `import all`), as Lean reads it: an `import` in a docstring or after the first command is not an import.

`--roots-out` gets one root module per line: `Tengoku.All` when nothing is excluded (the export is then the one it always was), the kept roots otherwise. `--report` says what was left out and why: each library asked for
(`requested`), and each one that imports a library left out (the first import found, as `file: module`). The result is checked before it is written: no kept library imports a library that was left out, and every root is
kept or left out. A name in `--exclude` that is not a root of the aggregate is an error, not a silent no-op: a typo must not release what it was to hold back.

  tree_roots.py --check-modules MODULES.txt --report REPORT.json

The import graph above is read from the sources, and a header this reader misreads would let a library that should have been left out stay in, carrying its definitions into the export unseen. So the workflow checks the
result a second way, from Lean itself: `Modules.lean --modules-out` writes the name of every module of the environment the kept roots import, and `--check-modules` fails when one of them belongs to a library that the
report says was left out (the module is the root or below it at a dot). It runs before the export, which is the expensive part.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HEADER_READ = 1 << 16  # a header is short; a file whose header runs past this is read whole
IDENT = re.compile(r"(?:(?!--)[^\s()\[\]{},;:])+")  # a module name: up to whitespace (or a comment that starts right after it)
IMPORT = re.compile(r"(?:(?:public|meta|private)\s+)*import(?:\s+all)?\s+")
WORD_END = re.compile(r"[\s]|$")


def skip_blank_and_comments(text: str, i: int) -> int:
    """the index of the next character that is neither whitespace nor part of a comment (`--` to the end of the line, `/- ... -/` with nesting; `/-!` and `/--` are block comments too)"""
    n = len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
        elif text.startswith("--", i):
            j = text.find("\n", i)
            i = n if j < 0 else j + 1
        elif text.startswith("/-", i):
            depth, i = 1, i + 2
            while i < n and depth:
                if text.startswith("/-", i):
                    depth, i = depth + 1, i + 2
                elif text.startswith("-/", i):
                    depth, i = depth - 1, i + 2
                else:
                    i += 1
        else:
            break
    return i


def header_imports(text: str) -> tuple[list[str], int]:
    """the modules a file imports, and the index where the header ended (the end of the text when the text ended inside it)"""
    mods: list[str] = []
    i = skip_blank_and_comments(text, 0)
    if text.startswith("prelude", i) and WORD_END.match(text, i + 7):
        i = skip_blank_and_comments(text, i + 7)
    while True:
        m = IMPORT.match(text, i)
        if not m:
            return mods, i
        name = IDENT.match(text, m.end())
        if not name:
            return mods, i
        mods.append(name.group().replace("«", "").replace("»", ""))
        i = skip_blank_and_comments(text, name.end())


def read_imports(path: Path) -> list[str]:
    with path.open(encoding="utf-8", errors="replace") as f:
        head = f.read(HEADER_READ)
        mods, stop = header_imports(head)
        if len(head) < HEADER_READ or stop < len(head) - 256:  # the whole file was read, or the header ended well inside what was read
            return mods
        return header_imports(head + f.read())[0]  # the header may run on past what was read


def files_of(tree: Path, root: str) -> list[Path]:
    """the sources of the library with this root module: `A/B.lean` and everything under `A/B/`"""
    base = tree.joinpath(*root.split("."))
    found = [base.with_suffix(".lean")] if base.with_suffix(".lean").is_file() else []
    if base.is_dir():
        found += sorted(base.rglob("*.lean"))
    return found


def owner_of(module: str, roots: set[str]) -> str | None:
    """the library a module belongs to: the longest root that is the module or a prefix of it at a dot"""
    parts = module.split(".")
    for k in range(len(parts), 0, -1):
        if ".".join(parts[:k]) in roots:
            return ".".join(parts[:k])
    return None


def import_graph(tree: Path, roots: list[str]) -> dict[str, dict[str, str]]:
    """for each library, the other libraries it imports, each with the first import that says so (`file: module`)"""
    rootset = set(roots)
    graph: dict[str, dict[str, str]] = {}
    for root in roots:
        deps: dict[str, str] = {}
        for path in files_of(tree, root):
            for mod in read_imports(path):
                other = owner_of(mod, rootset)
                if other is not None and other != root and other not in deps:
                    deps[other] = f"{path.relative_to(tree).as_posix()}: {mod}"
        graph[root] = deps
    return graph


def plan(roots: list[str], graph: dict[str, dict[str, str]], exclude: list[str]) -> dict:
    unknown = [e for e in exclude if e not in roots]
    if unknown:
        raise SystemExit(f"tree_roots: not a root module of the aggregate: {' '.join(unknown)}")
    out: dict[str, str] = {e: "requested" for e in exclude}
    changed = True
    while changed:  # a library that imports one left out is left out, and so is a library that imports that one
        changed = False
        for root in roots:
            if root in out:
                continue
            hit = next((d for d in graph[root] if d in out), None)
            if hit is not None:
                out[root] = f"imports {hit} ({graph[root][hit]})"
                changed = True
    kept = [r for r in roots if r not in out]
    for root in kept:  # the postcondition, from the graph itself
        bad = [d for d in graph[root] if d in out]
        assert not bad, (root, bad)
    assert len(kept) + len(out) == len(roots)
    return {"excluded": [{"root": r, "why": out[r]} for r in roots if r in out], "kept": kept}


def check_modules(report: dict, modules: list[str]) -> list[str]:
    """the modules of the imported environment that belong to a library the report says was left out"""
    left_out = [e["root"] for e in report["excluded"]]
    return [m for m in modules if any(m == r or m.startswith(r + ".") for r in left_out)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--tree", type=Path, help="the Tengoku checkout (the directory that holds Tengoku/)")
    ap.add_argument("--all", default="Tengoku/All.lean", help="the aggregate module, relative to --tree")
    ap.add_argument("--exclude", default="", help="root modules to leave out, separated by spaces")
    ap.add_argument("--roots-out", type=Path)
    ap.add_argument("--report", type=Path, help="written when the roots are made, read by --check-modules")
    ap.add_argument(
        "--check-modules",
        type=Path,
        help="the module names of the environment the kept roots import (Modules.lean --modules-out): none may belong to a library that was left out",
    )
    a = ap.parse_args(argv)
    if a.check_modules is not None:
        if a.report is None:
            ap.error("--check-modules needs --report")
        modules = [m for m in a.check_modules.read_text().split() if m]
        if not modules:
            raise SystemExit(f"tree_roots: {a.check_modules} names no module: the environment was not imported")
        bad = check_modules(json.loads(a.report.read_text()), modules)
        if bad:
            raise SystemExit(
                f"tree_roots: the kept roots import {len(bad)} modules of libraries that were left out ({', '.join(bad[:5])}): the sources' import graph missed an import"
            )
        print(f"the environment of the kept roots holds {len(modules)} modules and none of a library that was left out")
        return 0
    if a.tree is None or a.roots_out is None or a.report is None:
        ap.error("--tree, --roots-out and --report are needed to make the roots")
    aggregate = a.tree / a.all
    if not aggregate.is_file():
        raise SystemExit(f"tree_roots: no aggregate module at {aggregate}")
    roots = list(dict.fromkeys(read_imports(aggregate)))
    if not roots:
        raise SystemExit(f"tree_roots: {aggregate} imports nothing")
    exclude = list(dict.fromkeys(a.exclude.split()))
    all_module = ".".join(Path(a.all).with_suffix("").parts)
    if not exclude:
        result = {"excluded": [], "kept": roots}
        lines = [all_module]  # nothing left out: the export imports the aggregate, as it always did
    else:
        result = plan(roots, import_graph(a.tree, roots), exclude)
        lines = result["kept"]
        if not lines:
            raise SystemExit("tree_roots: every library is left out")
    report = {
        "all": all_module,
        "requested": exclude,
        "roots": len(roots),
        "kept": len(result["kept"]),
        "excluded": result["excluded"],
        "export_roots": lines,
    }
    a.roots_out.write_text("\n".join(lines) + "\n")
    a.report.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    print(
        f"the tree's roots: {len(roots)} libraries and modules in {all_module}; {len(result['excluded'])} left out ({len(exclude)} asked for), {len(result['kept'])} kept"
    )
    for e in result["excluded"]:
        print(f"  left out {e['root']}: {e['why']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
