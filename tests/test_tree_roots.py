"""tools/promote/tree_roots.py: the root modules of a whole-tree export with libraries left out, and every library that imports one left out too."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "promote"))
import tree_roots as T  # noqa: E402


def write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """the shape of Tengoku: an umbrella root `Tengoku` (the seeded root: `Tengoku.lean` and `Tengoku/Seed/...`; a prefix of every other root), five libraries below it (B imports A, E imports B, D imports C,
    every one imports the seed), a docstring of B that mentions C without importing it, and the aggregate `Tengoku/All.lean`, which imports everything on purpose"""
    write(
        tmp_path,
        "Tengoku/All.lean",
        "-- Everything in the tree.\nimport Tengoku\nimport Tengoku.A\nimport Tengoku.B\nimport Tengoku.C\nimport Tengoku.D\nimport Tengoku.E\n",
    )
    write(tmp_path, "Tengoku.lean", "import Tengoku.Seed.Core\n")
    write(tmp_path, "Tengoku/Seed/Core.lean", "import Mathlib.Algebra.Group.Basic\n\ntheorem seed_core : True := trivial\n")
    write(tmp_path, "Tengoku/A.lean", "import Tengoku.A.Core\n")
    write(tmp_path, "Tengoku/A/Core.lean", "import Tengoku.Seed.Core\n\ntheorem a_core : True := trivial\n")
    write(tmp_path, "Tengoku/B.lean", "import Tengoku.B.Main\n")
    write(
        tmp_path,
        "Tengoku/B/Main.lean",
        "/-! This file used to `import Tengoku.C`, it no longer does. -/\nimport Tengoku.Seed.Core\nimport Tengoku.A.Core\n\ntheorem b_main : True := trivial\n",
    )
    write(tmp_path, "Tengoku/C.lean", "import Tengoku.Seed.Core\n\ntheorem c_root : True := trivial\n")
    write(tmp_path, "Tengoku/D.lean", "import Tengoku.C\n")
    write(tmp_path, "Tengoku/E.lean", "public import Tengoku.B\n")
    return tmp_path


ROOTS = ["Tengoku", "Tengoku.A", "Tengoku.B", "Tengoku.C", "Tengoku.D", "Tengoku.E"]


def run(tree: Path, exclude: str = "") -> tuple[list[str], dict]:
    roots, report = tree / "roots.txt", tree / "report.json"
    assert T.main(["--tree", str(tree), "--exclude", exclude, "--roots-out", str(roots), "--report", str(report)]) == 0
    return roots.read_text().split(), json.loads(report.read_text())


def test_nothing_excluded_is_the_aggregate_itself(tree):
    roots, report = run(tree)
    assert roots == ["Tengoku.All"]  # the export is then the one it always was
    assert report["excluded"] == [] and report["kept"] == 6 and report["requested"] == []


def test_a_library_that_imports_an_excluded_one_is_excluded_with_it_and_so_on_down_the_chain(tree):
    roots, report = run(tree, "Tengoku.A")
    assert roots == ["Tengoku", "Tengoku.C", "Tengoku.D"], "the umbrella (the seed) stays: nothing in it imports a library"
    why = {e["root"]: e["why"] for e in report["excluded"]}
    assert why["Tengoku.A"] == "requested"
    assert why["Tengoku.B"] == "imports Tengoku.A (Tengoku/B/Main.lean: Tengoku.A.Core)"
    assert why["Tengoku.E"].startswith("imports Tengoku.B (Tengoku/E.lean: Tengoku.B)")  # the chain: E imports B, B imports A


def test_an_import_in_a_docstring_is_not_an_import(tree):
    roots, report = run(tree, "Tengoku.C")
    assert "Tengoku.B" in roots, "B only mentions C in a docstring: the header is read as Lean reads it"
    assert {e["root"] for e in report["excluded"]} == {"Tengoku.C", "Tengoku.D"}


def test_an_excluded_leaf_takes_nothing_else_with_it(tree):
    roots, _ = run(tree, "Tengoku.E")
    assert roots == ["Tengoku", "Tengoku.A", "Tengoku.B", "Tengoku.C", "Tengoku.D"]


def test_a_name_that_is_not_a_root_is_an_error_not_a_silent_no_op(tree):
    with pytest.raises(SystemExit, match="Tengoku.Typo"):
        run(tree, "Tengoku.A Tengoku.Typo")


def test_excluding_everything_is_refused(tree):
    with pytest.raises(SystemExit, match="every library"):
        run(tree, "Tengoku")  # every library imports the seed, so asking for the seed takes them all


def test_the_postcondition_holds_for_every_choice_of_exclusion(tree):
    """no kept library imports a library that was left out, whatever was asked for"""
    graph = T.import_graph(tree, ROOTS, skip={"Tengoku.All"})
    for ask in (["Tengoku"], ["Tengoku.A"], ["Tengoku.B"], ["Tengoku.C"], ["Tengoku.D"], ["Tengoku.E"], ["Tengoku.B", "Tengoku.D"]):
        result = T.plan(list(graph), graph, ask)
        out = {e["root"] for e in result["excluded"]}
        assert set(ask) <= out
        for root in result["kept"]:
            assert not (set(graph[root]) & out), (ask, root)


def test_a_report_is_written_with_what_was_asked_and_what_it_took(tree):
    _, report = run(tree, "Tengoku.A  Tengoku.A")  # a repeated name counts once
    assert report["requested"] == ["Tengoku.A"] and report["all"] == "Tengoku.All"
    assert report["export_roots"] == ["Tengoku", "Tengoku.C", "Tengoku.D"] and report["roots"] == 6 and report["kept"] == 3


@pytest.mark.parametrize(
    "text, expected",
    [
        ("import A\nimport B.C\n", ["A", "B.C"]),
        ("prelude\nimport Init.Core\n", ["Init.Core"]),
        ("public import A\nmeta import B\nimport all C\nprivate import D\n", ["A", "B", "C", "D"]),
        ("-- a comment\n/- a /- nested -/ block -/\nimport A -- trailing\nimport B\n", ["A", "B"]),
        ("/-! module doc: import Tengoku.X -/\nimport A\n\n/-- doc -/\ntheorem t : True := trivial\nimport NotAnImport\n", ["A"]),
        ("import A\ndef x := 1\nimport Late\n", ["A"]),  # the header ends at the first command
        ("import Tengoku.«Odd».Name\n", ["Tengoku.Odd.Name"]),
        ("", []),
    ],
)
def test_the_header_is_read_as_lean_reads_it(text, expected):
    assert T.header_imports(text)[0] == expected


def test_a_header_longer_than_the_first_read_is_read_whole(tmp_path):
    many = "".join(f"import Tengoku.L{i}.Module\n" for i in range(4000))  # about 100 kB of imports
    write(tmp_path, "Tengoku/Long.lean", many + "theorem t : True := trivial\n")
    assert len(many) > T.HEADER_READ
    assert T.read_imports(tmp_path / "Tengoku" / "Long.lean") == [f"Tengoku.L{i}.Module" for i in range(4000)]


def test_a_file_is_owned_by_the_longest_root_that_is_a_prefix_at_a_dot():
    roots = {"Tengoku.Lana", "Tengoku.LanaBelyi", "Tengoku.Seed"}
    assert T.owner_of("Tengoku.LanaBelyi.Main", roots) == "Tengoku.LanaBelyi"
    assert T.owner_of("Tengoku.Lana.Main", roots) == "Tengoku.Lana"
    assert T.owner_of("Tengoku.LanaBelyiExtra.Main", roots) is None  # a prefix of the string is not a prefix at a dot
    assert T.owner_of("Mathlib.Algebra.Group.Basic", roots) is None


def test_the_environment_of_the_kept_roots_is_checked_against_what_was_left_out(tree):
    """the sources' import graph is one reading; Lean's own import list is the second: a module of a library that was left out in it means the graph missed an import"""
    _, report = run(tree, "Tengoku.A")
    clean = ["Init", "Mathlib.Algebra.Group.Basic", "Tengoku", "Tengoku.Seed.Std.Util.LibraryNote", "Tengoku.C", "Tengoku.D"]
    assert T.check_modules(report, clean) == []
    leaked = clean + ["Tengoku.A.Core", "Tengoku.B.Main", "Tengoku.AExtra.Other"]
    assert T.check_modules(report, leaked) == [
        "Tengoku.A.Core",
        "Tengoku.B.Main",
    ]  # the root or below it at a dot: AExtra is another library


def test_the_check_runs_from_the_command_line_and_refuses_a_leak_and_an_empty_list(tree, capsys):
    run(tree, "Tengoku.A")
    report = str(tree / "report.json")
    ok = tree / "ok.txt"
    ok.write_text("Init\nTengoku.C\nTengoku.D\n")
    assert T.main(["--check-modules", str(ok), "--report", report]) == 0
    assert "none of a library that was left out" in capsys.readouterr().out
    leak = tree / "leak.txt"
    leak.write_text("Init\nTengoku.C\nTengoku.B.Main\n")
    with pytest.raises(SystemExit, match="missed an import"):
        T.main(["--check-modules", str(leak), "--report", report])
    empty = tree / "empty.txt"
    empty.write_text("\n")
    with pytest.raises(SystemExit, match="was not imported"):
        T.main(["--check-modules", str(empty), "--report", report])


def test_with_nothing_left_out_the_check_has_nothing_to_find(tree):
    _, report = run(tree)
    assert T.check_modules(report, ["Tengoku.A.Core", "Tengoku.B.Main"]) == []


def test_an_umbrella_root_owns_only_what_no_library_owns_and_the_aggregate_belongs_to_nobody(tree):
    """the first real run left out 247 libraries: `Tengoku` (the seeded root) is a prefix of every other root, its directory holds the whole tree, and a library's imports were charged to it"""
    graph = T.import_graph(tree, ROOTS, skip={"Tengoku.All"})
    assert graph["Tengoku"] == {}, "the seed imports no library"
    assert set(graph["Tengoku.A"]) == {"Tengoku"} and set(graph["Tengoku.B"]) == {
        "Tengoku",
        "Tengoku.A",
    }  # a library's import of the seed is an edge to the umbrella
    assert set(graph["Tengoku.D"]) == {"Tengoku.C"} and set(graph["Tengoku.E"]) == {"Tengoku.B"}
    unskipped = T.import_graph(tree, ROOTS)  # without `skip`, the aggregate (which imports everything) would be the umbrella's file
    assert set(unskipped["Tengoku"]) == set(ROOTS[1:]), "this is what the skip is for"


def test_the_seed_survives_every_exclusion_of_a_library(tree):
    for lib in ROOTS[1:]:
        roots, report = run(tree, lib)
        assert "Tengoku" in roots, lib
        assert "Tengoku" not in {e["root"] for e in report["excluded"]}, lib
