# The transplant: promoting Tengoku theorems into a Tengai module, measured

`.github/workflows/transplant.yml` (manual) takes a seeded sample of Tengoku theorems, exports the whole dependency closure of each with `lean4export`, **replays the export through Lean's kernel** into a built
`.olean` with `core/`'s `tengai-replay` ([ADR-0005](https://github.com/competemath/tengai/blob/main/docs/adr/0005-promotion-by-replay.md)), and checks what came out. It measures; it changes no repository.
The steps and what each one is for:

| Step | What it establishes |
|---|---|
| sample (`tools/promote/pick.py`) | a seeded sample over the libraries of a `candidates` run (`library`, `count`, `seed`, `candidates_run`); the same inputs give the same sample |
| export | the closure of the sample, in `lean4export` format 3.1 (pinned commit, the one Tengoku's independent check uses) |
| `tengai-replay` (two passes with `extensions=true`) | pass 1 finds which constants Lean core did not already hold; `tengai-extinfo` reads what Lean keeps about them outside the kernel in Tengoku's own environment (reducibility, classes, instances, projections, the binder names and annotations the exporter's term sharing replaced); pass 2 replays with all of it. Every declaration goes through `addDecl`: a wrong term is refused (invariant I1) |
| cold import | `import TengaiData.Sample` against an empty module, median of 7: the absolute cap `C_load` of 0.25 s (design fix 1) |
| axioms | `#print axioms` of every theorem of the sample: only `propext`, `Classical.choice`, `Quot.sound` |
| statement ids | the promotion lens: the isnad id of each replayed theorem against Tengoku's (`tools/promote/compare_ids.py`) |
| nanoda | the built module exported again and checked by an independent kernel that shares no code with Lean (I1) |
| manifest, snapshot | what was built, hashed; packed, unpacked and imported again |
| `layers=true` | the same sample promoted as a foundation and a layer per library (the export parsed once, `--save-tables`, each layer replayed from it), what a session loads of it, nanoda over the layers read back from their `.olean` files, the snapshot packed, verified and imported (below) |

## What it found (5,000 theorems of Aintlib, Compfiles and Azurite; run 44898078379, tengai v0.0.12)

