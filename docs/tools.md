# The instruments (`tools/`)

Each one reads and writes files, is deterministic where it can be, and has tests (`tests/`). A "CI" column names the workflow that runs it on real Lean.

| Tool | What it does | Design | CI |
|---|---|---|---|
| `closure/closure.py` | the reduced dependency closure of declarations, from a `lean4export` file alone (unused `have`s dropped, so padding cannot change it); `--meta`, `--modules` | ADR-0002 footprint | `closure` |
| `calibration/` | `groups.py` (duplicate-statement groups from the sources' isnad tags; cross-library sample), `run_isnad.py` (`tengoku-isnad` in batches that survive a bad module), `label.py` + `calibration/PROTOCOL.md` (alias / similar / independent by written rules), `summary.py` | P1a, P3 | `calibration` (manual) |
| `index/build.py` | the name-blind indexes: pattern shape and the static dependency graph by statement id (names only in `names.jsonl`) | design "indexes/" | |
| `index/Docs.lean`, `index/intent.py` | the intent index: what a statement is FOR, searchable in words (docstrings by statement id, prose only: code spans and names are dropped; BM25 from the index alone) | design "indexes/ (a) intent" | slice CI builds it twice byte-identical and searches it |
| `perf/` | `perf_profile.py` (cold import, cost per added module), `check_budget.py` + `perf-budget.toml` (absolute caps, lowered only) | gate 1, fix 1 | `perf` |
| `soundness/` | `verdict.py` (one verdict from axioms, vacuity, rebuild, probes; a missing report fails), `Probes.lean` (hypothesis-dropping and counterexample probes), `probe_findings.py` | I1, gate 1 | `probes` |
| `tawatur/admit.py` | admission, eviction (cap 3), status and threshold calibration of alternate routes | ADR-0002 | |
| `lens/lens.py` | lenses on statement ids: inverse, composition, aligned skip blocks (O(log n)), isnad round-trip acceptance with its denominator | ADR-0003, gate 3 | |
| `scramble/scramble.py` | identifier scrambling of the library AND the problems (by component, keyed); `ScrambleNames.lean` lists what Lean owns | fix 2, gate 2 | `scramble` |
| `harness/tamper.py`, `harness/records.py` | the frozen-prefix tamper check and its mutation corpus; the run-record schema, its validator, and the numbers gates 4 and 5 read from it (infra error rate, two-sided validity, arm parity) | gates 4, 5 | `readiness` |
| `registry/validate.py` | hypotheses are registered before they run and only change `status` (I7); harvest comes only from non-evaluation intake runs and non-held-out problems (I8) | I7, I8 | `ci` (`registry`) |
| `mirror/mirror.py` | `core/` equals a Tengai tag by git tree id (I6); the daily dry run | I6 | `mirror` |
| `readiness/` | `gather.py` + `report.py`: the five gates as one report; an unmeasured criterion keeps its gate closed. `DataStats.lean` + `data_stats.py`: lemma and definition counts and structural duplicates (gate 1) | P6 | `readiness` |
| `common/tengoku_isnad.py` | reads Tengoku's isnad output with Tengoku's own `isnad.py` (the recipe is never copied here) | | |

Local development: a minimal Lean is enough for the fixtures (`lake build` in `tools/soundness/fixture` or `tools/scramble/fixture`); the Tengoku tree and Mathlib are never built locally.

## The probes on real code (Lean core's `Init.Data.Nat`, 1,432 theorems; numbers from `tools/soundness/Probes.lean`, produced by the `slice` workflow on every change)

| Probe | Reads | Result |
| --- | --- | --- |
| `unused-hyps` (hypothesis dropping) | the proof term | 754 propositional hypotheses read, **0 unused** (the verdict refuses a probe that reports a count of 0 theorems) |
| `cx-sweep` (counterexample, one hypothesis dropped at a time, values 0..3, at most 512 assignments) | the statement only | 801 candidate generalisations: **70 out of reach** (a binder that is not `Nat`, `Int` or `Bool`), 731 searched, **698 rejected (95.5% of those searched) without a proof attempt**, **16 undecided** (the conclusion was never decidable by evaluation), **17 open with evidence** (the conclusion was decided on at least 2 assignments and held on all: 13 on more than 10) |

The 17 that stay open WITH evidence are the generalisations worth a proof attempt first. The 16 undecided have no evidence either way: a conclusion the probe cannot evaluate (an existential, for instance) is never refuted, so
`exists_eq_add_one_of_ne_zero` with its hypothesis dropped is among them although it is false at `n = 0`; the sweep says so (`undecided`) instead of counting it as support. The earlier count of 33 open mixed the two.
