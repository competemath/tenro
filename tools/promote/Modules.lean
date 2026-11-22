/-
The theorems of a tree by module: the raw material of the topics of a layered snapshot (tools/promote/tree_topics.py).

  lake env lean --run Modules.lean <Module>...     (from the Lake project that holds the modules; prefix match, like Docs.lean)

One line per theorem the modules declare: `{"m": "the.module", "n": ["name", "components"]}`, the module that declares it and the name as an array of components (a string or a number each), so that no escaping of
a name is involved and the name a reader makes by joining the components with dots is the one the export's reader makes. Every theorem is listed, a generated one (`eq_1`, `match_1`, `proof_1`) too: a
constant that no topic reaches is in no layer of the snapshot, so the topics must reach every theorem the snapshot is to hold. The modules are read from the module data of the imported environment, and nothing is computed from
a proof. The count goes to stderr.
-/
import Lean
open Lean

def nameToJson (n : Name) : Json :=
  Json.arr (n.components.toArray.map fun
    | .str _ s => Json.str s
    | .num _ k => toJson k
    | .anonymous => Json.null)

unsafe def main (args : List String) : IO UInt32 := do
  enableInitializersExecution
  if args.isEmpty then
    IO.eprintln "usage: lake env lean --run Modules.lean <Module>..."
    return 2
  initSearchPath (← findSysroot)
  let mods := args.map String.toName
  let env ← importModules (mods.toArray.map fun m => { module := m }) {} (trustLevel := 0) (loadExts := true)
  let mut count := 0
  for i in [0:env.header.moduleNames.size] do
    let m := env.header.moduleNames[i]!
    if !mods.any (·.isPrefixOf m) then continue
    for n in env.header.moduleData[i]!.constNames do
      match env.find? n with
      | some ci =>
        if ci.isTheorem then
          IO.println (Json.mkObj [("m", Json.str m.toString), ("n", nameToJson n)]).compress
          count := count + 1
      | none => pure ()
  IO.eprintln s!"modules: {count} theorems"
  return 0
