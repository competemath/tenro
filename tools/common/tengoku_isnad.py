"""Reading Tengoku's isnad output with Tengoku's own code (the pinned `.tengoku/scripts/isnad.py`): the recipe is never copied into tenro."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_module(isnad_py: Path):
    spec = importlib.util.spec_from_file_location("tengoku_isnad_py", isnad_py)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def load_isnad(
    isnad_py: Path, record_lines: list[str], dep_lines: list[str]
) -> tuple[list[tuple[str, str, str]], list[tuple[str, list[str]]]]:
    """(name, id, shape) per `isnad1` record, and (name, dependency names) per `isnad1-deps` line."""
    mod = load_module(isnad_py)
    records = []
    for ln in record_lines:
        if ln.startswith("isnad1\t"):
            r = mod.Record(ln)
            records.append((r.name, r.id, r.shape))
    deps = []
    for ln in dep_lines:
        if ln.startswith(mod.DEPS_TAG + "\t"):
            name, _, ds = mod.parse_deps_line(ln)
            deps.append((name, ds))
    return records, deps
