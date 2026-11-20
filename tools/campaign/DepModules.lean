/-
Which module each declaration of a list lives in: the one fact `candidates.py` needs about the dependencies of a theorem that are not in the library being read.

  lake env lean --run DepModules.lean NAMES.txt <Module>...     (from the Lake project that holds the modules)

NAMES.txt has one declaration name a line; the modules are imported (their imports come with them). One line `name<TAB>module` for every name the environment knows, nothing for the others.
-/
import Lean
open Lean

unsafe def main (args : List String) : IO UInt32 := do
  enableInitializersExecution
  match args with
  | [] | [_] =>
    IO.eprintln "usage: lake env lean --run DepModules.lean NAMES.txt <Module>..."
    return 2
  | file :: mods =>
    initSearchPath (← findSysroot)
    let env ← importModules (mods.toArray.map fun m => { module := m.toName }) {} (trustLevel := 0) (loadExts := true)
    let names ← IO.FS.lines file
    let mut found := 0
    for s in names do
      let n := s.toName
      if let some idx := env.getModuleIdxFor? n then
        if let some m := env.header.moduleNames[idx.toNat]? then
          IO.println s!"{s}\t{m}"
          found := found + 1
    IO.eprintln s!"depmodules: {found} of {names.size} names found"
    return 0
