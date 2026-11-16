# Tenro

The furnace. Where [Tengai](https://github.com/competemath/tengai)'s clean core is mixed with
[Tengoku](https://github.com/competemath/tengoku)'s audited intake and with verified partial subgoals harvested from prover
runs, and where hypotheses for improving Tengai are formed, built and benchmarked without touching Tengai's history or CI.

```
tengoku (frozen source)  ->  tenro (this repository)  ->  tengai (clean core)
```

Content moves one way only. Nothing here is imported by Tengai; Tengoku receives nothing from here.

## What is here today

- `core/` is Tengai at a tag (`core.lock`; `tools/mirror/mirror.py check` is the I6 test, a daily dry run applies hypothesis patches to Tengai's `main`).
- `Tenro/` (with `anomalous_archangel/`, the drip and its gate) is the overlay: it imports Tengoku and itself, and is where the hypothesis engine writes.
- `tools/` are the instruments of the plan (index below), each with tests and, where it needs Lean, a CI job on a fixture.
- `eval/protocol.md` fixes the evaluation (paired design, exact McNemar, power analysis, margins) before any campaign.
- The state of the five readiness gates is `tools/readiness/report.py` (the `readiness` workflow prints it): **no A/B against Mathlib until all five pass.**

## What it is for (target layout, from Tengai's `docs/design.md`)

| Path | Content |
|---|---|
| `core/` | byte-identical to a Tengai tag (tree-hash checked, identical `lean-toolchain`), or that tag plus named, registered hypothesis patches |
| `intake/` | Tengoku, pinned by commit; its compiled cache is used, nothing is copied |
| `harvest/` | kernel-checked partial subgoals from **non-evaluation** intake runs only |
| `hyp/<id>` | a hypothesis: a branch and a `manifest.json` (change, metric, expected effect, sample size) |
| `eval/` | harness specs, identifier scramblers, the pre-registered protocol (runs and the held-out suite are not here) |
| `tools/` | the instruments, see [docs/tools.md](docs/tools.md) |

A hypothesis is promoted to Tengai only on a net Pareto improvement, as a patch that applies cleanly to Tengai's `main`
(a daily dry run checks that for every live hypothesis).

The design is in [Tengai's `docs/design.md`](https://github.com/competemath/tengai/blob/docs/architecture/docs/design.md)
and its [decisions](https://github.com/competemath/tengai/tree/docs/architecture/docs/adr).

Licence: Apache-2.0 (see `LICENSE`).
