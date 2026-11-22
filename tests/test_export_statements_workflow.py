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
    steps = [
        (n, r) for n, r in runs() if 'lake env "$GITHUB_WORKSPACE/core/.lake/build/bin/tengai-extinfo"' in r
    ]  # in Tengoku's environment
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


def nanoda_step():
    steps = [(n, r) for n, r in runs() if "nanoda_bin" in r and "nanoda-layers" in r]
    assert len(steps) == 1, [n for n, _ in steps]
    return steps[0][1]


def test_the_independent_kernel_reads_what_an_exporter_without_our_patch_writes_from_the_olean_files():
    run = nanoda_step()
    assert "lean4export-plain" in run and "patch" not in run.replace("our patch", ""), (
        "nothing of ours between the .olean files and the checker"
    )
    assert 'checkout -q "$NANODA_COMMIT"' in run and 'checkout -q "$LEAN4EXPORT_COMMIT"' in run, "both tools at pinned commits"
    assert "layered.ndjson" in run and "layer-order.txt" in run, "every replayed layer is exported"
    exporter_runs = [ln for ln in run.splitlines() if "bin/lean4export" in ln and "layered.ndjson" in ln]
    assert len(exporter_runs) == 1 and "lean4export-plain/.lake/build/bin/lean4export" in exporter_runs[0], exporter_runs
    assert "lean4export/.lake/build/bin/lean4export" not in run, (
        "the patched exporter of the other steps must not be the one the checker is fed from"
    )


def test_the_independent_kernel_has_a_selftest_and_a_control_that_must_stop_and_only_the_real_run_admits_the_stubs():
    run = nanoda_step()
    assert "Empty/export" in run, "the checker works at all"
    # the control: every axiom an error; the export is full of statements that stand as axioms, so a pass means it did not read this export
    assert 'conf "$RUNNER_TEMP/layered.ndjson" false true' in run and "the control passed" in run and "exit 1" in run
    # the real run admits every axiom (the stubs) and still reports a hard error for nothing else
    assert 'conf "$RUNNER_TEMP/layered.ndjson" true false' in run
    assert run.count('conf "$RUNNER_TEMP/layered.ndjson" true') == 1, "only one run admits every axiom"


def test_the_independent_kernel_writes_the_files_the_manifest_reads_and_the_artifact_keeps_them():
    run = nanoda_step()
    manifest = (WORKFLOW.parent.parent.parent / "tools" / "promote" / "manifest.py").read_text()
    for name in ("nanoda-layers.status", "nanoda-layers.out"):
        assert name in run and name in manifest, name
    assert 'echo ok > "$RUNNER_TEMP/nanoda-layers.status"' in run and 'echo FAILED > "$RUNNER_TEMP/nanoda-layers.status"' in run
    assert '> "$RUNNER_TEMP/nanoda-layers.out"' in run, "the manifest counts the declarations from this file"
    upload = [s for s in JOB if "upload-artifact" in s.get("uses", "") and "statements-snapshot" in str(s.get("with", {}).get("name", ""))]
    assert len(upload) == 1 and "nanoda-layers.out" in upload[0]["with"]["path"]


def test_the_independent_kernel_input_defaults_to_nothing_changed():
    data = yaml.safe_load(WORKFLOW.read_text())
    triggers = data.get("on") or data.get(True)
    assert triggers["workflow_dispatch"]["inputs"]["nanoda"]["default"] == "false"
    step = next(s for s in JOB if "nanoda_bin" in s.get("run", "") and "nanoda-layers" in s["run"])
    assert "env.NANODA == 'true'" in step["if"] and "env.LAYERS_REPLAY == 'true'" in step["if"]


def test_the_licence_texts_are_fetched_in_a_step_that_may_fail_and_the_snapshot_is_then_packed_without_them():
    steps = [s for s in JOB if "licences.py" in s.get("run", "")]
    assert len(steps) == 1
    assert steps[0].get("continue-on-error") is True, (
        "a network call must not take the snapshot down with it: the release gate refuses a snapshot without them"
    )
    assert 'attribution.json" --out "$RUNNER_TEMP/legal"' in steps[0]["run"]
    assert (WORKFLOW.parent.parent.parent / "tools" / "release" / "licences.py").is_file()


def test_the_manifest_and_the_archive_both_take_the_licence_texts_when_there_are_some():
    snapshot = [r for _, r in runs() if "manifest.py layers" in r and "pack.py pack" in r]
    assert len(snapshot) == 1
    run = snapshot[0]
    assert 'legal_args=(--legal "$RUNNER_TEMP/legal")' in run and "LICENSES/INDEX.json" in run, "only when the writer left its index"
    for line in (ln for ln in run.splitlines() if "manifest.py layers" in ln or "pack.py pack" in ln):
        assert '"${legal_args[@]}"' in line, line[:100]


def ext_compare_step():
    steps = [s for s in JOB if "ext_compare.py" in s.get("run", "")]
    assert len(steps) == 1
    return steps[0]


