# The invariants and what enforces each

Tengai's `docs/design.md` states eight invariants. This table says, for each, **what checks it today, where, and what is not checked yet**, so nobody has to guess whether an invariant is a rule or a wish.

| | Invariant | Enforced by | Where it runs | Not checked yet |
|---|---|---|---|---|
| I1 | Untrusted search, trusted checking | `tools/soundness/verdict.py`: axiom report (Tengoku's `axiom_scan.py`), vacuity acknowledgements, clean rebuild and probes, with **a missing report counted as a failure**; no `sorryAx`, `Lean.ofReduceBool`, `Lean.ofReduceNat`, `Lean.trustCompiler` in our own namespaces | library only as a tool: `verdict.py` is not yet run by a CI job on real reports (P6 wiring) | the independent `nanoda` re-check is Tengoku's; not wired here |
| I2 | One canonical form, idempotent | Tengai `conventions.toml` + `tengai-canon` (rules: `gt-ge`, `not-eq`, `nat-succ`, `name-theorem`, `name-type`, `global-simp`, `global-instance`), the rule list held equal to the TOML by a test | Tengai CI, job `lean` | there is a checker, **not yet a normaliser**: idempotence of a rewrite is not testable until one exists |
| I3 | Tengai never imports Tengoku | `tools/check_layout.py` (cones, no `import Tengoku`), Tengai has no dependency in its `lakefile.toml` | Tengai CI, job `layout` | |
| I4 | Searchable, not active | canon rules `global-simp` and `global-instance` (the scoped and local forms are not flagged) | Tengai CI | global `notation`/`macro`/`syntax` and global attributes other than `simp` and `instance` |
| I5 | No upstream unfolding | *design only* (irreducible definitions and API lemmas) | | **nothing checks it** |
| I6 | Tenro's `core/` is Tengai, exactly | `tools/mirror/mirror.py check` (git tree id against the tag in `core.lock`, toolchains equal), daily `dry-run` of every `hyp/*/core.patch` against Tengai's `main` | Tenro CI, workflow `mirror` | |
| I7 | Hypotheses are pre-registered | `tools/registry/validate.py hyp`: complete manifest, `eval/protocol.md` must exist and match its hash, patch and mirror hashes, and on a pull request only `status` of a registered manifest may change | Tenro CI, job `registry` | no hypothesis exists yet |
| I8 | Harvest only from non-evaluation intake runs | `tools/registry/validate.py harvest`: `run_kind` must be `intake`, kernel-checked, not in the held-out list (records without the list fail closed); quarantine holds ids only | Tenro CI, job `registry` | the held-out list lives in `tenro-eval` (P5, not created) |

The five readiness gates are one report (`tools/readiness/report.py`, workflow `readiness`); a criterion nobody has measured keeps its gate closed, so "not checked yet" above is never read as "passing".
