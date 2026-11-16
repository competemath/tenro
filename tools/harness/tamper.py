#!/usr/bin/env python3
"""tamper.py - the frozen-prefix tamper check of the eval harness (the brief's gate 4: 0% undetected statement/definition tampering). Standard library only.

  tamper.py check ORIGINAL.lean SUBMISSION.lean       exit 0 when the submission is the original's frozen prefix followed by a clean proof
  tamper.py selftest [--out tamper.json]              the checker on a corpus of tamper mutants and of legitimate proofs: {"cases", "undetected", "false_alarms"}

A problem file is the problem's whole header (imports, definitions, the theorem's statement up to `:=`) followed by one sentinel line, `-- ==== PROOF ====`; the prover supplies what follows. The submission is
accepted only if
  1. it begins with EXACTLY the original's bytes up to and including the sentinel (every character of the statement and of every definition is frozen: not one byte, not a homoglyph, not a line ending);
  2. the proof after the sentinel contains no second sentinel and no top-level command at all (a proof is a term or a tactic block: helper lemmas live in `have` and `where`, never in new commands);
  3. the proof uses none of the escapes that make a kernel-checked statement mean less or run unchecked code: `sorry`, `admit`, `native_decide`, `Lean.ofReduceBool`, `unsafe`, `implemented_by`, `extern`,
     `set_option`, `open ... in` that rebinds a name, `local` notation or macro, `run_cmd`, `#eval`.
This is the FIRST of two independent checks: the second is external and runs after compilation (`#print axioms` of the problem's theorem and the isnad id of its statement against the id of the original's
statement, tools/readiness/report.py gate 4). A text check cannot see a semantic trick; the id comparison can, so neither is trusted alone.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scramble"))
from scramble import split_code  # noqa: E402

SENTINEL = "-- ==== PROOF ===="
ESCAPES = [
    (re.compile(r"\bsorry\b"), "sorry"),
    (re.compile(r"\badmit\b"), "admit"),
    (re.compile(r"\bnative_decide\b"), "native_decide"),
    (re.compile(r"\bdecide\s*\+\s*native\b"), "decide +native"),
    (re.compile(r"\bLean\.ofReduce(?:Bool|Nat)\b|\bofReduce(?:Bool|Nat)\b"), "ofReduceBool/Nat"),
    (re.compile(r"\bunsafe\b"), "unsafe"),
    (re.compile(r"\bimplemented_by\b|\bextern\b"), "implemented_by/extern"),
    (re.compile(r"\bset_option\b"), "set_option"),
    (re.compile(r"\bopen\b[^\n]*\bin\b"), "open ... in"),
    (
        re.compile(r"\blocal\s+(?:notation|macro|syntax|infix|infixl|infixr|prefix|postfix|elab|instance|attribute)\b"),
        "local notation/macro/instance",
    ),
    (re.compile(r"\brun_cmd\b|\brun_tac\b|\brun_elab\b|#eval\b|#reduce\b"), "run_cmd/#eval"),
    (
        re.compile(r"\b(?:axiom|opaque|initialize|builtin_initialize|macro_rules|macro|syntax|elab|notation|infix[lr]?|prefix|postfix)\b"),
        "command keyword",
    ),
]
COMMAND_AT_COLUMN_0 = re.compile(
    r"^(?!where\b|termination_by\b|decreasing_by\b|\||<;>|\)|\]|\})[^\s\-/]", re.M
)  # any non-blank, non-comment line that starts in column 0 starts a command (or breaks the proof's indentation)


def code_of(text: str) -> str:
    """the proof with comments and docstrings blanked and string literals emptied (so words inside them are not mistaken for code)"""
    out = []
    for kind, piece in split_code(text):
        out.append(piece if kind is True else ("" if kind is not False else "\n" * piece.count("\n")))
    return "".join(out)


def check(original: str, submission: str) -> list[str]:
    problems: list[str] = []
    cut = original.find(SENTINEL)
    if cut < 0 or original.count(SENTINEL) != 1:
        return ["the original has no single sentinel line"]
    end = cut + len(SENTINEL)
    prefix = original[:end]
    if not submission.startswith(prefix):
        # name the first byte that differs: a human reads this
        i = next((k for k, (a, b) in enumerate(zip(prefix, submission, strict=False)) if a != b), min(len(prefix), len(submission)))
        problems.append(f"the frozen prefix was changed (first difference at byte {i})")
        return problems
    tail = submission[end:]
    if SENTINEL in tail:
        problems.append("a second sentinel in the proof")
    body = code_of(tail)
    for rx, name in ESCAPES:
        if rx.search(body):
            problems.append(f"the proof uses {name}")
    if COMMAND_AT_COLUMN_0.search(body):
        problems.append("a top-level command or an unindented line in the proof")
    return problems


ORIGINAL = """import Mathlib
open Nat

