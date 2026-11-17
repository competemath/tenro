# Evaluation protocol (version 2)

This file is registered **before any campaign** (design fix 5): a hypothesis manifest carries the sha256 of this file (`tools/registry/validate.py hyp`), so a hypothesis cannot be registered
before the protocol exists, and a change to this file makes every earlier registration stale. Runs of provers are the owner's: nothing in this repository runs one.

## 1. What is compared

A **hypothesis** is a registered change to `core/` (a patch), to the overlay, or to the harness settings that a prover sees. The **baseline** is the same tree without it (`core.lock`'s tag).
Both are run on the **same held-out problems** (a paired design), with the same model, the same seeds and the same budget. The held-out set lives in the private `competemath/tenro-eval`
(ids and texts); this repository holds ids only, and only in the quarantine list (`harvest`, I8).

**Outcome per problem and system:** solved (1) or not (0) within the registered budget: the same `k` attempts and the same step/token ceiling for both. Nothing else counts as solved:
the proof must pass the kernel (`tools/soundness/verdict.py`: no `sorryAx`, no `Lean.ofReduceBool`, no vacuity, clean rebuild). **Identifiers are scrambled for both systems** (design fix 2): the
names of library constants *and* the names of problem declarations are replaced by fresh random names, so neither a memorised library nor a memorised problem helps.

## 2. The three quantities and the decision

For a campaign of `n` held-out problems: `b` = problems only the hypothesis solves, `c` = problems only the baseline solves, `psi = (b + c) / n`, `D = (b - c) / n`.

- **Primary (solve rate).** Exact McNemar test (`eval/power.py mcnemar b c`), two-sided, alpha = 0.05 for superiority; one-sided alpha = 0.05 against the margin `-m` for non-inferiority.
- **Secondary (cost).** Median tokens per solved problem and median wall time per solved problem, over problems both systems solved (paired Wilcoxon signed-rank, two-sided, alpha = 0.05).
- **Load (gate 1).** Cold `import Tengai` and the cost per added module against `perf-budget.toml`: an absolute cap, never a ratio to Mathlib.

**Net Pareto improvement (the only way a hypothesis is promoted to Tengai):** the primary is **superior** (D > 0, significant) with every other axis non-inferior within its registered margin, **or** the primary is
**non-inferior** within its margin and at least one other axis (cost or load) is **significantly better**, and the soundness verdict passes in every case. Anything else is rejected or stays unpromoted.

## 3. Sizes, fixed in advance

Alpha = 0.05 (two-sided; one-sided for non-inferiority), power = 0.90. `eval/power.py` is the one definition of the formulas (paired binary outcome, normal approximation of McNemar; the non-inferiority line bounds
the variance by `psi`); `tests/test_eval_power.py` checks them against a simulation and checks that this table is its output. Problems needed, by the discordant fraction `psi`:

| psi (discordant) | gain 0.02 | gain 0.03 | gain 0.05 | margin 0.01 | margin 0.02 |
|---|---|---|---|---|---|
| 0.10 | 2623 | 1164 | 417 | 8564 | 2141 |
| 0.20 | 5250 | 2331 | 837 | 17128 | 4282 |
| 0.30 | 7877 | 3499 | 1257 | 25692 | 6423 |

`psi` is not known until two runs of the **baseline against itself** (different seeds) have been made on the held-out set: that pilot measures the noise floor and `psi`. Until then 0.20 is assumed, and a
campaign registers `sample_size` from the row of the pilot's `psi`, rounded up to the table. **A campaign whose held-out set is smaller than its row is declared underpowered before it starts and cannot promote on
that claim**: it may be run to learn, never to decide. Margins are not below what the held-out set can resolve: with fewer than 4,300 problems no solve-rate margin under 0.02 can be tested (at `psi` = 0.20).

### 3b. What a held-out set of a given size can resolve (the inverse of the table above)

The smallest gain a set of `n` problems detects with power 0.90 and the smallest non-inferiority margin it can test (`eval/power.py resolvable`), by the discordant fraction:

| problems | psi 0.10: gain / margin | psi 0.20: gain / margin | psi 0.30: gain / margin |
|---|---|---|---|
| 500 | 0.046 / 0.042 | 0.065 / 0.059 | 0.080 / 0.072 |
| 1000 | 0.033 / 0.030 | 0.046 / 0.042 | 0.057 / 0.051 |
| 2000 | 0.023 / 0.021 | 0.033 / 0.030 | 0.040 / 0.036 |
| 4300 | 0.016 / 0.015 | 0.023 / 0.020 | 0.028 / 0.025 |

A claim finer than its row is declared underpowered (above). This is the table to read when choosing the size of the held-out set: it is a trade between the finest effect worth a promotion and the cost of curating and running `n` problems.

**Multiplicity.** Hypotheses of one campaign are tested together with the Holm step-down at alpha = 0.05 over the primary tests of the hypotheses in that campaign; a hypothesis tested again on the same held-out
problems after a change is a new hypothesis. A held-out problem used to tune a hypothesis is no longer held out: it moves to the development split, and the held-out list is replaced by problems not seen.

## 4. Discipline

- **No peeking, no stopping rule.** The sample is fixed at registration; results are read once, after all `n` problems and both systems are complete.
- **Registered before it runs.** The manifest (change, metric, expected effect, direction, sample size, margin, protocol hash, patch hash, `core.lock` tree) is committed first; afterwards only `status` may change (I7).
- **Reproducible record.** Every result is keyed by (core tree hash, hypothesis hash, harness hash, model, seeds, held-out split hash) and stores `b`, `c`, `n`, the p-values and the soundness verdict.
- **No contamination (I8).** Nothing from a held-out problem enters the library, the indexes, the harvest or the prover's context; the check runs at harvest time and again at promotion.
- **No Mathlib A/B** until the five readiness gates pass (design P6).

## 5. The held-out set: a staged plan (experimental)

**Chosen on 2026-11-17 on the owner's delegation, while Tengai and Tenro are experimental; the owner may overrule any line.** Curation and the problems themselves stay the owner's: Claude never sees a held-out problem.

- **Stage 0, pilot (learn only, never promotes).** The baseline run twice with different seeds on a pilot set of 300 problems. It measures `psi` (the noise floor); nothing is promoted from it.
- **Stage 1, 1,000 problems in three equal strata** (post-cutoff, dependency-ablation, cross-domain: the strata of readiness gate 5). At `psi` = 0.20 it resolves gains of 0.046 and margins of 0.042, so a Stage 1 campaign registers a non-inferiority margin of at least 0.05 and hopes for large gains only; a finer claim is declared underpowered. This is what the experimental phase can afford.
- **Stage 2, 4,300 problems.** Needed to test a margin of 0.02 (the row of 0.020 / 0.020 at `psi` = 0.20). Required before the owner considers a first release (docs/release-barrier.md in Tengai): no version 1 on Stage 1 evidence.
- **Curation.** The owner selects the problems and the strata; the list of ids is hashed and the hash registered in the first manifest, before the pilot. A problem used to tune anything moves to the development split and is replaced.

## 6. What this protocol does not settle

Who curates and from where (the owner, when `tenro-eval` is created); the model and the budget `k` of a campaign (registered per campaign); the pilot's `psi`. Until they exist the sizes above are a plan, not a measurement.
