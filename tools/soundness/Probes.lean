/-
The probes of the soundness wrapper (tools/soundness/verdict.py reads their findings). Run from the Lake project that holds the modules:

  lake env lean --run Probes.lean unused-hyps <Module>...

unused-hyps (the HYPOTHESIS-DROPPING probe): for every theorem of the modules, the hypotheses (binders whose type is a proposition) that the PROOF NEVER USES. A hypothesis the proof term, the
types of the other binders and the conclusion do not mention can be dropped with the same proof: the theorem is then stated more strongly than needed, and the generalised statement is a candidate
(for tenro: deduplicated against `data/` by isnad shape, confirmed by full id). Nothing is searched and nothing is trusted: it reads the proof term. One line a finding:

  unused<TAB><theorem><TAB><module><TAB><binder index from 0><TAB><binder name><TAB><binder type>

Theorems Lean generates or names internally (`_`, `eq_`, `proof_`, `match_`, `sizeOf_`) are not read.
-/
import Lean
open Lean Meta

def okName (n : Name) : Bool :=
  !n.isNum && !(n.isInternal || n.hasMacroScopes) &&
    (let s := n.getString!; !(s.startsWith "eq_" || s.startsWith "proof_" || s.startsWith "match_" || s.startsWith "sizeOf_" || s == "injEq"))

/-- the unused hypotheses of one theorem: (index among all the lambda binders, name, printed type) -/
def unusedHyps (ci : ConstantInfo) : MetaM (Array (Nat × Name × String)) := do
  let some value := (match ci with | .thmInfo t => some t.value | _ => none) | return #[]
  lambdaTelescope value fun xs body => do
    let mut out : Array (Nat × Name × String) := #[]
    let concl ← inferType body
    for h : i in [0:xs.size] do
      let x := xs[i]
      let ty ← inferType x
      unless (← isProp ty) do continue
      let id := x.fvarId!
      if body.containsFVar id || concl.containsFVar id then continue
      -- another binder's type may depend on it (a hypothesis about a proof): then it is not droppable
      let mut dependedOn := false
      for j in [0:xs.size] do
        if j != i && (← inferType xs[j]!).containsFVar id then dependedOn := true
      if dependedOn then continue
      let un ← x.fvarId!.getUserName
      out := out.push (i, (if un.hasMacroScopes then `_ else un), toString (← ppExpr ty))
    return out

def probe (mods : List Name) : CoreM (Array String) := do
  let env ← getEnv
  let mut rows : Array (String × String × String) := #[]
  for (n, ci) in env.constants.toList do
    let .thmInfo _ := ci | continue
    let some idx := env.getModuleIdxFor? n | continue
    let some m := env.header.moduleNames[idx.toNat]? | continue
    if !mods.any (·.isPrefixOf m) || !okName n then continue
    for (i, hn, ty) in (← (unusedHyps ci).run') do
      rows := rows.push (m.toString, n.toString, s!"unused\t{n}\t{m}\t{i}\t{hn}\t{ty.replace "\n" " "}")
  return (rows.qsort fun a b => a.1 < b.1 || (a.1 == b.1 && a.2.1 < b.2.1)).map (·.2.2)

unsafe def main (args : List String) : IO UInt32 := do
  enableInitializersExecution
  match args with
  | "unused-hyps" :: mods@(_ :: _) =>
    initSearchPath (← findSysroot)
    let env ← importModules (mods.toArray.map fun m => { module := m.toName }) {} (trustLevel := 0) (loadExts := true)
    let ctx : Core.Context := { fileName := "<probe>", fileMap := default, maxHeartbeats := 0 }
    let (lines, _) ← (probe (mods.map String.toName)).toIO ctx { env }
    for l in lines do IO.println l
    IO.eprintln s!"probe: {lines.size} unused hypotheses"
    return 0
  | _ =>
    IO.eprintln "usage: lake env lean --run Probes.lean unused-hyps <Module>..."
    return 2
