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

## Retrieval indexes

`pack.py verify` unpacks `indexes/` next to the layers and checks each file against the manifest (the files in the folder are exactly the files the manifest lists: a missing, a changed or an extra file is refused). They are plain JSON lines, sorted, deterministic, keyed by **statement id** (Tengoku's `isnad1` id: what a theorem states, not what it is called), so a prover or a scrambler that reads them cannot see a theorem's name. `names.jsonl` is the single exception, for a consumer that has to show a name to a person.

| file | what | use |
| --- | --- | --- |
| `shape.jsonl` | `{"shape": 8 hex, "ids": [...]}` | the cheap prefilter: a goal of this pattern shape may be stated by one of these statements; the full id decides, never the shape |
| `graph.jsonl` | `{"id", "deps": [ids]}` | what each statement's proofs lean on directly (static, over the theorems that state it) |
| `intent.jsonl`, `docs.jsonl` | inverted index and document lengths | words to statements: BM25 over the prose of the docstrings (inline code is dropped, so no identifier is indexed); `python3 tools/index/intent.py search <dir> "words" -k 10` |
| `names.jsonl` | `{"id", "names": [...]}` | statement id to theorem names |

What an index cannot do, stated: the intent index finds a statement by its docstring, so a theorem without a docstring, or one whose docstring is all code, is found by shape only; the docstring of a definition states nothing, so it is counted and not indexed; a query is words, not a formula (the shape index is the formula-side search); the shape is a prefilter with collisions (the stats file counts them), not an answer.

## What is active in a session, and what is not

Carried (`tengai-replay --ext`, tengai ADR-0005): the constants and their proofs, instances (global), reducibility, classes, projection information, structure information (fields and parents: `p.x` through a parent), and the binder names and annotations of the source.

Not carried: the simp set and every other attribute table (`ext`, `norm_cast`, `elab_as_elim`, ...), notation, macros, elaborators and tactics (they are code, which a replay does not carry), docstrings, the equation lemmas of recursive definitions, and the flat constructor of a structure unless an export names it (structure instance notation `{ x := 1 }` needs it). So a session has Lean core's tactics only (`omega`, `grind`, `simp` with explicit lemmas, `decide`, `exact?`, `apply`, `rw`, ...), no `ring`, `linarith`, `norm_num` or `positivity`. That is invariant I4 (visible, not active) and a consequence of replay, not an oversight.

## Size and latency

Read from the wide layered run (4,778 theorems of 16 libraries, 17 layers, tenro run 44937592081, the numbers of `docs/transplant.md`): the foundation is 500 MB of `.olean`; a session (the foundation and one topic) loads 512 to 904 MB, and the cold import costs +0.043 to +0.072 s over `import Init` (paired medians of 9 rounds, an empty module about 0.21 s); all 17 layers together are 1,626 MB and cost +0.107 s. The cap `C_load` is 0.25 s (`perf-budget.toml`); no session is over it. The same sample measured up to +0.083 s in an earlier run: the runner's noise is about 0.01 s. The snapshot (manifest, 17 layers) is 536 MB packed with zstd -12.

## Not verified

- A prover loop on a snapshot: Leak II (Pantograph over `LEAN_PATH`) and Leak IV (`lake serve`) have not been run on one. The environment fits their model (a prebuilt directory on `LEAN_PATH`, nothing built at request time); it has not been tried.
- Retrieval: Leak I (Loogle over the imported modules) has not been run on a snapshot, and the retrieval indexes of the design (intent, shape, dependency graph) are not built for promoted content yet.
