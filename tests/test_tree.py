from pathlib import Path

import pytest

from anomalous_archangel import tree

ROOT = Path(__file__).resolve().parent.parent


def test_the_real_tree_is_mapped():
    tm = tree.scan(ROOT)
    assert {"Tenro.Seed.Gauss", "Tenro.Seed.OddSum", "Tenro.Bridge.GaussOdd"} <= set(tm.modules)
    names = {d.name for m in tm.modules.values() for d in m.decls}
    assert {"Tenro.sum_range_mul_two", "Tenro.sum_range_odd", "Tenro.sum_range_odd_of_gauss"} <= names
    assert tm.tenro_imports("Tenro.Bridge.GaussOdd") == ["Tenro.Seed.Gauss", "Tenro.Seed.OddSum"]
    assert tm.order().index("Tenro.Seed.Gauss") < tm.order().index("Tenro.Bridge.GaussOdd")
    assert tm.closure("Tenro.Seed.Gauss") == ["Tenro.Seed.Gauss"]


def test_the_root_file_lists_every_module():
    """Tenro.lean is generated; this fails when a module is added without regenerating it (python -m anomalous_archangel root)."""
    assert (ROOT / "Tenro.lean").read_text() == tree.root_file(tree.scan(ROOT))


def test_namespaces_sections_and_private_names():
    m = tree.parse_module(
        "Tenro.X",
        "Tenro/X.lean",
        "import Tengoku.All\nnamespace Tenro\nsection S\n/-- doc here -/\ntheorem t : True := trivial\nend S\nprivate def hidden := 1\ntheorem _root_.Nat.mine : True := trivial\nend Tenro\ntheorem outside : True := trivial\n",
    )
    assert [(d.kind, d.name) for d in m.decls] == [
        ("theorem", "Tenro.t"),
        ("def", "Tenro.hidden"),
        ("theorem", "Nat.mine"),
        ("theorem", "outside"),
    ]
    assert m.decls[0].doc == "doc here"


def test_cycles_are_found(tmp_path):
    (tmp_path / "Tenro").mkdir()
    (tmp_path / "Tenro" / "A.lean").write_text("import Tenro.B\n")
    (tmp_path / "Tenro" / "B.lean").write_text("import Tenro.A\n")
    with pytest.raises(ValueError):
        tree.scan(tmp_path).order()


def test_the_digest_is_bounded():
    assert len(tree.scan(ROOT).digest(max_chars=300)) <= 300
