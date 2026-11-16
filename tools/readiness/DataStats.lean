/-
The counts behind gate 1's hygiene criteria: how many lemmas and how many definitions a library has (the brief asks for at most 4 lemmas per definition).

  lake env lean --run DataStats.lean <Module>...     (from the Lake project that holds the modules; prefix match)

lemma       a theorem whose name is the author's (not `eq_*`, `proof_*`, `match_*`, `sizeOf_*`, `injEq`, nothing internal)
definition  a definition (an instance and a structure's projections included, auxiliary and internal ones not), an inductive type or a structure, an opaque constant, an axiom is NOT counted
One JSON line: {"lemmas": n, "definitions": m, "modules": k}. The structural duplicates come from the isnad ids (tools/readiness/data_stats.py), not from here.
-/
import Lean
open Lean

def okName (n : Name) : Bool :=
  !n.isNum && !(n.isInternal || n.hasMacroScopes) &&
    (let s := n.getString!; !(s.startsWith "eq_" || s.startsWith "proof_" || s.startsWith "match_" || s.startsWith "sizeOf_" || s == "injEq"))

unsafe def main (args : List String) : IO UInt32 := do
  enableInitializersExecution
  if args.isEmpty then
    IO.eprintln "usage: lake env lean --run DataStats.lean <Module>..."
    return 2
  initSearchPath (← findSysroot)
  let mods := args.map String.toName
  let env ← importModules (mods.toArray.map fun m => { module := m }) {} (trustLevel := 0) (loadExts := true)
  let mut lemmas := 0
  let mut defs := 0
  let mut seen : Std.HashSet Name := {}
  for (n, ci) in env.constants.toList do
    let some idx := env.getModuleIdxFor? n | continue
    let some m := env.header.moduleNames[idx.toNat]? | continue
    unless mods.any (·.isPrefixOf m) do continue
    seen := seen.insert m
    unless okName n do continue
    match ci with
    | .thmInfo _ => lemmas := lemmas + 1
    | .defnInfo _ | .inductInfo _ | .opaqueInfo _ => defs := defs + 1
    | _ => pure ()
  IO.println s!"\{\"lemmas\": {lemmas}, \"definitions\": {defs}, \"modules\": {seen.size}}"
  return 0
