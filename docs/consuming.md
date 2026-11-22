# Consuming a Tengai snapshot (a prover environment, Leak)

A snapshot is what the transplant workflow builds with `layers=true` (docs/transplant.md): a **foundation** layer and one layer per **topic**, as built `.olean` files, with a manifest. A prover environment puts it on `LEAN_PATH` next to Lean core and imports the layers it needs. Nothing is compiled on the consumer's side.

Status: the snapshot is a workflow artifact (`transplant-layers-<run id>`, 14 days) today, not a release. Where it is published is the owner's decision and has not been made.

## What it holds

```
manifest.json                    schema 2: pins, every layer (imports, units, constants, theorems, olean size and sha256), the checks of the whole
TengaiData/Foundation.olean      what more than one topic reaches
TengaiData/Topic/<Name>.olean    what one topic reaches; imports the foundation
indexes/shape.jsonl              retrieval: statements by pattern shape (name-blind)
indexes/graph.jsonl              retrieval: what each statement's proofs lean on (name-blind)
indexes/intent.jsonl, docs.jsonl retrieval: the docstrings as an inverted index, BM25 (name-blind)
indexes/names.jsonl              the one file with names: statement id -> theorem names
```

The manifest (`indexes` key) lists every index file with its size and sha256 and the counts the builders wrote. The manifest says what was checked: the replay through Lean's kernel (every layer on its own), an independent kernel (nanoda) over all the layers read back out of the `.olean` files, the statement ids against Tengoku's, the axioms of every promoted theorem (the standard three only), and what a session loads (cold import, paired rounds, against the cap in `perf-budget.toml`).

## Verify and unpack

```bash
python3 tools/release/pack.py verify snapshot-layers.tar.zst --sha256 <sha256 of the archive> --into snapshot
```

It checks the archive hash, that no member lies outside the target directory, that the archive holds exactly the layers the manifest lists, each with the size and sha256 the manifest recorded, and that every layer imports only layers of the manifest. It prints the `LEAN_PATH` entry. The trust is in the hashes, not in where the file came from.

## Use

```bash
LEAN_PATH="snapshot:$(lake env printenv LEAN_PATH)" lake env lean problem.lean
```

`import TengaiData.Foundation` and `import TengaiData.Topic.<Name>` (a topic layer imports the foundation: importing a topic is enough). A session loads the foundation and the topics it imports, not the rest.

