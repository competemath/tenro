# Labelling the statement groups: a written, rule-based protocol

**Why.** The divergence metric and the foundation list of the tawatur tier (design P3) are calibrated on labelled groups: theorems that state the same thing (same isnad `id`) and are
*alias* (one proof copied or reused), *similar* (related proofs, not alike enough to call one) or *independent*. The 51/11/7 split of 2026-10-04 was never stored, so it cannot be
reproduced. This protocol regenerates the groups and labels them by rules a person can read, so the labels are reproducible and a reviewer sees only the cases the rules cannot settle.

**Input.** One group = every theorem of the tree sharing one isnad `id` (two or more). Each member has `name`, `lib`, `modules`, and the reduced closure from
`tools/closure/closure.py` (`--meta` adds the isnad record). Parameters: `protocol.toml`.

## Rules, applied to every pair in a group, in this order (first match wins)

1. **alias, same chain.** Same `lib` (except a *collection* listed in `protocol.toml`, a library of separately written solutions such as Compfiles, whose members are not one chain); or one theorem's closure contains the other's name (one proof uses the other); or both come from one translated upstream (same `from` source in the
   isnad records).
2. **substance.** A member with fewer than `substance_floor` constants outside the forced layer (Init, Std and Lean by defining module; the three axioms; the constants the statement itself mentions, not their transitive closure, which can swallow a whole proof's footprint)
   cannot be called independent of anything: the pair is *similar*.
3. **alias, shared proof.** Closure Jaccard (after the forced layer and the statement's constants) at least `alias_jaccard_min`.
4. **independent.** Different `lib`, neither closure contains the other's name, Jaccard at most `independent_jaccard_max`.
5. **similar.** Anything else.

**Group label** = the strongest relation that holds for a set of members: *independent* if some pair is independent, else *similar* if some pair is similar, else *alias*. The label of the
group is also stored per pair, because the calibration compares pairs.

## What a person sees

A pair is **borderline** when its Jaccard is within `borderline_margin` of `alias_jaccard_min` or `independent_jaccard_max`, or rule 2 decided it with a member 1 constant under the floor.
A person sees only (a) borderline pairs and (b) every group labelled *independent* (the label that matters most: a false "independent" is the costly error). Their answers go to
`human.jsonl` (`{group, pair, label, reason}`) and override the rule label for that pair only. Alias and clear-similar groups are never sent.

## What this does not claim

The rules decide *proof* relations from closure data; they say nothing about the truth or the faithfulness of a statement. The Jaccard thresholds are initial: the calibration may
move them, and a move is a new `protocol.toml` version with every label recomputed, never an edit of labels.
