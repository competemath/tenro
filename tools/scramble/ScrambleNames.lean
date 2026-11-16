/-
The names the scrambler needs from Lean, one `kind<TAB>name` line each (run from the Lake project that holds the library, `lake env lean --run`):

  lib       a declaration of the modules whose top-level name is the first argument (the library and the problem are scrambled)
  core      a declaration of Init, Std or Lean (never scrambled)
  reserved  an identifier-like token of Lean's parser (keywords, tactic and command names: never scrambled)

  lake env lean --run ScrambleNames.lean Fx
-/
import Lean
open Lean

def main (args : List String) : IO Unit := do
  initSearchPath (← findSysroot)
  let top := args.headD "Fx"
  let env ← importModules #[{ module := top.toName }, { module := `Init }, { module := `Std }, { module := `Lean }] {}
  for (n, _) in env.constants.map₁.toList do
    let some i := env.getModuleIdxFor? n | continue
    let root := (env.header.moduleNames[i.toNat]!).getRoot.toString
    if root == top then
      unless n.isInternal || n.hasMacroScopes do IO.println s!"lib\t{n}"
    else if root == "Init" || root == "Std" || root == "Lean" then IO.println s!"core\t{n}"
  for tok in (Parser.getTokenTable env).findPrefix "" do
    if tok.length > 0 && tok.all (fun c => c.isAlphanum || c == '_' || c == '\'') then IO.println s!"reserved\t{tok}"
