"""The closure extractor (tools/closure/closure.py) on synthetic exports written in the format of lean4export 3.1 (the shapes were read from a real export:
tests/test_closure_real.py reads the real one in CI)."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "closure"))
import closure as cl  # noqa: E402


class Builder:
    """lean4export 3.1 lines, written in the order the exporter keeps: every sub-term before the terms that use it"""

    def __init__(self):
        self.lines = [
            {
                "meta": {
                    "exporter": {"name": "lean4export", "version": "3.1.0"},
                    "format": {"version": "3.1.0"},
                    "lean": {"version": "4.34.0-rc2"},
                }
            }
        ]
        self.names: dict[str, int] = {}
        self.nterms = 0

    def name(self, full: str) -> int:
        if full in self.names:
            return self.names[full]
        pre, _, last = full.rpartition(".")
        p = self.name(pre) if pre else 0
        i = len(self.names) + 1
        self.names[full] = i
        self.lines.append({"in": i, "str": {"pre": p, "str": last}})
        return i

    def term(self, **kw) -> int:
        i = self.nterms
        self.nterms += 1
        self.lines.append({"ie": i, **kw})
        return i

    def const(self, full: str) -> int:
        return self.term(const={"name": self.name(full), "us": []})

    def bvar(self, i: int) -> int:
        return self.term(bvar=i)

    def sort(self) -> int:
        return self.term(sort=0)

    def app(self, f: int, x: int) -> int:
        return self.term(app={"fn": f, "arg": x})

    def lam(self, ty: int, body: int) -> int:
        return self.term(lam={"binderInfo": "default", "body": body, "name": self.name("x"), "type": ty})

    def pi(self, ty: int, body: int) -> int:
        return self.term(forallE={"binderInfo": "default", "body": body, "name": self.name("x"), "type": ty})

    def let(self, ty: int, value: int, body: int, nondep: bool = False) -> int:
        return self.term(letE={"body": body, "name": self.name("h"), "nondep": nondep, "type": ty, "value": value})

    def proj(self, struct: int, type_name: str) -> int:
        return self.term(proj={"idx": 0, "struct": struct, "typeName": self.name(type_name)})

    def mdata(self, e: int) -> int:
        return self.term(mdata={"expr": e})

    def decl(self, kind: str, full: str, ty: int, value: int | None = None) -> None:
        n = self.name(full)
        body = {"all": [n], "levelParams": [], "name": n, "type": ty}
        if value is not None:
            body["value"] = value
        self.lines.append({kind: body})

    def write(self, path: Path) -> None:
        path.write_text("".join(json.dumps(o) + "\n" for o in self.lines), encoding="utf-8")


def load(b: Builder) -> cl.Export:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "e.ndjson"
        b.write(p)
        ex = cl.Export()
        ex.read(p)
        return ex


def closure_of(b: Builder, name: str) -> set[str]:
    ex = load(b)
    return set(cl.records(ex, [name], {})[0]["closure"])


def base() -> Builder:
    """the declarations every case uses: a type T, a proposition P with a proof p0 and a second proof p1"""
    b = Builder()
    sort = b.sort()
    b.decl("axiom", "T", sort)
    t = b.const("T")
    b.decl("axiom", "P", t)
    b.decl("axiom", "Q", t)
    b.decl("axiom", "R", t)
    return b


class Transitive(unittest.TestCase):
    def test_a_constant_in_the_value_is_in_the_closure(self):
        b = base()
        t = b.const("T")
        p = b.const("P")
        b.decl("thm", "thm1", t, p)
        self.assertEqual(closure_of(b, "thm1"), {"P", "T"})

    def test_the_closure_goes_through_a_definition(self):
        b = base()
        t = b.const("T")
        b.decl("def", "d", t, b.const("Q"))
        b.decl("thm", "thm1", t, b.const("d"))
        self.assertEqual(closure_of(b, "thm1"), {"d", "Q", "T"})

    def test_the_closure_goes_through_a_theorem_value(self):
        b = base()
        t = b.const("T")
        b.decl("thm", "lemma1", t, b.const("R"))
        b.decl("thm", "thm1", t, b.const("lemma1"))
        self.assertEqual(closure_of(b, "thm1"), {"lemma1", "R", "T"})

    def test_the_theorem_itself_is_not_in_its_closure_unless_asked(self):
        b = base()
        t = b.const("T")
        b.decl("thm", "thm1", t, b.const("P"))
        ex = load(b)
        self.assertNotIn("thm1", cl.records(ex, ["thm1"], {})[0]["closure"])
        self.assertNotIn("thm1", cl.records(ex, ["thm1"], {})[0]["statement_closure"])

    def test_a_projection_reaches_its_structure(self):
        b = base()
        t = b.const("T")
        b.decl("axiom", "S", t)
        b.decl("thm", "thm1", t, b.proj(b.const("P"), "S"))
        self.assertEqual(closure_of(b, "thm1"), {"P", "S", "T"})

    def test_metadata_is_transparent(self):
        b = base()
        t = b.const("T")
        b.decl("thm", "thm1", t, b.mdata(b.const("P")))
        self.assertEqual(closure_of(b, "thm1"), {"P", "T"})

    def test_a_cycle_through_a_declared_name_ends(self):
        b = base()
        t = b.const("T")
        b.decl("def", "loop", t, b.const("loop"))  # a recursive definition names itself
        b.decl("thm", "thm1", t, b.const("loop"))
        self.assertEqual(closure_of(b, "thm1"), {"loop", "T"})


class Reduction(unittest.TestCase):
    """a binder nothing uses disappears with the term bound to it; one that is used keeps everything"""

    def have(self, b: Builder, how: str, value: int, body_uses_var: bool, extra_body: int) -> int:
        t = b.const("T")
        body = b.bvar(0) if body_uses_var else extra_body
        if how == "letE":
            return b.let(t, value, body)
        if how == "nondep":
            return b.let(t, value, body, nondep=True)
        if how == "redex":
            return b.app(b.lam(t, body), value)
        if how == "letFun":
            f = b.const("letFun")
            spine = b.app(b.app(b.app(f, t), t), value)
            return b.app(spine, b.lam(t, body))
        raise AssertionError(how)

    def run_case(self, how: str, used: bool) -> set[str]:
        b = base()
        t = b.const("T")
        value = b.const("Q")  # the bound term mentions Q
        main = b.const("P")  # the body's own term mentions P
        proof = self.have(b, how, value, used, main)
        b.decl("thm", "thm1", t, proof)
        return closure_of(b, "thm1")

    def test_an_unused_binder_is_dropped_in_every_form(self):
        for how in ("letE", "nondep", "redex", "letFun"):
            with self.subTest(how=how):
                self.assertEqual(self.run_case(how, used=False), {"P", "T"}, "Q must be gone")

    def test_a_used_binder_keeps_what_it_binds(self):
        for how in ("letE", "nondep", "redex", "letFun"):
            with self.subTest(how=how):
                # the body is the variable itself: Q stays, P was never there; letFun is the constant a `have` is written with, and it is a real use
                expected = {"Q", "T", "letFun"} if how == "letFun" else {"Q", "T"}
                self.assertEqual(self.run_case(how, used=True), expected)

    def test_a_chain_of_unused_binders_goes_entirely(self):
        # have h1 := Q; have h2 := (uses h1 and R); P : h2 is unused, and once h2 is gone h1 is unused too
        b = base()
        t = b.const("T")
        q, r, p = b.const("Q"), b.const("R"), b.const("P")
        h1 = b.bvar(0)  # inside h2's value: no binder between, so h1 is bvar 0
        h2_value = b.app(r, h1)
        inner = b.let(t, h2_value, p)  # let h2 := R h1 in P: P does not use h2
        outer = b.let(t, q, inner)  # let h1 := Q in (let h2 := ... in P)
        b.decl("thm", "thm1", t, outer)
        self.assertEqual(closure_of(b, "thm1"), {"P", "T"})

    def test_the_chain_stops_where_a_binder_is_used(self):
        b = base()
        t = b.const("T")
        q, r = b.const("Q"), b.const("R")
        h1_in_value = b.bvar(0)
        h2_value = b.app(r, h1_in_value)
        h2_used = b.bvar(0)  # the body of the inner let is h2 itself
        inner = b.let(t, h2_value, h2_used)
        outer = b.let(t, q, inner)
        b.decl("thm", "thm1", t, outer)
        self.assertEqual(closure_of(b, "thm1"), {"Q", "R", "T"})

    def test_a_variable_used_two_binders_down_is_seen(self):
        # fun x => fun y => x : the outer variable is used through the inner lambda (loose bound variable 1)
        b = base()
        t = b.const("T")
        x_in_inner = b.bvar(1)
        inner = b.lam(t, x_in_inner)
        q = b.const("Q")
        redex = b.app(b.lam(t, inner), q)  # (fun x => fun y => x) Q: x is used, so Q stays
        b.decl("thm", "thm1", t, redex)
        self.assertEqual(closure_of(b, "thm1"), {"Q", "T"})

    def test_a_variable_unused_under_two_binders_is_dropped(self):
        b = base()
        t = b.const("T")
        y_only = b.bvar(0)
        inner = b.lam(t, y_only)
        redex = b.app(b.lam(t, inner), b.const("Q"))  # (fun x => fun y => y) Q: x unused
        b.decl("thm", "thm1", t, redex)
        self.assertEqual(closure_of(b, "thm1"), {"T"})

    def test_a_lambda_that_is_not_applied_keeps_its_type(self):
        b = base()
        t = b.const("T")
        q = b.const("Q")
        b.decl("thm", "thm1", t, b.lam(q, b.const("P")))  # fun (x : Q) => P: nobody removes a plain binder
        self.assertEqual(closure_of(b, "thm1"), {"Q", "P", "T"})

    def test_the_type_is_never_reduced_away(self):
        b = base()
        t = b.const("T")
        b.decl("thm", "thm1", b.pi(b.const("Q"), t), b.lam(t, b.const("P")))
        self.assertEqual(closure_of(b, "thm1"), {"Q", "T", "P"})

    def test_padding_with_an_unused_have_changes_nothing(self):
        plain, padded = base(), base()
        for b, pad in ((plain, False), (padded, True)):
            t = b.const("T")
            core = b.const("P")
            proof = b.let(t, b.const("R"), core) if pad else core
            b.decl("thm", "thm1", t, proof)
        self.assertEqual(closure_of(plain, "thm1"), closure_of(padded, "thm1"))

    def test_padding_that_is_applied_is_seen(self):
        b = base()
        t = b.const("T")
        used = b.app(b.const("R"), b.bvar(0))  # the body applies the bound variable to R
        b.decl("thm", "thm1", t, b.let(t, b.const("Q"), used))
        self.assertEqual(closure_of(b, "thm1"), {"Q", "R", "T"})


class Statement(unittest.TestCase):
    def test_the_statement_closure_is_the_closure_of_the_type(self):
        b = base()
        b.decl("def", "d", b.const("T"), b.const("R"))
        b.decl("thm", "thm1", b.const("d"), b.const("P"))  # the statement mentions d, which reaches R
        r = cl.records(load(b), ["thm1"], {})[0]
        self.assertEqual(set(r["statement_closure"]), {"d", "R", "T"})
        self.assertEqual(set(r["closure"]), {"d", "P", "R", "T"})

    def test_equal_statements_share_the_fallback_id(self):
        b = base()
        t = b.const("T")
        b.decl("thm", "a", t, b.const("P"))
        b.decl("thm", "b", t, b.const("Q"))
        ex = load(b)
        a, c = cl.records(ex, ["a"], {})[0], cl.records(ex, ["b"], {})[0]
        self.assertEqual(a["id"], c["id"])
        self.assertTrue(a["id"].startswith("stmt:"))

    def test_the_meta_supplies_id_library_and_module(self):
        b = base()
        b.decl("thm", "thm1", b.const("T"), b.const("P"))
        r = cl.records(load(b), ["thm1"], {"thm1": ("eq.1h0v.s3.abc", "lib-a", "Lib.Mod")})[0]
        self.assertEqual((r["id"], r["lib"], r["modules"]), ("eq.1h0v.s3.abc", "lib-a", {"thm1": "Lib.Mod"}))

    def test_modules_table_fills_the_closure_constants_it_knows(self):
        b = base()
        b.decl("thm", "thm1", b.const("T"), b.const("P"))
        r = cl.records(load(b), ["thm1"], {"thm1": ("i", "l", "Lib.Mod")}, modules={"T": "Init.Prelude", "Other": "Std.X"})[0]
        self.assertEqual(r["modules"], {"T": "Init.Prelude", "thm1": "Lib.Mod"})


class Format(unittest.TestCase):
    def test_a_newer_major_version_is_refused(self):
        b = base()
        b.lines[0]["meta"]["format"]["version"] = "4.0.0"
        with self.assertRaises(SystemExit):
            load(b)

    def test_a_term_out_of_order_is_refused(self):
        b = base()
        b.lines.append({"ie": 99, "sort": 0})
        with self.assertRaises(SystemExit):
            load(b)

    def test_a_term_that_uses_a_later_term_is_refused(self):
        b = base()
        b.lines.append({"ie": b.nterms, "app": {"fn": b.nterms + 1, "arg": 0}})
        with self.assertRaises(SystemExit):
            load(b)

    def test_an_undeclared_name_is_refused(self):
        b = base()
        with self.assertRaises(SystemExit):
            cl.records(load(b), ["nope"], {})

    def test_the_command_line_writes_one_json_line_a_name(self):
        b = base()
        b.decl("thm", "thm1", b.const("T"), b.const("P"))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "e.ndjson"
            b.write(p)
            r = subprocess.run(
                [sys.executable, str(ROOT / "tools" / "closure" / "closure.py"), str(p), "--names", "thm1"], capture_output=True, text=True
            )
        self.assertEqual(r.returncode, 0, r.stderr)
        rows = [json.loads(x) for x in r.stdout.splitlines()]
        self.assertEqual([x["name"] for x in rows], ["thm1"])
        self.assertEqual(set(rows[0]), {"id", "lib", "name", "closure", "statement_closure"})


if __name__ == "__main__":
    unittest.main()
