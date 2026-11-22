# The statements flavor: a base for search, not for checking

A snapshot of a promotion (docs/transplant.md, docs/consuming.md) holds every constant that a proof of a promoted theorem reaches, because the kernel checks the proofs again: 183,763 constants and 1.6 GB of `.olean` for 4,778 theorems. A **statements** export keeps each theorem as an **axiom of its type** and does not visit its proof, so everything only the proofs used drops out with them.

## Why this is sound for search (invariant I1)

`exact`, `apply`, `rw`, `simp [lemma]` and the elaboration of a statement use the *type* of a lemma. The proof of a lemma is never unfolded (proof irrelevance), so a lemma that stands as an axiom of its type serves the search. A proof found there is **checked afterwards in an environment that holds the real proofs** (the full snapshot, or Tengoku's own tree): untrusted search, trusted checking.

What it is not: a verified environment. `#print axioms` of a promoted theorem prints the theorem itself. A statements snapshot has to say so in its manifest (`flavor: statements`) and name the Tengoku commit its statements come from, whose independent check is what vouches for the proofs.

## What was built

* `tools/export/lean4export-statements.patch`: `lean4export --statements`, a theorem is written as an `axiom` line (same name, level parameters and type; `isUnsafe` false) and its proof is not visited, **except** a theorem that the value of a definition or an opaque constant mentions, which keeps its proof (the rule below). The exporter prints on stderr how many theorems that is. Nothing else changes.
* `tools/export/compare_exports.py`: two exports of one environment (full, `--statements`) agree on every declaration they share, without trusting the numbering of terms (each declaration is reduced to a digest with every name, level and term resolved): a theorem is an axiom with the same name, level parameters and type; the statements export has no theorem and nothing the full one lacks. 12 tests on synthetic exports; the workflow `export-statements` runs it on `Init` exported both ways before anything else.
* `.github/workflows/export-statements.yml`: the gates, then the wide sample of the transplant runs exported as statements (the same 4,800 roots as the 1.6 GB snapshot: a size to set against it), then the whole tree exported as statements (lines, bytes, time, memory) and, as a probe, each replayed through the kernel by `tengai-replay` (size of the module, what a session loads).
* `tools/export/export_stats.py`: the lines of an export by kind, bytes, zstd size, and the wall time and peak memory of the export from `/usr/bin/time -v`.
* `tools/promote/stmt_closure.py` and the workflow `stmt-closure`: the same question answered from the export of a sample alone.

## Measured

The statement-only closure of the wide sample (4,778 theorems of 16 libraries; run 44949277153), by the sum over units of the terms below each unit's own declarations:

| | units | constants | terms | foundation units | a session (median / largest), units | a session, terms |
|---|---:|---:|---:|---:|---:|---:|
| full closure | 193,851 | 199,693 | 86.7 M | 93,512 | 64,020 / 118,110 | 18.1 M / 44.3 M |
| theorems as axioms | 41,483 (21 %) | 45,494 (23 %) | 5.1 M (6 %) | 12,913 (14 %) | 7,607 / 17,709 | 0.72 M / 2.40 M |

Opaque constants stubbed too changes nothing (41,419 units). The terms are per-unit sums (a term shared by two units counts twice): a measure of size, not the size of the export.

The same question for Lean core alone, from the exports themselves (workflow `export-statements`, run 44951869407, `Init` exported both ways): the full export is 6,483,244 lines and 347 MB (59,591 declarations, 6.13 M terms); with `--statements` 1,008,897 lines and 59 MB (46,473 declarations, 0.83 M terms), 15.6 % of the lines and 13.5 % of the terms.

**The exporter shares terms up to binder names and binder info.** `lean4export` writes a term once, with the binder names and annotations of the first alpha-equivalent term it met (Lean's `Expr.eqv` ignores both), so which names a declaration carries depends on what was visited before it, and leaving the proofs out changes that. The first comparison of the two `Init` exports, which treated names and info as part of a term, reported 3,215 changed declarations for that reason alone; `compare_exports.py` now compares terms up to them and counts the declarations that differ only so (`binder_names_only`). A replay restores the names and annotations of the source from Tengoku's environment (`bi` rows), so the replayed statements are the source's.

### The exports themselves, and a replay (the rule of v2: theorems a definition's value mentions are kept with their proofs)

| | the wide sample (4,800 roots, 16 libraries) | all of the intake (311,857 roots, 31,407 modules) |
|---|---:|---:|
| the export with proofs (the snapshot's) | 44.8 M lines, 2.45 GB | not made |
| theorems as axioms only (v1) | 2.43 M lines, 134 MB | not made |
| **v2**: lines / bytes / zstd -3 | **5.38 M / 292 MB / 48 MB** | **55.0 M / 3.10 GB / 511 MB** |
| v2: terms, names | 5.03 M, 285 k | 51.7 M, 2.67 M |
| v2: axioms, definitions, inductive groups, theorems kept | 15,484, 20,791, 2,011, 20,134 | 351,092, 140,002, 8,034, 118,154 |
| theorems kept in the whole imported environment | 106,089 | 210,432 |
| the exporter: time, peak memory | 57 s, 8.3 GB | 12.5 min, 12.5 GB |
| replay of it (the sample on core v0.0.16, the intake on v0.0.17 with `--stub-refused`; nothing refused in either): time, peak memory | 1 min 59 s, 1.64 GB | **37 min 25 s, 14.3 GB** (612,257 constants added, 5,150 skipped because core holds them, 7,789 inductive groups, 0 refused) |
| the module it builds | **237 MB** (the proofs flavor: 1,626 MB), 55,316 constants | **3.66 GB**, 612,257 constants |
| cold import over an empty module (median of 7) | **+0.007 s** (the proofs flavor: +0.138 s) | **+0.30 s** (0.535 s against 0.233 s) |

The rule costs size (the first version, theorems as axioms only, was 147 MB for the sample, which the kernel then refused at `Rat.instEncodable`): 1.6 times the module, and the exporter's memory is the limit of the approach on a 16 GB runner (12.5 GB for the intake; the whole `Tengoku.All` with this rule would not fit, hence waves: the seed first, the intake on top of it). The replay is near the same limit: 14.3 GB of the runner's 16, in 37 minutes.

**One module of all the intake is over the cap.** The cold-load cap `C_load` is 0.25 s (`perf-budget.toml`, lowered only) and the whole intake as one module costs 0.30 s over an empty session (run 44991509898; minimum to minimum, 0.2305 s to 0.5264 s: +0.296 s). The cost does not grow with the number of constants: 11 times the constants (55,316 to 612,257) and 15 times the bytes cost 44 times the import time (0.125 µs a constant for the sample, 0.49 µs for the intake), so the cap cannot be read off the sample, only measured on what a session loads. The remedy is the one the proofs flavor already uses: a foundation and one layer per library (`tools/promote/layers.py`, `tengai-replay --import` and `--only`), so that a session loads the foundation and its own topic. The next section is that, measured.

## The layered snapshot of all the intake: every session is under the cap

All the intake as statements (the export of run 44996811094: 311,773 theorems of 228 libraries, after the 84 sampled names that are not constants of the tree were taken out; 635,796 constants), with the libraries as topics, planned by `tools/promote/layers.py` (3 min 56 s, 2.47 GB of Python):

| | |
|---|---|
| the foundation: a constant two libraries or more need | 73,784 units, **78,464 constants (12.3 %)** |
| the layer of a library: what only that library needs | smallest 2, median 637, 90th percentile 3,927, largest 72,288 constants (lean-pool); together 557,332 |
| the statement of each theorem | in the layer of its library, **none in the foundation**: the layers index places 311,773 of 311,773 |
| what a library uses of the foundation | 275 to 57,800 units, median 9,527, of 73,784 |

Replayed (run 45000625394, `tengai-replay` v0.0.17): the export is parsed once into 2.59 GB of tables (3 to 3.5 minutes, 12.2 GB in the run that measured it, 44998867847), then each layer is its own process: the foundation 2 min 46 s (3.1 GB), Tauceti 6 min 50 s, NavierStokesEuler 4 min 35 s, OpenaiMath 1 min 51 s, LeanPool 1 min 20 s, the median layer 0.7 s, none over 6.7 GB; 31 minutes for the 229 layers and about 35 with the parse. **Nothing refused**: 0 of 612,257 constants added. A session is the foundation and one library; its cold import over an empty module (paired median of 9 rounds; the empty module took 0.176 s; the cap `C_load` is 0.25 s):

| session | constants loaded | net import |
|---|---:|---:|
| the foundation | 78,464 | +0.017 s |
| the foundation and one library: the 228 of them, minimum / median / 90th percentile | | +0.007 / **+0.013** / +0.016 s |
| the slowest: Tauceti, OpenaiMath, NavierStokesEuler, LeanPool | 145,340 / 140,626 / 134,048 / 150,752 | **+0.038** / +0.033 / +0.031 / +0.030 s |
| the foundation and the four largest libraries together | 335,374 | +0.099 s |
| everything, the 229 layers together | 635,796 (3.9 GB of oleans) | +0.210 s |

**No session is over the cap** (229 measured: the foundation, and the foundation with each library). The snapshot is 3,902,373,416 bytes of `.olean` and **648,240,378 bytes (648 MB) as one archive** (`zstd -19 --long=27`, 9 min 12 s, 648 MB of memory); `pack.py verify` of the archive passed, and a session from the unpacked copy imported eight layers and `#check`ed 24 theorems of the layers index. The manifest (`flavor: statements`) records the pins (the tenro commit that made the export, Tengoku `1d727eb`, the exporter patch's sha256, lean4export `483e011`, the tengai tag) and the 0 refused.

Two things the numbers do not say. "Everything" at +0.210 s is under the cap, but the one-module build of the same content measured +0.30 s in the run above: the two are from different runs on different runners (the empty module took 0.176 s here and 0.233 s there), so this is not a claim that the layered form loads the whole faster. And the snapshot is Tengoku **at the pin** (`1d727eb`, 20 Nov 08:18 UTC), not at the head of the intake since.

## What the first replay of the whole tree refused, and the rule it taught

The whole tree exported as statements (69,255,348 lines, 4.10 GB; workflow `export-statements`, run 44952755442) was refused by the kernel at `Rat.instEncodable`. A minimal export of that one constant, both ways (`statements-repro`, run 44957656258, `Tengoku.Seed.Data.Rat.Encodable`), reproduces it: the two exports agree on every declaration (the stub's type is the theorem's, up to binder names), the full export replays, the statements export is refused. Read from the exports themselves:

* the definition is `Equiv.mk toFun invFun _proof_3 _proof_4` with `toFun`, `invFun` matches over a subtype `{d // 0 < d ∧ n.natAbs.Coprime d}`; `_proof_1 a b c d` is the proof of the conjunction `0 < b ∧ Coprime ..`, an auxiliary theorem whose value is `And.intro ..`;
* the declared type of `_proof_3` is `∀ x, invFun (toFun x) = invFun (toFun x)` (the type of the `rfl` that proves it), while the field wants `invFun (toFun x) = x`: the kernel has to reduce `invFun (toFun x)` to `x`, and that means reducing `And.rec` on `_proof_1 ..`, which is a constructor application **only once the theorem is unfolded**. With `_proof_1` an axiom the reduction is stuck and the definition is refused (the kernel, as far as I remember its source, does not eta-expand a structure in `Prop`, so it cannot get past a stuck proof of a conjunction; the evidence here is the refusal and the exports, not a reading of the kernel).

A theorem stood as an axiom can be typed against, rewritten with and applied; it cannot be **computed through**. The rule that follows, in the patch (`lean4export --statements`, v2): **a theorem that the value of a definition or an opaque constant mentions is exported with its proof**, the rest as axioms. It is decided once over the environment (`Expr.getUsedConstants` of every value), without running the kernel, and it is a superset of what the kernel needs (auxiliary proofs of definitions, well-foundedness proofs, instance proofs). The proofs of the kept theorems are not scanned again: what they mention stays a stub, which is enough to type them.

## What it does not say, yet

* **Coverage.** The snapshot holds what the 311,773 intake statements reach. The seed's other lemma statements, about **650,000** (998,428 axioms in the whole-tree export of run 44952755442 against 351,092 in the all-intake one), are not in it, and a proof uses lemmas that no statement mentions. `layers.py` reads a tree of topics (tenro#101: `Seed/<area>` and `Intake/<library>`, a constant at the lowest node that holds every topic that needs it) and `Modules.lean` with `tree_topics.py` make the topics of a whole tree by module path; none of it has run on the whole tree. Whether its replay fits a 16 GB runner is not known: the parse of the intake alone took 12.2 GB.
* **Faithfulness to Tengoku.** What backs "these are Tengoku's statements" today: `compare_exports.py` between the full and the statements export (Init, the repro modules), the kernel's check of every replayed declaration, and the 30 statement ids that matched in the first proofs-flavor transplant. Not at the scale of the snapshot. `tengai-typeinfo --hashes` (tengai v0.0.18) prints a record a declaration (its kind, the hash and the size of its type, the hash of its value) that Tengoku's environment and the snapshot's can be compared by, whatever the binder names the exporter shared; the comparison over every layer (`tools/promote/faithful.py`) is not run yet. The hash is Lean's 32 bits: a record that agrees makes a difference very unlikely, it does not prove there is none.
* **Statement ids.** `tengoku-isnad` reads theorems; a statements module has axioms, and at the last count (22 Nov) 37 % of the tree's rows had no id in their source. The retrieval indexes keyed by id are not built for this snapshot; the layers index (`indexes/layers.jsonl`: theorem name to the layer that holds it) is.
* **Replay.** A definition whose body needs the kernel to unfold a theorem (a reduction through a well-foundedness proof) does not replay with that theorem as an axiom: it fails loudly, or, with `--stub-refused`, stands as an axiom of its type and is listed. With the rule of v2 none of the 612,257 constants of the intake export was refused (run 44991509898: the probe printed "0 declarations were refused by the kernel"). The seed's other lemmas, the part of the whole tree that no intake statement reaches, have not been replayed.
* **Proving.** Nothing here says a prover does as well in a statements environment; that is a hypothesis for a campaign.
