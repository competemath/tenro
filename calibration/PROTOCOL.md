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

## Labels so far

`human.jsonl` holds the 6 groups the first run (150 sampled groups: 139 alias, 8 similar, 3 independent) sent for a person's judgement. On 2026-11-17 the owner delegated the call to Claude while the whole
programme is experimental; each line says so and the owner may overrule any of them (a change is a new line with the owner's name, never an edit). The one conservative choice: the borderline pair at Jaccard 0.60 stays *alias*.

## Result of the first complete run (2026-11-17, run 44148817353)

`calibration/thresholds.json` holds it. 150 sampled cross-library groups (alias 139, similar 8, independent 3), 211 pairs, with the delegated labels of `human.jsonl`: **197 alias pairs, 5 independent pairs** (the 9 similar pairs carry no constraint).

- **The footprint axis alone separates them.** Every alias pair has footprint distance at most 0.397 and every independent pair at least 0.753, so any threshold `a` in (0.397, 0.753] is feasible; the report gives the region and `a` = 0.57 is its centre (a first-scanned value would sit on the edge).
- **The waypoint axis adds nothing on this sample.** `b` = 0 is the only feasible value: 61 of 197 alias pairs have waypoint distance above 0 (up to 1.0: a copied proof whose `have`s differ is still an alias), and one independent pair has waypoint distance 0 (neither proof has any `have`). Requiring waypoint divergence would call real aliases independent or real independents alias, so until more pairs say otherwise the tawatur rule behaves as footprint-only: **a = 0.57, b = 0**.
- **Limits, stated.** Only 5 independent pairs, 3 groups; the alias label comes largely from rule 1 (same library chain), so the alias side is the larger and easier half. The result narrows nothing about proofs of the same statement inside one library, which the sample did not include. More independent pairs (and the owner's judgement of the delegated ones) are what would move these numbers.

### The census (2026-11-18, run 44177063777): the same answer on the whole population

The tagged tree has only 252 cross-library statement groups, so the second run took all of them (548 theorems, exported in 4 shards): 321 alias pairs, 14 similar, **6 independent** (one more than the sample: the infinitude of primes in an elementary-number-theory library against one of the six proofs in Proofs from THE BOOK, footprint distance 0.897, judged independent on the owner's delegation). Result: **a = 0.57, b = 0**, unchanged; the feasible region is 0.397 < a <= 0.753 as before (the largest alias distance is still 0.397, the smallest independent one 0.753), and `calibration/thresholds.json` is now this run's.

Waypoints, on the census: 106 of the 321 alias pairs have waypoint distance above 0, and 5 of the 6 independent pairs do, so there is a hint of signal (independent proofs tend to have different `have`s) but not a separation: a threshold above 0 would still call a real independent pair (the one whose proofs have no `have` at all) an alias, or real aliases independent. Whether waypoints help is a question for more data than this tree holds (a census of 6 independent pairs is a census), or for same-library pairs, which this population leaves out by rule 1.
