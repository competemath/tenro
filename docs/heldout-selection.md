# Choosing the held-out problems

The owner delegated the choice (2026-11-20: "just pick what you think is high impact and relevant"), so the held-out problems are chosen by **written rules and a seed**, not by hand: anyone can re-run the selection, and a change of a rule is a visible change of
this file and of `tools/campaign/heldout.py`. The owner may overrule any line.

## What a problem is

A theorem of the tree that a prover is asked to prove again, from its statement, with the theorem itself **removed from the library in every arm** (invariant I8: nothing of a held-out problem is visible to the system under test). Because a statement can live under several
names, a candidate must state something no other record states (`aliases == 0`); otherwise the alias would still be there.

## The three strata (readiness gate 5)

| Stratum | A theorem is in it when | Why it is worth testing |
| --- | --- | --- |
| post-cutoff | its `date` is on or after the model's cutoff | no memorised library helps, so a gain is the library's |
| cross-domain | its dependencies lie in two or more libraries | it needs the union Tengoku makes, which Mathlib alone does not have |
| dependency-ablation | it depends on 2 to 12 other theorems of its own library | the library's lemmas are what the prover has to find |

A theorem is in at most one, chosen in the order above (the scarcest first). Every candidate is non-trivial: at least one hypothesis and at least 32 expression nodes (`size` >= 5), so `rfl` and `simp` one-liners do not count.

Within a stratum the order is the sha256 of `seed + id`: the same candidates and seed give the same problems. No library gets more than 20% of a stratum, so one big library cannot be the benchmark.

## The command

```bash
python3 tools/campaign/heldout.py CANDIDATES.jsonl --cutoff 2026-07-01 --per-stratum 100 --seed tenro-heldout-1 --out SELECTION.json
```

`CANDIDATES.jsonl` is built from `tengoku-isnad` and `tengoku-isnad --deps` over the libraries chosen (the `tengoku-slice` workflow produces the inputs); a line is `{"id", "name", "library", "module", "date", "deps", "hyps", "size", "aliases"}`.
`SELECTION.json` has the ids per stratum, the counts and how many were available (a stratum with too few candidates is reported short and the command exits 3, never padded), the ids to remove from the library in every arm (`exclude`), and the `split_hash` a
campaign registration needs (`campaign.py split-hash`).

## Where the problem texts live

The ids and the statements of the selected problems go to the private `competemath/tenro-eval` (this repository holds ids only, and only in the quarantine list). The selection is **a plan for the first campaign**; a problem used to tune anything moves to the development
split and is replaced (`eval/protocol.md`, section 3).