def test_the_extension_entries_are_read_back_by_the_same_tool_from_the_snapshot_and_compared_without_ending_the_run():
    step = ext_compare_step()
    run = step["run"]
    assert step.get("continue-on-error") is True, (
        "a difference is recorded and refused by the release gate; a run of an hour does not end on it"
    )
    assert "tengai-extinfo" in run and 'LEAN_PATH="$RUNNER_TEMP/layered:$core_path"' in run, "the snapshot's environment, not Tengoku's"
    assert "replayed-constants.jsonl" in run and "constants.jsonl" in run and "names.jsonl" not in run, (
        "every constant, not the first name of each unit"
    )
    assert "mapfile -t mods" in run
    assert 'mode=global; if [ "$SCOPED_INSTANCES" = true ]; then mode=scoped; fi' in run and '--instances "$mode"' in run
    assert '[ ! -s "$RUNNER_TEMP/ext.jsonl" ]' in run and "exit 0" in run, (
        "an export without extension rows: said, not compared, not failed"
    )


def test_the_extension_comparison_writes_the_file_the_manifest_reads_and_the_artifact_keeps_it():
    run = ext_compare_step()["run"]
    manifest = (WORKFLOW.parent.parent.parent / "tools" / "promote" / "manifest.py").read_text()
    assert '--out "$RUNNER_TEMP/ext-faithful.json"' in run and "ext-faithful.json" in manifest
    upload = [s for s in JOB if "upload-artifact" in s.get("uses", "") and "statements-snapshot" in str(s.get("with", {}).get("name", ""))]
    assert "ext-faithful.json" in upload[0]["with"]["path"]


def run_conf(permit_all: str, error: str) -> dict:
    """the real conf() of the nanoda step, run by bash, and what it writes"""
    import json
    import subprocess

    run = nanoda_step()
    start = run.index("conf() {")
    end = run.index("\n}\n", start) + 3
    out = subprocess.run(
        ["bash", "-c", run[start:end] + f"\nconf /x/layered.ndjson {permit_all} {error}"], capture_output=True, text=True, check=True
    ).stdout
    return json.loads(out)


def test_nanoda_gets_a_configuration_it_accepts_in_each_of_the_three_runs():
    # the rules of the pinned nanoda (src/util.rs, Config::try_from): `unsafe_permit_all_axioms` needs `unpermitted_axiom_hard_error: false` and NO `permitted_axioms` key at all (the first rehearsal of the
    # step was refused: "unsafe_permit_all_axioms && nonempty permitted_axioms list"); without `print_axioms: false` it prints every admitted axiom and reports a pretty printer error
    every = run_conf("true", "false")  # the real run: every axiom admitted (the statements that stand as axioms)
    assert every["unsafe_permit_all_axioms"] is True and every["unpermitted_axiom_hard_error"] is False
    assert "permitted_axioms" not in every
    assert every["print_axioms"] is False and every["print_success_message"] is True
    strict = run_conf("false", "true")  # the control and the selftest: every axiom but the standard ones an error
    assert strict["unsafe_permit_all_axioms"] is False and strict["unpermitted_axiom_hard_error"] is True
    assert (
        "propext" in strict["permitted_axioms"]
        and "Classical.choice" in strict["permitted_axioms"]
        and "Quot.sound" in strict["permitted_axioms"]
    )
    for conf in (every, strict):
        assert conf["export_file_path"] == "/x/layered.ndjson" and conf["use_stdin"] is False and conf["print_axioms"] is False


def test_the_selftest_must_print_the_success_line_the_real_run_is_read_from_and_the_control_must_stop_on_an_axiom():
    run = nanoda_step()
    assert "nanoda-selftest.out" in run and "Checked [0-9]+ declarations with no errors" in run
    assert "the selftest of nanoda did not print the success line" in run
    assert (
        "grep -qi 'axiom'" in run
        and "the control stopped, but not on an axiom" in run
        and 'head -3 "$RUNNER_TEMP/nanoda-control.out"' in run
    )


def test_a_refused_extension_entry_is_kept_with_its_reason_in_the_log_and_the_artifact():
    # the first whole-tree comparison lost 5 instances ("failed": 3 and 2 in two layers) and the reasons, on stderr, went with the file they were redirected to
    replays = [r for _, r in runs() if '--stub-refused "${args[@]}"' in r and "--tables" in r]
    assert len(replays) == 1
    run = replays[0]
    assert '2> "$RUNNER_TEMP/layer-time.txt"' in run, "the replay's stderr is where the reasons are"
    assert ': > "$RUNNER_TEMP/ext-failures.txt"' in run, "an empty file when no layer has a failure, and not the file of an earlier step"
    # a layer without a failure must not end the step: grep exits 1 on no line and the step runs with -e -o pipefail
    assert 'grep \'^ext: \' "$RUNNER_TEMP/layer-time.txt" | sed "s|^|$module |" | tee -a "$RUNNER_TEMP/ext-failures.txt" || true' in run
    upload = [
        s for s in JOB if "upload-artifact" in s.get("uses", "") and str(s.get("with", {}).get("name", "")).startswith("export-statements")
    ]
    assert len(upload) == 1 and "ext-failures.txt" in upload[0]["with"]["path"]


def test_every_layer_says_which_constants_it_added_and_the_comparison_judges_only_those():
    replays = [r for _, r in runs() if '--stub-refused "${args[@]}"' in r and "--tables" in r]
    assert len(replays) == 1
    assert '--added "$RUNNER_TEMP/added/$module.jsonl"' in replays[0] and 'mkdir -p "$RUNNER_TEMP/added"' in replays[0]
    run = ext_compare_step()["run"]
    assert 'cat "$RUNNER_TEMP"/added/*.jsonl > "$RUNNER_TEMP/added-all.jsonl"' in run
    assert '--added "$RUNNER_TEMP/added-all.jsonl"' in run
