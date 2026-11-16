# How content moves

```
tengoku (frozen source)  ->  tenro (this repository)  ->  tengai (clean core)
   audited intake              overlay + core/ + harvest        one canonical form, one proof per statement
```

Content moves one way. Nothing in Tenro is imported by Tengai, and Tengoku receives nothing from either (Tengai's `docs/adr/0001-roles-and-flow.md`).

**Into Tenro.**
- `core/` is Tengai at a tag, byte for byte (`core.lock`, `tools/mirror/mirror.py`; invariant I6). It changes only by `mirror.py sync TAG`, or on a hypothesis branch through `hyp/<id>/core.patch`.
- `tengoku.pin` names the Tengoku commit the overlay is built against; its compiled cache is Tengoku's own release asset (`scripts/tengoku-setup.sh`).
- `harvest/` (not built yet) holds kernel-checked partial subgoals from **non-evaluation** intake runs only (invariant I8).

**Inside Tenro.** The overlay, `Tenro/`, is where `anomalous-archangel` (the drip) writes freely: names, modules and statements move, and nothing outside Tenro may depend on a Tenro name staying put. It imports Tengoku (`Tengoku.All`) and itself; the clean core is not imported by the drip's gate, because the proof gate (Leak IV) knows Tengoku only.

**Out of Tenro.** A hypothesis is a branch `hyp/<id>` with `hyp/<id>/manifest.json` (change, metric, expected effect, sample size, fixed before any run) and `hyp/<id>/core.patch`. It is promoted to Tengai only on a net Pareto improvement on held-out problems, as that patch, which a daily dry run keeps applicable to Tengai's main. The promoted theorems are re-proved inside Tengai's own cone; each carries `source_id` and a proof that the canonical statement is equivalent to its source (the promotion lens, ADR-0003). This repository holds no token that could push to Tengoku.
