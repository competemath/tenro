# The instruments (`tools/`)

Each one reads and writes files, is deterministic where it can be, and has tests (`tests/`). A "CI" column names the workflow that runs it on real Lean.

| Tool | What it does | Design | CI |
|---|---|---|---|
| `closure/closure.py` | the reduced dependency closure of declarations, from a `lean4export` file alone (unused `have`s dropped, so padding cannot change it); `--meta`, `--modules` | ADR-0002 footprint | `closure` |
| `calibration/` | `groups.py` (duplicate-statement groups from the sources' isnad tags; cross-library sample), `run_isnad.py` (`tengoku-isnad` in batches that survive a bad module), `label.py` + `calibration/PROTOCOL.md` (alias / similar / independent by written rules), `summary.py` | P1a, P3 | `calibration` (manual) |
| `index/build.py` | the name-blind indexes: pattern shape and the static dependency graph by statement id (names only in `names.jsonl`) | design "indexes/" | |
| `perf/` | `perf_profile.py` (cold import, cost per added module), `check_budget.py` + `perf-budget.toml` (absolute caps, lowered only) | gate 1, fix 1 | `perf` |
| `soundness/` | `verdict.py` (one verdict from axioms, vacuity, rebuild, probes; a missing report fails), `Probes.lean` (hypothesis-dropping and counterexample probes), `probe_findings.py` | I1, gate 1 | `probes` |
| `tawatur/admit.py` | admission, eviction (cap 3), status and threshold calibration of alternate routes | ADR-0002 | |
| `lens/lens.py` | lenses on statement ids: inverse, composition, aligned skip blocks (O(log n)), isnad round-trip acceptance with its denominator | ADR-0003, gate 3 | |
| `scramble/scramble.py` | identifier scrambling of the library AND the problems (by component, keyed); `ScrambleNames.lean` lists what Lean owns | fix 2, gate 2 | `scramble` |
| `harness/tamper.py` | the frozen-prefix tamper check and its mutation corpus | gate 4 | `readiness` |
| `registry/validate.py` | hypotheses are registered before they run and only change `status` (I7); harvest comes only from non-evaluation intake runs and non-held-out problems (I8) | I7, I8 | `ci` (`registry`) |
| `mirror/mirror.py` | `core/` equals a Tengai tag by git tree id (I6); the daily dry run | I6 | `mirror` |
| `readiness/` | `gather.py` + `report.py`: the five gates as one report; an unmeasured criterion keeps its gate closed. `DataStats.lean` + `data_stats.py`: lemma and definition counts and structural duplicates (gate 1) | P6 | `readiness` |
| `common/tengoku_isnad.py` | reads Tengoku's isnad output with Tengoku's own `isnad.py` (the recipe is never copied here) | | |

Local development: a minimal Lean is enough for the fixtures (`lake build` in `tools/soundness/fixture` or `tools/scramble/fixture`); the Tengoku tree and Mathlib are never built locally.
