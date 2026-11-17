# Proofs about the tools

`proofs/` is a stand-alone Lean project (core only: no Mathlib, no Tengoku, no Tengai) of theorems about the tools Tengai and Tenro depend on. It builds in about a minute (`cd proofs && lake build`), every
warning is an error, and `TenroProofs/Audit.lean` fails the build if any theorem uses an axiom other than `propext`, `Classical.choice` and `Quot.sound` (a `sorry` or `Lean.ofReduceBool` stops it; an empty
project also stops it). CI job `proofs`.

| File | What is proved | About |
| --- | --- | --- |
| `Eviction.lean` | for ANY scoring of triples: the kept triple scores at least as much as each of the four (`evict_optimal`); an admission never lowers the folder's score (`evict_not_worse`); on a tie the folder is unchanged (`evict_stable`); the folder changes only to a triple containing the candidate (`evict_contains_candidate`) | the eviction rule of `tools/tawatur/admit.py` |
| `Lens.lean` | invertible lenses compose to an invertible lens; composition is associative with the identity as unit, so a skip lens (a block composed once) equals the chain step by step (`chain_append`); a chain of invertible lenses is invertible; the acceptance test of a composition follows from the parts | the lens model of ADR-0003, `tools/lens/lens.py` |

**What is not proved.** That the Python implements the model (tests do that); real-number Jaccard arithmetic; the residuals of a split. Not every tool can be proved: what reads Lean's own output (the closure extractor, the
normaliser on real syntax) is checked by tests against real Lean, not by theorems; a proof of an abstract model of the normaliser (idempotent and meaning-preserving on a small expression language) is a candidate
for the next file. Where a tool cannot be proved because it would need a decision procedure that cannot exist (is this proof a copy of that one in general), the tool is calibrated and tested instead, and says so.
