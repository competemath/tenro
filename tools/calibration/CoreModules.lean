/-
The defining module of every constant of Lean's core (Init, Std, Lean): `name<TAB>module`, one line each, sorted.
The forced layer of the tawatur test judges Lean's core by module (docs/tawatur.md in Tengoku); a constant's name says nothing (`Nat.succ` is in `Init.Prelude`).

  lake env lean --run tools/calibration/CoreModules.lean > core-modules.tsv
-/
import Lean
open Lean

def main : IO Unit := do
  initSearchPath (← findSysroot)
  let env ← importModules #[{ module := `Init }, { module := `Std }, { module := `Lean }] {}
  let mut rows : Array String := #[]
  for (n, _) in env.constants.map₁.toList do
    if let some i := env.getModuleIdxFor? n then
      rows := rows.push s!"{n}\t{env.header.moduleNames[i.toNat]!}"
  for r in rows.qsort (· < ·) do
    IO.println r
