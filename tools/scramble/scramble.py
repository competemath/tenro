#!/usr/bin/env python3
"""scramble.py - identifier scrambling for the name-obfuscation test (eval/protocol.md, design fix 2). Standard library only.

  scramble.py map     --library NAMES --problem NAMES --core NAMES --reserved TOKENS --key-file KEY > map.json
  scramble.py map     --names NAMES.tsv --key-file KEY > map.json          (NAMES.tsv from tools/scramble/ScrambleNames.lean: kind<TAB>name)
  scramble.py copy    SRC_PROJECT DST_PROJECT --map map.json                (the scrambled copy of a Lake project, files moved to their scrambled paths)
  scramble.py rewrite --map map.json FILE.lean...  (rewrites in place: the files of the scrambled copy, never the originals)

What is scrambled. BOTH the library's identifiers and the problem's, so that a prover can use neither a memorised library lemma name nor a memorised problem name. The unit is the COMPONENT of a name
(`Nat.succ_le` has the components `Nat` and `succ_le`): one global map component -> fresh component, applied to every identifier token of every file of the scrambled copy, so that namespaces,
`open`, dot notation and `export` resolve exactly as before (a name's meaning never depends on which spelling its component has, only on the components being the same everywhere).
What is kept: every component of a name that Lean's core (Init, Std, Lean) defines, whatever else uses it (a library name that is also a core word, like `Problem`, is NOT scrambled: `map` reports how many) (the core is not scrambled: the prover is told to use it), every reserved token of Lean's
parser (keywords, tactic names, attribute names: `--reserved`, from Lean's own token table in CI), and everything that is not an identifier (numbers, strings, operators). Comments and docstrings are
DROPPED from the scrambled copy: they spell the original names in prose.
The fresh name is `x` + the first 16 hex digits of HMAC-SHA256(key, component): reproducible from the key, which stays with the owner and never enters this repository (design: the scrambled problems and
the key live in tenro-eval). The map is checked: injective, no fresh name equal to any existing component or reserved token.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import sys
from pathlib import Path

PART = r"(?:[^\W\d]|_|«[^»]+»)(?:[\w'!?℀-⅏₀-ₜ]|«[^»]+»)*"
IDENT = re.compile(rf"{PART}(?:\.{PART})*")


def components(names: list[str]) -> set[str]:
    out: set[str] = set()
    for n in names:
        out |= {p.strip("«»") for p in re.findall(PART, n)}
    return out


def fresh(key: bytes, comp: str) -> str:
    return "x" + hmac.new(key, comp.encode("utf-8"), hashlib.sha256).hexdigest()[:16]


def build_map(library: list[str], problem: list[str], core: list[str], reserved: set[str], key: bytes) -> dict[str, str]:
    """component -> fresh component, for every component of the library and the problem that the core and the parser do not own"""
    keep = components(core) | reserved
    todo = (components(library) | components(problem)) - keep
    mapping = {c: fresh(key, c) for c in sorted(todo)}
    if len(set(mapping.values())) != len(mapping):
        raise ValueError("two components got the same fresh name: change the key")
    existing = components(library) | components(problem) | keep
    clash = set(mapping.values()) & existing
    if clash:
        raise ValueError(f"fresh names collide with existing ones: {sorted(clash)[:5]}")
    return mapping


def split_code(text: str):
    """yield (is_code, piece): comments and docstrings (nested `/- -/`, and `--` to the end of the line) are not code; neither is the inside of a string literal"""
    i, n, start = 0, len(text), 0
    while i < n:
        two = text[i : i + 2]
        if two == "--":
            j = text.find("\n", i)
            j = n if j < 0 else j
            yield True, text[start:i]
            yield False, text[i:j]
            i = start = j
        elif two == "/-":
            depth, j = 1, i + 2
            while j < n and depth:
                if text.startswith("/-", j):
                    depth, j = depth + 1, j + 2
                elif text.startswith("-/", j):
                    depth, j = depth - 1, j + 2
                else:
                    j += 1
            yield True, text[start:i]
            yield False, text[i:j]
            i = start = j
        elif text[i] == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            yield True, text[start:i]
            yield "string", text[i : j + 1]
            i = start = j + 1
        else:
            i += 1
    yield True, text[start:]


def rewrite_code(code: str, mapping: dict[str, str]) -> str:
    def sub(m: re.Match) -> str:
        parts = re.findall(PART, m.group(0))
        return ".".join(mapping.get(p.strip("«»"), p) for p in parts)

    return IDENT.sub(sub, code)


def rewrite(text: str, mapping: dict[str, str]) -> str:
    out = []
    for kind, piece in split_code(text):
        if kind is True:
            out.append(rewrite_code(piece, mapping))
        elif kind == "string":
            out.append(piece)
        else:  # a comment or docstring: dropped, but its lines are kept so positions of errors stay readable
            out.append("\n" * piece.count("\n"))
    return "".join(out)


def read_names(path: str) -> tuple[list[str], list[str], set[str]]:
    """`kind<TAB>name` lines (tools/scramble/ScrambleNames.lean): (library names, core names, reserved tokens)"""
    lib, core, reserved = [], [], set()
    for ln in Path(path).read_text(encoding="utf-8").splitlines():
        kind, _, name = ln.partition("\t")
        if kind == "lib":
            lib.append(name)
        elif kind == "core":
            core.append(name)
        elif kind == "reserved":
            reserved.add(name)
    return lib, core, reserved


QUOTED = re.compile(r'"([^"\\]*)"')


def copy_tree(src: Path, dst: Path, mapping: dict[str, str]) -> int:
    """The scrambled copy of a Lake project: every .lean file rewritten and moved to the path its components map to, and the quoted names of lakefile.toml mapped. Returns the number of files."""
    n = 0
    for f in sorted(src.rglob("*")):
        if not f.is_file() or ".lake" in f.parts:
            continue
        rel = f.relative_to(src)
        if f.suffix == ".lean":
            parts = [mapping.get(p, p) for p in rel.with_suffix("").parts]
            target = dst.joinpath(*parts).with_suffix(".lean")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(rewrite(f.read_text(encoding="utf-8"), mapping), encoding="utf-8")
            n += 1
        elif f.name in ("lakefile.toml", "lean-toolchain"):
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            text = f.read_text(encoding="utf-8")
            if f.name == "lakefile.toml":
                text = QUOTED.sub(lambda m: f'"{mapping.get(m.group(1), m.group(1))}"', text)
            target.write_text(text, encoding="utf-8")
    return n


def read_lines(path: str) -> list[str]:
    return [ln.strip() for ln in Path(path).read_text(encoding="utf-8").splitlines() if ln.strip()]


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "map" and "--names" in argv:
        opts = dict(zip(argv[1::2], argv[2::2], strict=False))
        lib, core, reserved = read_names(opts["--names"])
        mapping = build_map(lib, [], core, reserved, Path(opts["--key-file"]).read_bytes().strip())
        unscrambled = components(lib) - set(mapping)
        print(
            f"scramble: {len(mapping)} components scrambled, {len(unscrambled)} kept because the core or the parser owns the same word: {sorted(unscrambled)[:20]}",
            file=sys.stderr,
        )
        print(json.dumps(mapping, indent=0, sort_keys=True))
        return 0
    if len(argv) == 5 and argv[0] == "copy" and argv[3] == "--map":
        print(copy_tree(Path(argv[1]), Path(argv[2]), json.loads(Path(argv[4]).read_text(encoding="utf-8"))))
        return 0
    if argv and argv[0] == "map":
        opts = dict(zip(argv[1::2], argv[2::2], strict=False))
        mapping = build_map(
            read_lines(opts["--library"]), read_lines(opts["--problem"]), read_lines(opts["--core"]), set(read_lines(opts["--reserved"])),
            Path(opts["--key-file"]).read_bytes().strip(),
        )  # fmt: skip
        print(json.dumps(mapping, indent=0, sort_keys=True))
        return 0
    if len(argv) >= 3 and argv[0] == "rewrite" and argv[1] == "--map":
        mapping = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
        for f in argv[3:]:
            p = Path(f)
            p.write_text(rewrite(p.read_text(encoding="utf-8"), mapping), encoding="utf-8")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