To find the layer of a theorem, `python3 tools/release/use.py SNAPSHOT_DIR --theorem Nat.add_comm` (or `--topic aintlib`, several of each) reads `indexes/layers.jsonl` and prints the `import` lines, the layers and the number of constants a session would load, and the `LEAN_PATH` line; `--header FILE` writes the imports to a file a problem can be appended to, `--list-topics` lists the topics. A theorem the index does not know is an error that names the closest names. (Run on the rehearsal snapshot of run 45021032830, the layer of one of aintlib's theorems loads 42,278 constants: the figure of the sessions table.)

## Retrieval indexes

`pack.py verify` unpacks `indexes/` next to the layers and checks each file against the manifest (the files in the folder are exactly the files the manifest lists: a missing, a changed or an extra file is refused). They are plain JSON lines, sorted, deterministic, keyed by **statement id** (Tengoku's `isnad1` id: what a theorem states, not what it is called), so a prover or a scrambler that reads them cannot see a theorem's name. `names.jsonl` is the single exception, for a consumer that has to show a name to a person.

| file | what | use |
| --- | --- | --- |
| `shape.jsonl` | `{"shape": 8 hex, "ids": [...]}` | the cheap prefilter: a goal of this pattern shape may be stated by one of these statements; the full id decides, never the shape |
| `graph.jsonl` | `{"id", "deps": [ids]}` | what each statement's proofs lean on directly (static, over the theorems that state it) |
| `intent.jsonl`, `docs.jsonl` | inverted index and document lengths | words to statements: BM25 over the prose of the docstrings (inline code is dropped, so no identifier is indexed); `python3 tools/index/intent.py search <dir> "words" -k 10` |
| `names.jsonl` | `{"id", "names": [...]}` | statement id to theorem names |

Measured on the wide sample (4,778 theorems of 16 libraries, 17 layers; tenro run 44946576493): the shape and graph indexes cover **82,053 statements** (of 82,657 theorems that have a statement id), in **68,374 shapes** (7,091 of them shared by more than one statement: the prefilter has about 1.2 statements to confirm per shape), with **791,732 dependency edges** (372,151 dependencies are dropped because their statement has no id in the input). The intent index holds **13,413 statements with a docstring** (7,784 distinct tokens); 8,223 documented definitions are counted and not indexed, and 15,705 docstrings belong to declarations outside the snapshot. The files are 40.6 MB (`graph.jsonl` 27.0, `names.jsonl` 7.0, `shape.jsonl` 4.5, `intent.jsonl` 2.5, `docs.jsonl` 0.7), and the packed snapshot is 541,278,580 bytes, about 5.6 MB more than the same layers without them (run 44943029972). Building them took 6 minutes on the runner.

What an index cannot do, stated: the intent index finds a statement by its docstring, so a theorem without a docstring, or one whose docstring is all code, is found by shape only; the docstring of a definition states nothing, so it is counted and not indexed; a query is words, not a formula (the shape index is the formula-side search); the shape is a prefilter with collisions (the stats file counts them), not an answer.

## What is active in a session, and what is not

Carried (`tengai-replay --ext`, tengai ADR-0005): the constants and their proofs, instances (the global ones global, the scoped ones scoped in their namespaces, so `open scoped X` activates them as in Tengoku: Tengai v0.0.20 on, none before), reducibility, classes, projection information, structure information (fields and parents: `p.x` through a parent), and the binder names and annotations of the source.

Not carried: the simp set and every other attribute table (`ext`, `norm_cast`, `elab_as_elim`, ...), notation, macros, elaborators and tactics (they are code, which a replay does not carry), docstrings, the equation lemmas of recursive definitions, and the flat constructor of a structure unless an export names it (structure instance notation `{ x := 1 }` needs it). So a session has Lean core's tactics only (`omega`, `grind`, `simp` with explicit lemmas, `decide`, `exact?`, `apply`, `rw`, ...), no `ring`, `linarith`, `norm_num` or `positivity`. That is invariant I4 (visible, not active) and a consequence of replay, not an oversight.

## Size and latency

Read from the wide layered run (4,778 theorems of 16 libraries, 17 layers, tenro run 44937592081, the numbers of `docs/transplant.md`): the foundation is 500 MB of `.olean`; a session (the foundation and one topic) loads 512 to 904 MB, and the cold import costs +0.043 to +0.072 s over `import Init` (paired medians of 9 rounds, an empty module about 0.21 s); all 17 layers together are 1,626 MB and cost +0.107 s. The cap `C_load` is 0.25 s (`perf-budget.toml`); no session is over it. The same sample measured up to +0.083 s in an earlier run: the runner's noise is about 0.01 s. The snapshot (manifest, 17 layers) is 536 MB packed with zstd -12.

## The statements snapshot (theorems as axioms of their type)

The `export-statements` workflow (`export_run`, `layers_replay`, `pack`; docs/statements.md) builds the same kind of snapshot from the **statements flavor**: every theorem stands as an axiom of its type (its proof is not in it, except the proofs a definition computes through), so that **all the intake** is a base a session can search and apply against, not a proof library. The artifact is `statements-snapshot-<run id>` (30 days), not a release; the first is run 45000625394 (Tengoku at `1d727eb`, 311,773 theorems of 228 libraries, 635,796 constants).

```
manifest.json                    schema 2, flavor "statements": pins, every layer (imports, units, constants, olean size and sha256), what was checked; it lists no theorems
TengaiData/Foundation.olean      what two libraries or more need (78,464 constants)
TengaiData/Topic/<Library>.olean the statements of one library and what only it needs; imports the foundation
indexes/layers.jsonl             {"name", "library", "layer"}: the layer that holds each theorem's statement
indexes/layers-stats.json        the counts and the sha256 of layers.jsonl
legal/ATTRIBUTION.md             where the content comes from (library, repository, commit, licence); only in a snapshot packed with the licence texts
legal/LICENSES/<owner>/<repo>@<commit>/<file>  each library's licence and notice files, byte for byte, with LICENSES/INDEX.json (sizes, sha256, problems)
```

Verify and unpack as above (`pack.py verify`: the 229 layers and the two index files are checked against the manifest). To work on a theorem, look its name up in `indexes/layers.jsonl` and `import` that layer (it imports the foundation): the session loads the foundation and that library, +0.013 s in the middle and **+0.038 s at most** over an empty module (229 sessions measured, paired medians; the cap is 0.25 s); the foundation and the four largest libraries together are +0.099 s, all 229 layers +0.210 s. The archive is 648 MB (`zstd -19 --long=27`), 3.9 GB unpacked.

**What it is for, and not.** A session on it is for search and for applying statements (invariant I1: untrusted search, trusted checking): a theorem there has no proof, so `#print axioms` of anything that uses one lists the theorem itself, and a result found there is **checked in an environment that has the real proofs** (Tengoku's, or a proofs snapshot of the same theorems), never accepted from here. What a definition computes through is kept with its proof (the rule of docs/statements.md), except in a snapshot built with `drop_proofs` (the whole tree), where a definition that only computes through a theorem stands as an axiom of its type if the kernel refuses it (listed in the manifest). It carries the constants. A snapshot built with `ext_rows` (the first, run 45000625394, was not) carries **the extension entries** Lean keeps about them as well (`tengai-replay --ext`, tengai ADR-0005): instances, classes, structure information and projection information, reducibility, and the binder names and annotations of the source, so that a session can resolve `x + y` and read `p.x` through a parent. It carries **no simp set, no notation, no macro, no elaborator and no tactic** (a replay does not carry code: invariant I4, visible but not active; a session has Lean core's tactics only, as the section above says). Instances are registered **global** by default (active as soon as the layer is imported, as in the proofs snapshot) or, with `scoped_instances`, scoped to the namespace of each layer's module, which a session opens to activate them (the reading of invariant I4): the intake's closure has no instance that is scoped in Tengoku (0 of 16,073, run 45019953667), so for it the choice is only one of activation.

**What was checked, and what was not.** The kernel accepted every declaration of every layer (0 refused of 612,257), the manifest's hashes verify, the layers index places 311,773 of 311,773 theorems, and a session from the unpacked copy imported eight layers and `#check`ed 24 theorems. **Faithful to Tengoku:** the records of `tengai-typeinfo --hashes` (kind, hash and size of the type, hash of the value) read in Tengoku's environment and in the snapshot's agree for 635,787 of 635,787 constants (run 45018433715; the hash is Lean's 32 bits: a difference is certain, an agreement very unlikely to be one and not a proof). A snapshot built with `nanoda=true` was also read back out of its `.olean` files, exported again by a lean4export without our patch and accepted by **nanoda**, an independent kernel that shares no code with Lean (a theorem stands as an axiom of its type there, so it checks every other declaration); with `ext_rows`, the extension entries read back by the same tool in the snapshot's environment are compared with Tengoku's; the licence texts and notices of every library, as its repository holds them at the commit it was taken from, are in the archive under `legal/` (`tools/release/licences.py`). docs/statements.md has the measurements. Not checked: a prover on it. It holds the statements the intake's statements reach, not the seed's other lemmas (the whole tree has been exported, planned and partly replayed, not built or checked whole): see docs/statements.md, "What it does not say, yet".

## Not verified

- A prover loop on a snapshot: Leak II (Pantograph over `LEAN_PATH`) and Leak IV (`lake serve`) have not been run on one. The environment fits their model (a prebuilt directory on `LEAN_PATH`, nothing built at request time); it has not been tried.
- Retrieval: Leak I (Loogle over the imported modules) has not been run on a snapshot, and no search over the built indexes by a real consumer has been done. The indexes are built, hashed and shipped (run 44946576493); how well they retrieve (recall on held-out goals) is not measured.