* 149,765 constants added, 9,763 already in Lean core, 1,866 inductive groups; replay 14 min 22 s, 7.8 GB. 213,337 declarations re-checked by nanoda (2 min 50 s, 3.2 GB), no error. All 5,000 theorems rest on the standard axioms only.
* Extension entries carried: 9,289 instances, 1,116 classes, 4,025 projections, 10,161 reducibility entries, none refused (with tengai v0.0.11 ten instances were, e.g. `Prod.instMeasurableSpace` and `Finite.of_fintype`, before the binders were restored). `#synth Field Real`, `CommRing Int`, `Monoid Nat` and `Group (Equiv.Perm Nat)` all succeed in the replayed module.
* Cold import (median of 7): 0.2825 s against 0.1993 s for an empty module, so +0.083 s (cap 0.25 s), for one module holding all of it. The olean is 1,263.9 MB (zstd -3: 431.1 MB), the snapshot 417.9 MB. Import time grows with the constants in the module, so one module that grows with the library meets the cap at some tens of thousands of theorems (linear extrapolation, not measured), which is why a promotion is to be a stack of layers.
* **Statement ids: 4,999 of 5,000 equal, 0 different, 0 missing.** Two statements drifted at first (same kind, variables and canonical hash, another hypothesis count or size class, which isnad reads off the expression, not off the statement). Both causes are now known and measured:
  * a binder name or annotation: lean4export writes terms that are equal up to binder names and annotations once, keeping the first, so a replayed type could carry another term's binders (explicit where Tengoku has implicit: another hypothesis count). Fixed in tengai v0.0.12 (`tengai-extinfo` reads the leading binders, `tengai-replay` puts them back before `addDecl`): one of the two drifts is gone.
  * **expression metadata**: `Usa1995P4.gcd_lcm_dvd_prod_gcd`: the source type has two `mdata` nodes (`[mdata borrowed:1 Nat]`, Lean's borrowed-argument annotation), which `lean4export` leaves out unless it is given `--export-mdata`; the replayed type has 105 nodes where the source has 107, which moves it across a size class (`s5` against `s6`); the canonical hash is the same. Run 44902210371 printed it with `tools/promote/typeinfo_diff.py`.
    `mdata` is inert for the kernel and for elaboration, so the lens accepts this drift (`compare_ids.py`: reported, not failed) and **`data/` is keyed by the source id**, with the replayed id recorded when it differs. Exporting with `--export-mdata` would carry the nodes into every proof term as well, which costs space for nothing, so it is not done.

## By layers

`layers=true` (needs `extensions=true` and a candidates run) adds, after the one-module pipeline: `tools/promote/layers.py` plans the layers (each library of the sample is a topic; a constant more than one topic needs goes to the foundation, one topic needs to that topic's layer;
an inductive type with its constructors and recursors is one unit), `tengai-replay --import/--only` replays the foundation and then each topic on top of it, and the cold import is timed for the foundation, each topic, everything, and the one module. Statement ids and axioms are
checked across the layers as for the one module. The result is an artifact `transplant-layers-<run id>` (`layers.json`, `layers-load.md`).

### What it found by layers (the same 5,000 theorems, three topics: Aintlib, Compfiles, Azurite; run 44910275681, tengai v0.0.13)

* **The plan:** 159,528 units (164,007 constants, counting those Lean core already holds): the foundation (what more than one topic reaches) 79,799 units, Aintlib 48,745, Compfiles 17,909, Azurite 13,075. No constant of the foundation depends on a topic layer (checked for every one).
* **Replayed layer by layer, each kernel-checked on its own:** 72,019 + 48,619 + 16,811 + 12,316 = **149,765 constants added, the number the one-module replay adds**. The extension entries add up to the one-module counts too (instances 5,681 + 3,130 + 211 + 267 = 9,289; classes 1,116; projections 4,025; reducibility 10,161; 0 refused).
* **Statements and axioms across the layers:** 4,999 of 5,000 statement ids equal, the one that differs is the `mdata` drift above, 0 different, 0 missing; all 5,000 theorems resolve from the layers and rest on the standard axioms only.
* **Sizes:** olean 402.0 MB (foundation) + 546.0 (Aintlib) + 194.0 (Compfiles) + 178.7 (Azurite) = 1,320.8 MB against 1,263.9 MB for one module (+4.5 %, what each module repeats); zstd -3 138.5 + 184.0 + 65.9 + 60.6 = 449 MB against 431 MB.
* **What a session loads:** the foundation and Aintlib 948 MB (75 % of the one module), with Compfiles 596 MB (47 %), with Azurite 581 MB (46 %). With three topics the foundation is only 30 % of the whole: most of what a library reaches, only that library reaches.
* **Cold import (median of 7, net over an empty module):** Foundation +0.062 s, Azurite +0.071, Compfiles +0.083, Aintlib +0.131, all layers +0.128, the one module +0.171 s. These are not a scaling law: the same one module measured +0.083 s in run 44898078379 (empty module 0.199 s there, 0.239 s here), so the runner's noise is as large as the effect. Read as a bound: roughly 0.13 ms per MB loaded, which reaches the cap `C_load` (0.25 s) at about 1.9 GB loaded.
* **Not done then, done since (below):** the layered modules were not exported and checked by nanoda, and every layer's `tengai-replay` read the whole export again.

### A wide layered run (4,778 theorems of 16 libraries as topics, 17 layers; run 44937592081, tengai v0.0.15)

`manifests=true` samples the intake manifests of the pinned Tengoku (name and module, no isnad pass), `layers_only=true` skips the one-module pipeline, `count=4800`, seed `wide-2`. 22 of the 4,800 sampled names are not constants of the tree (physlib 21, aintlib 1: a manifest name need not be the tree's name)
and are taken out of the sample and counted (`tools/promote/missing.py`).

* **Replayed by layers, each kernel-checked on its own:** 183,763 constants added (the foundation 85,259, the 16 topics the rest), 10,088 already in Lean core, 2,369 inductive groups. Extension entries: 12,979 reducibility, 5,454 projections, **2,167 structures** (the field and parent information of tengai v0.0.14), 1,136 classes,
  10,197 instances, 0 refused.
* **The export is parsed once:** `tengai-replay --save-tables` wrote the parsed export (1,967 MB, 2 min 51 s, 9.4 GB at its peak) and each layer replayed from it (`--tables`). The layers step took **14 min 5 s** including that save; the same sample took 31 min when every layer parsed the export again (run 44926671313: the 15 small layers 1 min 13 s to 1 min 48 s each).
  From the table file the foundation took 3 min 06 s, Aintlib 4 min 14 s and the 15 small layers 5 to 37 s each (3 min 40 s together).
* **What a session loads (paired, 9 rounds; empty module about 0.21 s):** the foundation 499.7 MB, +0.043 s net; a session (the foundation and one topic) 512 to 903.6 MB, at most +0.072 s (Aintlib, the largest topic); all 17 layers 1,626 MB, +0.107 s. The cap `C_load` is 0.25 s: no session is over it.
  An earlier run of the same sample (44926671313) measured +0.055 s, up to +0.083 s and +0.117 s: the runner's noise is about 0.01 s. Compressed (zstd -3) the foundation is 173 MB and all layers about 554 MB.
* **Independent check across the layers:** the layered modules read back out of their `.olean` files, exported (50.2 million lines, 2.75 GB) and checked by nanoda: 248,691 declarations, no error, 2 min 52 s, 3.0 GB.
* **Snapshot:** manifest schema 2 (4,778 theorems), packed (zstd -12: 536 MB), verified (`tools/release/pack.py verify`: hash, members, sizes, imports between layers) and imported from its unpacked copy.
* **Axioms:** all 4,778 theorems resolve from the layers and rest on `propext`, `Classical.choice` and `Quot.sound` only.
* **Duplicates (`compare_ids.py`):** of 4,750 replayed theorems 4,743 distinct statements: 7 statements are stated twice (14 theorems), so 7 theorems (0.15 %) would be redundant under one proof per statement id. A sample of 300 theorems a library says little about the duplicates inside a library: the sample is too thin to meet them.
* **Not compared:** statement ids against Tengoku's (0 of 4,778: a manifest sample carries no source ids; the one-module runs above compare them).
