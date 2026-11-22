/-
The theorems of a tree by module: the raw material of the topics of a layered snapshot (tools/promote/tree_topics.py).

  lake env lean --run Modules.lean [--modules-out FILE] [--prefix P] <Module>...     (from the Lake project that holds the modules)

The modules are imported; the theorems listed are those of the modules whose name has one of the modules named as a prefix (like Docs.lean), or, with `--prefix P`, the prefix P (a tree's aggregate module
`Tengoku.All` is imported, and the prefix `Tengoku` takes every module under it).

One line per theorem the modules declare: `{"m": "the.module", "n": ["name", "components"]}`, the module that declares it and the name as an array of components (a string or a number each), so that no escaping of
a name is involved and the name a reader makes by joining the components with dots is the one the export's reader makes. Every theorem is listed, a generated one (`eq_1`, `match_1`, `proof_1`) too: a
constant that no topic reaches is in no layer of the snapshot, so the topics must reach every theorem the snapshot is to hold. The modules are read from the module data of the imported environment, and nothing is computed from
a proof. The count goes to stderr. `--modules-out FILE` also writes the name of every module of the imported environment (the modules named and everything they import, one per line): what a whole-tree
export that leaves libraries out (tools/promote/tree_roots.py) checks against the libraries it left out, from Lean's own import of the kept roots and not from a reading of the sources.
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
  let (modulesOut, args) := match args with
    | "--modules-out" :: f :: rest => (some f, rest)
    | _ => (none, args)
  let (prefixes, names) := match args with
    | "--prefix" :: p :: rest => ([p.toName], rest)
    | ["--prefix"] => ([], [])
    | _ => ([], args)
  if names.isEmpty then
    IO.eprintln "usage: lake env lean --run Modules.lean [--modules-out FILE] [--prefix P] <Module>..."
    return 2
  initSearchPath (← findSysroot)
  let mods := names.map String.toName
  let prefixes := if prefixes.isEmpty then mods else prefixes
  let env ← importModules (mods.toArray.map fun m => { module := m }) {} (trustLevel := 0) (loadExts := true)
  if let some f := modulesOut then
    IO.FS.writeFile f ("\n".intercalate (env.header.moduleNames.toList.map toString) ++ "\n")
  let mut count := 0
  for i in [0:env.header.moduleNames.size] do
    let m := env.header.moduleNames[i]!
    if !prefixes.any (·.isPrefixOf m) then continue
    for n in env.header.moduleData[i]!.constNames do
      match env.find? n with
      | some ci =>
        if ci.isTheorem then
          IO.println (Json.mkObj [("m", Json.str m.toString), ("n", nameToJson n)]).compress
          count := count + 1
      | none => pure ()
  IO.eprintln s!"modules: {count} theorems"
  return 0
