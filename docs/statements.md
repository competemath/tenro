# The statements flavor: a base for search, not for checking

A snapshot of a promotion (docs/transplant.md, docs/consuming.md) holds every constant that a proof of a promoted theorem reaches, because the kernel checks the proofs again: 183,763 constants and 1.6 GB of `.olean` for 4,778 theorems. A **statements** export keeps each theorem as an **axiom of its type** and does not visit its proof, so everything only the proofs used drops out with them.

## Why this is sound for search (invariant I1)

`exact`, `apply`, `rw`, `simp [lemma]` and the elaboration of a statement use the *type* of a lemma. The proof of a lemma is never unfolded (proof irrelevance), so a lemma that stands as an axiom of its type serves the search. A proof found there is **checked afterwards in an environment that holds the real proofs** (the full snapshot, or Tengoku's own tree): untrusted search, trusted checking.

What it is not: a verified environment. `#print axioms` of a promoted theorem prints the theorem itself. A statements snapshot has to say so in its manifest (`flavor: statements`) and name the Tengoku commit its statements come from, whose independent check is what vouches for the proofs.

## What was built

* `tools/export/lean4export-statements.patch`: `lean4export --statements`, a theorem is written as an `axiom` line (same name, level parameters and type; `isUnsafe` false) and its proof is not visited. Nothing else changes.
* `tools/export/compare_exports.py`: two exports of one environment (full, `--statements`) agree on every declaration they share, without trusting the numbering of terms (each declaration is reduced to a digest with every name, level and term resolved): a theorem is an axiom with the same name, level parameters and type; the statements export has no theorem and nothing the full one lacks. 12 tests on synthetic exports; the workflow `export-statements` runs it on `Init` exported both ways before anything else.
* `.github/workflows/export-statements.yml`: the gates, then the wide sample of the transplant runs exported as statements (the same 4,800 roots as the 1.6 GB snapshot: a size to set against it), then the whole tree exported as statements (lines, bytes, time, memory) and, as a probe, each replayed through the kernel by `tengai-replay` (size of the module, what a session loads).
* `tools/export/export_stats.py`: the lines of an export by kind, bytes, zstd size, and the wall time and peak memory of the export from `/usr/bin/time -v`.
* `tools/promote/stmt_closure.py` and the workflow `stmt-closure`: the same question answered from the export of a sample alone.

## Measured

The statement-only closure of the wide sample (4,778 theorems of 16 libraries; run 44949277153), by the sum over units of the terms below each unit's own declarations:

| | units | constants | terms | foundation units | a session (median / largest), units | a session, terms |
|---|---:|---:|---:|---:|---:|---:|
| full closure | 193,851 | 199,693 | 86.7 M | 93,512 | 64,020 / 118,110 | 18.1 M / 44.3 M |
| theorems as axioms | 41,483 (21 %) | 45,494 (23 %) | 5.1 M (6 %) | 12,913 (14 %) | 7,607 / 17,709 | 0.72 M / 2.40 M |

Opaque constants stubbed too changes nothing (41,419 units). The terms are per-unit sums (a term shared by two units counts twice): a measure of size, not the size of the export.

The same question for Lean core alone, from the exports themselves (workflow `export-statements`, run 44951869407, `Init` exported both ways): the full export is 6,483,244 lines and 347 MB (59,591 declarations, 6.13 M terms); with `--statements` 1,008,897 lines and 59 MB (46,473 declarations, 0.83 M terms), 15.6 % of the lines and 13.5 % of the terms.

**The exporter shares terms up to binder names and binder info.** `lean4export` writes a term once, with the binder names and annotations of the first alpha-equivalent term it met (Lean's `Expr.eqv` ignores both), so which names a declaration carries depends on what was visited before it, and leaving the proofs out changes that. The first comparison of the two `Init` exports, which treated names and info as part of a term, reported 3,215 changed declarations for that reason alone; `compare_exports.py` now compares terms up to them and counts the declarations that differ only so (`binder_names_only`). A replay restores the names and annotations of the source from Tengoku's environment (`bi` rows), so the replayed statements are the source's.

## What the first replay of the whole tree refused, and the rule it taught

The whole tree exported as statements (69,255,348 lines, 4.10 GB; workflow `export-statements`, run 44952755442) was refused by the kernel at `Rat.instEncodable`. A minimal export of that one constant, both ways (`statements-repro`, run 44957656258, `Tengoku.Seed.Data.Rat.Encodable`), reproduces it: the two exports agree on every declaration (the stub's type is the theorem's, up to binder names), the full export replays, the statements export is refused. Read from the exports themselves:

* the definition is `Equiv.mk toFun invFun _proof_3 _proof_4` with `toFun`, `invFun` matches over a subtype `{d // 0 < d ∧ n.natAbs.Coprime d}`; `_proof_1 a b c d` is the proof of the conjunction `0 < b ∧ Coprime ..`, an auxiliary theorem whose value is `And.intro ..`;
* the declared type of `_proof_3` is `∀ x, invFun (toFun x) = invFun (toFun x)` (the type of the `rfl` that proves it), while the field wants `invFun (toFun x) = x`: the kernel has to reduce `invFun (toFun x)` to `x`, and that means reducing `And.rec` on `_proof_1 ..`, which is a constructor application **only once the theorem is unfolded**. With `_proof_1` an axiom the reduction is stuck and the definition is refused (the kernel, as far as I remember its source, does not eta-expand a structure in `Prop`, so it cannot get past a stuck proof of a conjunction; the evidence here is the refusal and the exports, not a reading of the kernel).

A theorem stood as an axiom can be typed against, rewritten with and applied; it cannot be **computed through**. The rule that follows, in the patch (`lean4export --statements`, v2): **a theorem that the value of a definition or an opaque constant mentions is exported with its proof**, the rest as axioms. It is decided once over the environment (`Expr.getUsedConstants` of every value), without running the kernel, and it is a superset of what the kernel needs (auxiliary proofs of definitions, well-foundedness proofs, instance proofs). The proofs of the kept theorems are not scanned again: what they mention stays a stub, which is enough to type them.

## What it does not say, yet

* **Coverage.** That closure holds what the 4,778 *statements* reach. A base also needs the lemmas of the seed (Mathlib) that no promoted statement mentions: the whole tree has to be exported as statements (the workflow's job), not a sample.
* **Statement ids.** `tengoku-isnad` reads theorems; a statements module has axioms. The comparison with Tengoku's ids needs either an isnad option for axioms (a Tengoku change) or a comparison of types from the exports.
* **Replay.** A definition whose body needs the kernel to unfold a theorem (a reduction through a well-foundedness proof) would not replay with that theorem as an axiom: it fails loudly, and the theorem would have to be kept. How many there are is not known.
* **Proving.** Nothing here says a prover does as well in a statements environment; that is a hypothesis for a campaign.
