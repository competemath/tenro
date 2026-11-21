# The statements flavor: a base for search, not for checking

A snapshot of a promotion (docs/transplant.md, docs/consuming.md) holds every constant that a proof of a promoted theorem reaches, because the kernel checks the proofs again: 183,763 constants and 1.6 GB of `.olean` for 4,778 theorems. A **statements** export keeps each theorem as an **axiom of its type** and does not visit its proof, so everything only the proofs used drops out with them.

## Why this is sound for search (invariant I1)

`exact`, `apply`, `rw`, `simp [lemma]` and the elaboration of a statement use the *type* of a lemma. The proof of a lemma is never unfolded (proof irrelevance), so a lemma that stands as an axiom of its type serves the search. A proof found there is **checked afterwards in an environment that holds the real proofs** (the full snapshot, or Tengoku's own tree): untrusted search, trusted checking.

What it is not: a verified environment. `#print axioms` of a promoted theorem prints the theorem itself. A statements snapshot has to say so in its manifest (`flavor: statements`) and name the Tengoku commit its statements come from, whose independent check is what vouches for the proofs.

## What was built

* `tools/export/lean4export-statements.patch`: `lean4export --statements`, a theorem is written as an `axiom` line (same name, level parameters and type; `isUnsafe` false) and its proof is not visited. Nothing else changes.
* `tools/export/compare_exports.py`: two exports of one environment (full, `--statements`) agree on every declaration they share, without trusting the numbering of terms (each declaration is reduced to a digest with every name, level and term resolved): a theorem is an axiom with the same name, level parameters and type; the statements export has no theorem and nothing the full one lacks. 12 tests on synthetic exports; the workflow `export-statements` runs it on `Init` exported both ways before anything else.
* `.github/workflows/export-statements.yml`: the gates, then the whole tree exported as statements (lines, bytes, time, memory) and, as a probe, replayed through the kernel by `tengai-replay` (size of the module, what a session loads).
* `tools/promote/stmt_closure.py` and the workflow `stmt-closure`: the same question answered from the export of a sample alone.

## Measured

The statement-only closure of the wide sample (4,778 theorems of 16 libraries; run 44949277153), by the sum over units of the terms below each unit's own declarations:

| | units | constants | terms | foundation units | a session (median / largest), units | a session, terms |
|---|---:|---:|---:|---:|---:|---:|
| full closure | 193,851 | 199,693 | 86.7 M | 93,512 | 64,020 / 118,110 | 18.1 M / 44.3 M |
| theorems as axioms | 41,483 (21 %) | 45,494 (23 %) | 5.1 M (6 %) | 12,913 (14 %) | 7,607 / 17,709 | 0.72 M / 2.40 M |

Opaque constants stubbed too changes nothing (41,419 units). The terms are per-unit sums (a term shared by two units counts twice): a measure of size, not the size of the export.

## What it does not say, yet

* **Coverage.** That closure holds what the 4,778 *statements* reach. A base also needs the lemmas of the seed (Mathlib) that no promoted statement mentions: the whole tree has to be exported as statements (the workflow's job), not a sample.
* **Statement ids.** `tengoku-isnad` reads theorems; a statements module has axioms. The comparison with Tengoku's ids needs either an isnad option for axioms (a Tengoku change) or a comparison of types from the exports.
* **Replay.** A definition whose body needs the kernel to unfold a theorem (a reduction through a well-foundedness proof) would not replay with that theorem as an axiom: it fails loudly, and the theorem would have to be kept. How many there are is not known.
* **Proving.** Nothing here says a prover does as well in a statements environment; that is a hypothesis for a campaign.
