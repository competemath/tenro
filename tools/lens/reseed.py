#!/usr/bin/env python3
"""reseed.py - what a library re-cut did to its theorems, computed from two manifests (the real-migration corpus of the readiness gate 3). Standard library only.

  reseed.py classify OLD.jsonl NEW.jsonl [--names-out names.jsonl]

OLD and NEW are Tengoku's `data/intake/<library>/manifest.jsonl` at two commits (lines `{name, statement, module, ...}`). Every old theorem lands in exactly one class:

  unchanged   same name, same statement, same module
  moved       same name, same statement, another module
  restated    same name, another statement (a lens entry is needed: the statement id changes)
  renamed     the name is gone and exactly one theorem of the new manifest that was not in the old one has the same statement once the declared name is removed (or, when several share the statement,
              exactly one in the same module)
  removed     the name is gone and no such theorem exists (a theorem that cannot be placed in one class is `removed` plus an `added`: the record never guesses)

`added` counts the new theorems no old one maps to. The two numbers a migration is judged by are kept apart, because they answer different questions:

  survival   (unchanged + moved + renamed + restated) / old: how much of the old library still exists
  fidelity   (unchanged + moved + renamed) / (old theorems that survive): of those that survive, how many are the SAME statement (the lens is the identity on ids: nothing to migrate)

The statement id used here is a hash of the whitespace-normalised statement with the declared name removed: a stand-in for the isnad id (the manifest does not carry it), and a stricter one, since it is textual.
`names-out` lists every theorem that changed in any way (`{"old", "new", "change", "old_module", "new_module"}`), the shape of `data/migrations/<id>/names.jsonl` in docs/migration-support.md of Tengoku.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from util import read_jsonl  # noqa: E402

DECL = re.compile(r"^(theorem|lemma)\s+\S+")


def statement_id(statement: str) -> str:
    """hash of the statement with whitespace normalised and the declared name replaced by `_`"""
    s = DECL.sub(r"\1 _", re.sub(r"\s+", " ", statement).strip())
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _same_up_to_qualification(old: dict, new: dict, old_name: str, new_name: str) -> bool:
    """the two statements are the same once the new name is read as the old one wherever it occurs in the declaration"""
    a = re.sub(r"\s+", " ", old["statement"]).strip()
    b = re.sub(r"\s+", " ", new["statement"]).strip().replace(new_name, old_name, 1)
    return a == b


def classify(old: list[dict], new: list[dict]) -> tuple[dict, list[dict]]:
    o = {x["name"]: x for x in old}
    n = {x["name"]: x for x in new}
    if len(o) != len(old) or len(n) != len(new):
        raise ValueError("a manifest lists a name twice")
    changes: list[dict] = []
    counts = {k: 0 for k in ("unchanged", "moved", "restated", "renamed", "removed")}
    gone = [name for name in o if name not in n]
    new_only = [name for name in n if name not in o]
    old_by_id: dict[str, list[str]] = {}
    new_by_id: dict[str, list[str]] = {}
    for name in gone:
        old_by_id.setdefault(statement_id(o[name]["statement"]), []).append(name)
    for name in new_only:
        new_by_id.setdefault(statement_id(n[name]["statement"]), []).append(name)
    renamed_to: dict[str, str] = {}
    for sid, olds in old_by_id.items():
        news = new_by_id.get(sid, [])
        if len(olds) == 1 and len(news) == 1:
            renamed_to[olds[0]] = news[0]
    # a statement shared by several theorems of the library cannot be matched by statement alone; within ONE module it often can (a rename keeps the module): exactly one gone and one new
    # theorem with that statement in that module is still a rename, and anything less clear stays a removal plus an addition
    old_by_mod: dict[tuple[str, str], list[str]] = {}
    new_by_mod: dict[tuple[str, str], list[str]] = {}
    for name in gone:
        if name not in renamed_to:
            old_by_mod.setdefault((o[name]["module"], statement_id(o[name]["statement"])), []).append(name)
    taken = set(renamed_to.values())
    for name in new_only:
        if name not in taken:
            new_by_mod.setdefault((n[name]["module"], statement_id(n[name]["statement"])), []).append(name)
    for key, olds in old_by_mod.items():
        news = new_by_mod.get(key, [])
        if len(olds) == 1 and len(news) == 1:
            renamed_to[olds[0]] = news[0]
    # a qualification (`foo` became `Ns.foo`) keeps the last component of the name and the module, and changes the statement only where the name occurs in it: match on those two, and ask that the
    # statements agree once the old name's qualified form is read as the old name (a statement that really changed is `restated`, not a rename)
    unresolved_old = [name for name in gone if name not in renamed_to]
    taken = set(renamed_to.values())
    new_by_last: dict[tuple[str, str], list[str]] = {}
    for name in new_only:
        if name not in taken:
            new_by_last.setdefault((n[name]["module"], name.rsplit(".", 1)[-1]), []).append(name)
    for name in unresolved_old:
        cands = new_by_last.get((o[name]["module"], name.rsplit(".", 1)[-1]), [])
        if len(cands) == 1 and _same_up_to_qualification(o[name], n[cands[0]], name, cands[0]):
            renamed_to[name] = cands[0]
            new_by_last[(o[name]["module"], name.rsplit(".", 1)[-1])] = []
    for name, x in o.items():
        if name in n:
            y = n[name]
            if re.sub(r"\s+", " ", y["statement"]).strip() != re.sub(r"\s+", " ", x["statement"]).strip():
                counts["restated"] += 1
                changes.append({"old": name, "new": name, "change": "restated", "old_module": x["module"], "new_module": y["module"]})
            elif y["module"] != x["module"]:
                counts["moved"] += 1
                changes.append({"old": name, "new": name, "change": "moved", "old_module": x["module"], "new_module": y["module"]})
            else:
                counts["unchanged"] += 1
        elif name in renamed_to:
            counts["renamed"] += 1
            changes.append(
                {
                    "old": name,
                    "new": renamed_to[name],
                    "change": "renamed",
                    "old_module": x["module"],
                    "new_module": n[renamed_to[name]]["module"],
                }
            )
        else:
            counts["removed"] += 1
            changes.append({"old": name, "new": None, "change": "removed", "old_module": x["module"], "new_module": None})
    survivors = counts["unchanged"] + counts["moved"] + counts["renamed"] + counts["restated"]
    same = counts["unchanged"] + counts["moved"] + counts["renamed"]
    mapped_new = {c["new"] for c in changes if c["change"] == "renamed"} | {name for name in o if name in n}
    summary = {
        "old": len(o),
        "new": len(n),
        **counts,
        "added": len(n) - len(mapped_new),
        "survival": round(survivors / len(o), 6) if o else None,
        "fidelity": round(same / survivors, 6) if survivors else None,
    }
    return summary, sorted(changes, key=lambda c: (c["change"], c["old"]))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("classify")
    c.add_argument("old", type=Path)
    c.add_argument("new", type=Path)
    c.add_argument("--names-out", type=Path, default=None)
    a = ap.parse_args(argv)
    summary, changes = classify(read_jsonl(a.old), read_jsonl(a.new))
    if a.names_out:
        a.names_out.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in changes), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
