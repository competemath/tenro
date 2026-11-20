# Running a campaign (the owner's part, and what the tools check)

Nothing in Tenro runs a prover. A campaign is the owner's runs, recorded in a form the tools can read once (`eval/protocol.md`).

**What the owner provides**
1. **The held-out id list** (private `competemath/tenro-eval`; ids only ever leave it as a hash): one problem id per line, split into the three strata of readiness gate 5 (post-cutoff, dependency-ablation, cross-domain).
   `python3 tools/campaign/campaign.py split-hash IDS.txt` prints the `split` hash.
2. **A registration** `campaign.json` spec (fields in the docstring of `tools/campaign/campaign.py`): the protocol hash (`sha256sum eval/protocol.md`), the split hash, `n`, `psi`, the two arms (same model, turn cap and sample budget in both), and the primary claim
   (superiority with an expected gain, or non-inferiority with a margin). `campaign.py register SPEC.json --out DIR` refuses an incomplete or inconsistent registration and says whether `n` is enough for the claim (otherwise: underpowered, to learn from, never to decide).
   Commit the spec **before** any run.
3. **The runs**: one line per attempt in `RUNS.jsonl` (`tools/harness/records.py` lists the fields; `records.py validate` checks them).

**What the tools then say**
- `campaign.py analyse SPEC.json RUNS.jsonl`: the paired result (`b`, `c`, `n`, `psi`, `D`, exact McNemar p, the primary verdict), or `incomplete` (not every problem has a result in both arms: nothing is computed), `invalid` (more than 1% of the problems have no result: the harness is being measured), `invalid-input` (a malformed run or registration).
- `records.py summarise RUNS.jsonl --out DIR` writes the harness error rate and the two-sided validity that gate 4 reads; `register --out DIR` writes the `campaign.json` that gate 5 reads.

**Not covered yet**: the secondary axes (cost, load) that a net Pareto improvement also needs; `promotable_on_primary_alone` says so in its name.
