/-
The docstrings of a library: the raw material of the `intent` index (tools/index/intent.py).

  lake env lean --run Docs.lean <Module>...     (from the Lake project that holds the modules; prefix match, like DataStats.lean)

One line per documented theorem or definition whose name is the author's: `doc<TAB>name<TAB>module<TAB>kind<TAB>doc text` (kind `thm` or `def`), the text with `\` written `\\`, a tab `\t` and a line break `\n`
so that a line is one record. Only what the author wrote is read: no auxiliary, internal or generated declaration (the same filter as DataStats.lean), and nothing is computed from a proof.
-/
import Lean
open Lean

def okName (n : Name) : Bool :=
  !n.isNum && !(n.isInternal || n.hasMacroScopes) &&
    (let s := n.getString!; !(s.startsWith "eq_" || s.startsWith "proof_" || s.startsWith "match_" || s.startsWith "sizeOf_" || s == "injEq"))

def escape (s : String) : String :=
  s.foldl (fun acc c => match c with
    | '\\' => acc ++ "\\\\"
    | '\t' => acc ++ "\\t"
    | '\n' => acc ++ "\\n"
    | '\r' => acc
    | c => acc.push c) ""

unsafe def main (args : List String) : IO UInt32 := do
  enableInitializersExecution
  if args.isEmpty then
    IO.eprintln "usage: lake env lean --run Docs.lean <Module>..."
    return 2
  initSearchPath (← findSysroot)
  let mods := args.map String.toName
  let env ← importModules (mods.toArray.map fun m => { module := m }) {} (trustLevel := 0) (loadExts := true)
  let mut rows : Array (String × String × String) := #[]
  for (n, ci) in env.constants.toList do
    let some idx := env.getModuleIdxFor? n | continue
    let some m := env.header.moduleNames[idx.toNat]? | continue
    if !mods.any (·.isPrefixOf m) || !okName n then continue
    unless ci.isTheorem || ci.isDefinition do continue
    let some doc ← findDocString? env n (includeBuiltin := false) | continue
    rows := rows.push (n.toString, m.toString, (if ci.isTheorem then "thm" else "def") ++ "\t" ++ escape doc)
  for (n, m, d) in rows.qsort (fun a b => a.1 < b.1) do
    IO.println s!"doc\t{n}\t{m}\t{d}"
  IO.eprintln s!"docs: {rows.size} documented declarations"
  return 0