/-- the problem -/
theorem p (n : Nat) (h : 0 < n) : n ≤ n * n := by
-- ==== PROOF ===="""

LEGITIMATE = [
    "\n  nlinarith [h]\n",
    "\n  have h1 : n ≤ n * n := Nat.le_mul_self n\n  exact h1\n",
    "\n  -- a comment that says sorry and axiom and set_option\n  simpa using Nat.le_mul_self n\n",
    '\n  have : "sorry" = "sorry" := rfl\n  exact Nat.le_mul_self n\n',
    "\n  exact aux n\nwhere\n  aux (m : Nat) : m ≤ m * m := Nat.le_mul_self m\n",
    "\n  decide\n",
]
MUTANTS = {
    "a hypothesis dropped": ORIGINAL.replace(" (h : 0 < n)", "") + "\n  exact Nat.le_mul_self n\n",
    "the inequality weakened": ORIGINAL.replace("n ≤ n * n", "n ≤ n * n + 1") + "\n  omega\n",
    "a numeral changed": ORIGINAL.replace("0 < n", "1 < n") + "\n  omega\n",
    "the theorem renamed": ORIGINAL.replace("theorem p ", "theorem q ") + "\n  omega\n",
    "an open changed": ORIGINAL.replace("open Nat", "open Int") + "\n  omega\n",
    "a homoglyph in the statement": ORIGINAL.replace("Nat", "Nаt", 1) + "\n  omega\n",  # Cyrillic a
    "a line ending changed": ORIGINAL.replace("\n", "\r\n") + "\n  omega\n",
    "the sentinel removed": ORIGINAL.replace(SENTINEL, "") + "\n  omega\n",
    "a second sentinel": ORIGINAL + "\n  omega\n" + SENTINEL + "\n  omega\n",
    "sorry": ORIGINAL + "\n  sorry\n",
    "an axiom": ORIGINAL + "\n  exact absurd h (axiomFalse n)\naxiom axiomFalse (n : Nat) : ¬ 0 < n\n",
    "a new top-level theorem": ORIGINAL + "\n  exact helper n\ntheorem helper (n : Nat) : n ≤ n * n := sorry_free\n",
    "set_option": ORIGINAL + "\n  set_option maxRecDepth 1 in omega\n",
    "native_decide": ORIGINAL + "\n  native_decide\n",
    "decide +native": ORIGINAL + "\n  decide +native\n",
    "ofReduceBool": ORIGINAL + "\n  exact Lean.ofReduceBool _ _ rfl\n",
    "a local notation": ORIGINAL + "\n  local notation \"n\" => 0\n  omega\n",
    "open ... in": ORIGINAL + "\n  open Int in omega\n",
    "unsafe": ORIGINAL + "\n  exact unsafe_thing\nunsafe def unsafe_thing : True := trivial\n",
    "#eval": ORIGINAL + "\n  omega\n#eval 1\n",
    "a macro": ORIGINAL + "\n  omega\nmacro \"omega\" : tactic => `(tactic| skip)\n",
    "a command after the proof": ORIGINAL + "\n  omega\ninstance : Inhabited Nat := ⟨5⟩\n",
    "the whole file replaced": "theorem p (n : Nat) : n ≤ n * n := by omega\n",
    "the prefix truncated": ORIGINAL[: len(ORIGINAL) - 30] + "\n  omega\n",
}  # fmt: skip


def selftest() -> dict:
    undetected = [name for name, text in MUTANTS.items() if not check(ORIGINAL, text)]
    false_alarms = [i for i, proof in enumerate(LEGITIMATE) if check(ORIGINAL, ORIGINAL + proof)]
    return {
        "cases": len(MUTANTS),
        "undetected": len(undetected),
        "undetected_names": undetected,
        "legitimate": len(LEGITIMATE),
        "false_alarms": len(false_alarms),
    }


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) == 3 and argv[0] == "check":
        problems = check(Path(argv[1]).read_text(encoding="utf-8", newline=""), Path(argv[2]).read_text(encoding="utf-8", newline=""))
        for p in problems:
            print(p)
        return 1 if problems else 0
    if argv and argv[0] == "selftest":
        result = selftest()
        text = json.dumps(result, indent=1)
        if "--out" in argv:
            Path(argv[argv.index("--out") + 1]).write_text(text + "\n", encoding="utf-8")
        print(text)
        return 0 if result["undetected"] == 0 and result["false_alarms"] == 0 else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
