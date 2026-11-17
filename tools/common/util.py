"""util.py - the two small things several tools did each their own way: how far apart two sets are, and reading a JSON-lines file. Standard library only.

`jaccard(a, b)`: |a ∩ b| / |a ∪ b|, and 1.0 for two empty sets (two things that share nothing and have nothing are not different). `distance(a, b) = 1 - jaccard(a, b)` is the divergence measure of the
tawatur tier (Tengai ADR-0002) and the closure overlap of the calibration labels (calibration/PROTOCOL.md); one definition, so the two cannot drift apart.
`read_jsonl(path)`: one JSON value per non-blank line.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa, sb = set(a), set(b)
    union = sa | sb
    return len(sa & sb) / len(union) if union else 1.0


def distance(a: Iterable[str], b: Iterable[str]) -> float:
    return 1 - jaccard(a, b)


def read_jsonl(path: Path | str) -> list:
    return [json.loads(ln) for ln in Path(path).read_text(encoding="utf-8").splitlines() if ln.strip()]
