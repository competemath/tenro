#!/usr/bin/env python3
"""intent.py - the `intent` index (Tengai docs/design.md, "indexes/ (a) intent (text)"): what a statement is FOR, searchable in words, name-blind. Standard library only.

  intent.py build --docs DOCS.tsv --isnad ISNAD.tsv --isnad-py TENGOKU/scripts/isnad.py --out DIR
  intent.py search DIR "the first list is a prefix of the second" [-k 10]

DOCS.tsv is the output of `tools/index/Docs.lean` (`doc<TAB>name<TAB>module<TAB>escaped text`); ISNAD.tsv that of `tengoku-isnad`. A docstring belongs to the STATEMENT its theorem states (the isnad id),
so two theorems that state the same thing share one document, and the index never needs a name. Output, deterministic (sorted, one JSON object a line):

  intent.jsonl   {"token", "df", "postings": [[doc position, term frequency], ...]}   an inverted index
  docs.jsonl     {"id": statement id, "length": tokens}                               one per document, in the order of the postings' positions
  intent-stats.json   counts, docs whose theorem has no id in the input, and the sha256 of each file

NAME-BLIND by construction, not by promise: the text is reduced to plain words; inline code (`like this`) and code blocks are DROPPED, because that is where a docstring spells out declaration names
and formulas, so what is indexed is the prose and no identifier. A test checks that no declared name occurs in the output. The cost is stated: a docstring that says everything inside code spans
is indexed by nothing, and a query is words, not formulas (the shape index is the formula-side search).

Ranking is BM25 (k1 = 1.2, b = 0.75), computed from the index alone, so a search over the released index needs nothing else.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from tengoku_isnad import load_module  # noqa: E402

K1, B = 1.2, 0.75
STOP = frozenset(
    "a an and are as at be by for from has have in is it its of on or that the their then there these this those to was were which with without not no if else when where while who whom whose".split()
)
FENCE = re.compile(r"```.*?```", re.DOTALL)
CODE = re.compile(r"`[^`]*`")
WORD = re.compile(r"[a-z]{2,}")


def unescape(s: str) -> str:
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            n = s[i + 1]
            out.append({"n": "\n", "t": "\t", "\\": "\\"}.get(n, n))
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def stem(w: str) -> str:
    """the only normalisation: a plural `s` goes (`lists` and `list` meet); nothing cleverer, so that the token of a word is predictable"""
    return w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w


def tokens(text: str) -> list[str]:
    """the words of the prose of a docstring: code spans and fences removed, lowercase letters only, stop words dropped"""
    prose = CODE.sub(" ", FENCE.sub(" ", text)).lower()
    return [stem(w) for w in WORD.findall(prose) if w not in STOP]


def build(docs: list[tuple[str, str]], id_of: dict[str, str]) -> dict:
    """docs: (theorem name, docstring); id_of: theorem name -> statement id. Returns the index and its statistics."""
    by_id: dict[str, list[str]] = {}
    missing = 0
    for name, text in docs:
        ident = id_of.get(name)
        if ident is None:
            missing += 1
            continue
        toks = tokens(text)
        if toks:
            by_id.setdefault(ident, []).extend(toks)
    ids = sorted(by_id)
    postings: dict[str, list[list[int]]] = {}
    lengths = []
    for pos, ident in enumerate(ids):
        toks = by_id[ident]
        lengths.append({"id": ident, "length": len(toks)})
        tf: dict[str, int] = {}
        for t in toks:
            tf[t] = tf.get(t, 0) + 1
        for t, n in tf.items():
            postings.setdefault(t, []).append([pos, n])
    index = [{"token": t, "df": len(p), "postings": p} for t, p in sorted(postings.items())]
    return {
        "index": index,
        "docs": lengths,
        "stats": {"documents": len(ids), "tokens": len(index), "docstrings_without_an_id": missing},
    }


def write(out: Path, built: dict) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for key, fname in (("index", "intent.jsonl"), ("docs", "docs.jsonl")):
        text = "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in built[key])
        (out / fname).write_text(text, encoding="utf-8")
        hashes[fname] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    stats = {**built["stats"], "sha256": hashes}
    (out / "intent-stats.json").write_text(json.dumps(stats, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    return stats


def load(out: Path) -> tuple[dict[str, list[list[int]]], list[dict]]:
    idx = {}
    for ln in (out / "intent.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(ln)
        idx[row["token"]] = row["postings"]
    docs = [json.loads(ln) for ln in (out / "docs.jsonl").read_text(encoding="utf-8").splitlines()]
    return idx, docs


def search(idx: dict[str, list[list[int]]], docs: list[dict], query: str, k: int = 10) -> list[tuple[str, float]]:
    """(statement id, BM25 score), best first, ties by id: the index alone is enough"""
    n = len(docs)
    if n == 0:
        return []
    avg = sum(d["length"] for d in docs) / n
    score: dict[int, float] = {}
    for t in set(tokens(query)):
        post = idx.get(t)
        if not post:
            continue
        idf = math.log(1 + (n - len(post) + 0.5) / (len(post) + 0.5))
        for pos, tf in post:
            dl = docs[pos]["length"]
            score[pos] = score.get(pos, 0.0) + idf * tf * (K1 + 1) / (tf + K1 * (1 - B + B * dl / avg))
    ranked = sorted(score.items(), key=lambda p: (-p[1], docs[p[0]]["id"]))
    return [(docs[pos]["id"], round(s, 6)) for pos, s in ranked[:k]]


def read_docs(path: Path) -> list[tuple[str, str]]:
    out = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        cols = ln.split("\t")
        if len(cols) >= 4 and cols[0] == "doc":
            out.append((cols[1], unescape("\t".join(cols[3:]))))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--docs", type=Path, required=True)
    b.add_argument("--isnad", type=Path, required=True)
    b.add_argument("--isnad-py", type=Path, required=True)
    b.add_argument("--out", type=Path, required=True)
    s = sub.add_parser("search")
    s.add_argument("dir", type=Path)
    s.add_argument("query")
    s.add_argument("-k", type=int, default=10)
    a = ap.parse_args(argv)
    if a.cmd == "build":
        mod = load_module(a.isnad_py)
        id_of = {}
        for ln in a.isnad.read_text(encoding="utf-8").splitlines():
            if ln.startswith("isnad1\t"):
                r = mod.Record(ln)
                id_of[r.name] = r.id
        print(json.dumps(write(a.out, build(read_docs(a.docs), id_of)), sort_keys=True, indent=1))
        return 0
    idx, docs = load(a.dir)
    for ident, sc in search(idx, docs, a.query, a.k):
        print(f"{sc}\t{ident}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
