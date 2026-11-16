#!/usr/bin/env python3
"""scramble.py - identifier scrambling for the name-obfuscation test (eval/protocol.md, design fix 2). Standard library only.

  scramble.py map     --library NAMES --problem NAMES --core NAMES --reserved TOKENS --key-file KEY > map.json
  scramble.py rewrite --map map.json FILE.lean...  (rewrites in place: the files of the scrambled copy, never the originals)

What is scrambled. BOTH the library's identifiers and the problem's, so that a prover can use neither a memorised library lemma name nor a memorised problem name. The unit is the COMPONENT of a name
(`Nat.succ_le` has the components `Nat` and `succ_le`): one global map component -> fresh component, applied to every identifier token of every file of the scrambled copy, so that namespaces,
`open`, dot notation and `export` resolve exactly as before (a name's meaning never depends on which spelling its component has, only on the components being the same everywhere).
What is kept: every component of a name that Lean's core (Init, Std, Lean) defines, whatever else uses it (the core is not scrambled: the prover is told to use it), every reserved token of Lean's
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


def read_lines(path: str) -> list[str]:
    return [ln.strip() for ln in Path(path).read_text(encoding="utf-8").splitlines() if ln.strip()]


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
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
