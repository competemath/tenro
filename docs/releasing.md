# Publishing a statements snapshot

A snapshot is built as a workflow artifact (`statements-snapshot-<run id>`, 30 days: docs/statements.md, docs/consuming.md). Publishing it makes it a **pre-release** of this repository that anyone can download and verify. Publishing is an act of the owner: the workflow does nothing until it is run with `dry_run=false`, and it is not run without the owner's yes.

## What gates a release

`tools/release/notes.py` refuses (exit status 1, nothing written) unless all of these hold, and there is no option to release without them:

- the manifest is a **statements** snapshot (`flavor: statements`);
- the kernel accepted every layer (`checks.kernel`);
- the comparison with Tengoku's environment **ran and found no problem** (`checks.faithful.ok`: the hash and the size of every type, and of every value that both sides have, agree; docs/statements.md says what the hash can and cannot show);
- **every library has a repository, a commit and a licence** (`attribution.unknown` is empty: a library the registry has no licence for is listed as unknown and blocks the release);
- **the licence texts travel in the archive** (`legal` in the manifest, `legal/` in the tar, verified by `pack.py verify`) and have **no problem** (`legal.problems` is 0: every repository at its commit has a licence file at the root that reads as the licence the registry records; MIT and Apache-2.0 ask for the text and the notices to travel with copies). A snapshot packed before this gate existed has none and cannot be released as it is;
- **if it ran, the independent kernel said ok** (`checks.nanoda.status`: nanoda accepted the layers read back out of their `.olean` files; one that did not run is stated in the notes as unchecked, not refused);
- **if the extension entries were put back** (`checks.extensions`), **Lean refused none** of them and **they were compared** with Tengoku's by the same tool (`checks.ext_faithful`) **without a difference, a loss or an invention** (what Lean core's own constants say, and the instances Tengoku has the other way, are counted and reported, not refused);
- the tag is `snapshot-<name>` (letters, digits, dot, dash, underscore) and **not a version**: the release barrier (`release-guard.toml`, `max_major = 0`) allows no v1 of anything in this repository before the owner's explicit approval, and a snapshot is experimental by definition.

## Leaving libraries out

A library whose licence text is missing at the commit the tree pins blocks the release (the gate above), and the snapshot is one tree: the other libraries are not blocked by it. The export can leave libraries out (`exclude_libraries`, with `sample_mode=tree` and `tree=false`; docs/statements.md): `tools/promote/tree_roots.py` leaves out the libraries asked for **and every library that imports one of them** (a constant a statement reaches is in the export), the kept roots replace `Tengoku.All`, Lean's own list of the modules the kept roots import is checked against what was left out before the export starts, the manifest pins `excluded_libraries`, and the notes print the pins. Which libraries to leave out, and whether to release without them or to move their pins first, is the owner's decision: the snapshot says exactly what it does not hold.

## The workflow

`release-snapshot` (Actions, run by hand, from `main` only):

| input | |
|---|---|
| `run_id` | the id of the `export-statements` run that made `statements-snapshot-<run id>` (with `pack=true`) |
| `tag` | `snapshot-<name>`, for example `snapshot-2026-11-22` |
| `dry_run` | `true` by default |

It downloads the artifact, checks the archive's sha256 against what the run recorded, runs `tools/release/pack.py verify` (every olean against the manifest, every index file and every licence file too), checks that the manifest next to the archive is the one inside it, runs the gates, and writes the notes and `ATTRIBUTION.md`. With `dry_run=true` it stops there and keeps the notes, the attribution and `SHA256SUMS` as an artifact (`release-snapshot-<run id>`): **read them first**. With `dry_run=false` it creates a **pre-release** named after the tag, with `snapshot.tar.zst`, `manifest.json`, `SHA256SUMS`, `ATTRIBUTION.md` and the notes. It has been run once, as a dry run (run 45023865472, on the intake snapshot of run 45018433715: the archive of 648,360,736 bytes verified in CI and the notes were written; under the gates then in force, which did not yet ask for the licence texts).

## What the notes say

What it is (theorems as axioms of their type, constants and, if built with them, the extension entries; invariant I1: results are checked in an environment that has the real proofs), what was checked and what was not (the faithfulness comparison, an independent kernel, the extension entries read back, the sessions under the cap; a prover or a Leak environment on it; the seed's other lemmas), the pins it was made from (the Tengoku commit, the exporter and its patch, the tengai tag, the tenro commit of the export, whether the proofs were dropped and the instances scoped), how to verify and use it, and where the content comes from. The content is other people's libraries: each is under the licence in `ATTRIBUTION.md`, its licence text and notices are in the archive under `legal/LICENSES/`, and they apply to its content.

## Taking a release back

A pre-release can be deleted from the Releases page, or with `gh release delete <tag> --cleanup-tag --repo competemath/tenro` (the release and the tag the workflow created). A copy somebody downloaded is theirs: publish only what you would stand behind.
