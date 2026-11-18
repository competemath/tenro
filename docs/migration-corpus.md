# The real-migration corpus (readiness gate 3)

Gate 3 of ADR-0004 asks for ">= 98% automatic bidirectional lens migration on the real-migration corpus, 100% isnad round trip". The corpus is the library re-cuts Tengoku has actually done: two manifests
(`data/intake/<library>/manifest.jsonl`) at two commits, classified by `tools/lens/reseed.py classify`. Statement ids here are textual (a hash of the statement without its name), a stand-in for the isnad id (the
manifest does not carry it) and stricter than it; the isnad round trip on the same pairs needs the trees built and is the next step.

| Re-cut | Old | New | Survive | Same statement among survivors | Lost |
| --- | --- | --- | --- | --- | --- |
| navier-stokes-euler, first cut to final re-cut (`navier-stokes-euler.json`) | 14,099 theorems, 912 modules | 32,855 | **94.93%** | **100%** (13,384 of 13,384: 13,383 unchanged, 1 renamed, 0 restated, 0 moved) | 715 theorems, in 122 modules; 121 of them vanish whole (695 theorems) |

**What this says about the gate as written.** The re-cut migrated every theorem that survived without touching a statement (fidelity 100%), but it did not keep 5.07% of the old theorems: whole modules were dropped (the re-cut was made
"with the authors' own imports", and modules Gate 2 did not accept were left out). A lens cannot migrate a theorem that no longer exists; it can only report it. So "98% migrated" cannot be one number: **survival** (how much of the old library still exists) is a property of
the re-cut, and **fidelity** (of what survives, how much is the same statement or has a lens entry) is a property of the migration. Against the gate's 98% the corpus gives 100% for fidelity and 94.93% for survival. **Recommendation:** read the gate as fidelity >= 98%
with every removed theorem listed in `names.jsonl` (so a dependent learns what it lost), and report survival beside it as a fact about the re-cut. That is a change to the gate as the owner wrote it, so it is the owner's to accept.

One re-cut is one data point. The other razes in `data/raze/` (lean-pool, openai-math, prismriver, ...) are removals whole or re-intakes of a different shape; Tau Ceti's reseed is the large one still to add.
