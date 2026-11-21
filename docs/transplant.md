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
| `layers=true` | the same sample promoted as a foundation and a layer per library, and what a session loads of it (below) |

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
