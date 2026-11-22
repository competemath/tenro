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
