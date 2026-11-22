"""export-statements.yml: the `drop_proofs` flag reaches every export of statements, and the manifest cannot say something else than the export did.

Each `run:` step is a shell of its own: a bash array made in one step is empty in the next, and `"${drop[@]}"` over an empty array is no argument at all, so the flag would be dropped without a word (it was, in the first
draft of the tree-mode step). These tests read the real workflow file."""

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "export-statements.yml"
JOB = next(iter(yaml.safe_load(WORKFLOW.read_text())["jobs"].values()))["steps"]
EXPORT_OF_THE_SAMPLE = re.compile(r"lean4export\"\s.*--statements\b.*>\s*\"\$RUNNER_TEMP/(sample|tree)-stmt\.ndjson\"")


def runs():
    for s in JOB:
        if "run" in s:
            yield s.get("name", "?"), s["run"]


def test_a_step_that_expands_the_flag_makes_it_in_the_same_step():
    expanding = [(name, run) for name, run in runs() if '"${drop[@]}"' in run]
    assert expanding, "no step takes the flag: the test reads the wrong file"
    for name, run in expanding:
        assert "drop=(" in run, f"{name!r} expands drop but does not make it: a shell step does not see another step's array"


def test_every_export_of_statements_of_the_sample_or_the_tree_takes_the_flag():
    exports = [(name, run) for name, run in runs() if EXPORT_OF_THE_SAMPLE.search(run.replace("\\\n", " "))]
    assert len(exports) >= 3, [n for n, _ in exports]  # the sample (manifests), the sample (tree) and the tree
    for name, run in exports:
        for line in run.splitlines():
            if "lean4export" in line and "--statements" in line and "-stmt.ndjson" in line:
                assert '"${drop[@]}"' in line, f"{name!r}: this export ignores drop_proofs: {line.strip()[:120]}"


def test_the_flag_is_an_input_with_a_default_that_changes_nothing():
    data = yaml.safe_load(WORKFLOW.read_text())
    triggers = data.get("on") or data.get(True)  # YAML 1.1 reads the key `on` as the boolean true
    assert triggers["workflow_dispatch"]["inputs"]["drop_proofs"]["default"] == "false"


def test_the_export_says_how_it_was_made_and_a_replay_must_agree():
    kept = [(n, r) for n, r in runs() if re.search(r">\s*\"\$RUNNER_TEMP/kept/drop-proofs\.txt\"", r)]
    assert len(kept) == 1, "exactly one step records the flag in the export artifact"
    checked = [(n, r) for n, r in runs() if "drop-proofs.txt" in r and "made=" in r]
    assert len(checked) == 1, "exactly one step compares the export's flag with the run's"
    assert "exit 1" in checked[0][1] and "DROP_PROOFS" in checked[0][1]
    assert "drop-proofs.txt" in checked[0][1] and "echo false" in checked[0][1], "an export from before the flag kept its proofs: false"


def test_the_manifest_pins_the_flag():
    assert any('--pin "drop_proofs=' in r for _, r in runs())


def test_the_extension_rows_are_read_for_every_constant_not_only_the_first_name_of_each_unit():
    # tengai-extinfo looks up the names it is given and expands nothing: the constructors and recursors of an inductive block have binder annotations to restore too
    steps = [(n, r) for n, r in runs() if "tengai-extinfo" in r and "lake env" in r]
    assert len(steps) == 1, [n for n, _ in steps]
    run = steps[0][1]
    assert "layers/*.constants.jsonl" in run and "names.jsonl" not in run.replace("ext-names.jsonl", "")
    assert "ext_partition.py" in run, "every row must belong to a layer, checked in the run that has Tengoku"


def test_a_layer_is_replayed_with_its_own_rows_and_never_with_all_of_them():
    replays = [r for _, r in runs() if '--stub-refused "${args[@]}"' in r and "--tables" in r]
    assert len(replays) == 1
    run = replays[0]
    assert "ext_partition.py" in run
    assert '--ext "$RUNNER_TEMP/ext/$module.ext.jsonl"' in run
    assert '--ext "$RUNNER_TEMP/ext.jsonl"' not in run, "every layer would parse every row"


def test_the_extension_rows_are_kept_with_the_export_and_taken_back_by_a_replay():
    kept = [r for _, r in runs() if 'kept/ext.jsonl.zst"' in r and "zstd -3" in r]
    taken = [r for _, r in runs() if 'kept/ext.jsonl.zst"' in r and "zstd -d" in r]
    assert (len(kept), len(taken)) == (1, 1)


def test_the_extension_input_defaults_to_nothing_changed():
    data = yaml.safe_load(WORKFLOW.read_text())
    triggers = data.get("on") or data.get(True)
    assert triggers["workflow_dispatch"]["inputs"]["ext_rows"]["default"] == "false"


def test_scoped_instances_are_asked_for_only_with_the_extension_entries_only_when_the_input_says_so_and_the_manifest_pins_it():
    data = yaml.safe_load(WORKFLOW.read_text())
    triggers = data.get("on") or data.get(True)
    assert triggers["workflow_dispatch"]["inputs"]["scoped_instances"]["default"] == "false"
    replays = [r for _, r in runs() if '--stub-refused "${args[@]}"' in r and "--tables" in r]
    assert len(replays) == 1
    run = replays[0]
    assert run.count("--scoped-instances") == 1
    block = run[run.index('if [ -s "$RUNNER_TEMP/ext/$module.ext.jsonl" ]; then') :]
    block = block[: block.index("fi\n", block.index("--scoped-instances")) + 2]
    assert '--ext "$RUNNER_TEMP/ext/$module.ext.jsonl"' in block and '[ "$SCOPED_INSTANCES" = true ]' in block, block
    assert any('--pin "scoped_instances=${SCOPED_INSTANCES:-false}"' in r for _, r in runs()), (
        "the manifest says which mode the instances were registered in"
    )
