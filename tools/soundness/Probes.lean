/-
The probes of the soundness wrapper (tools/soundness/verdict.py reads their findings). Run from the Lake project that holds the modules:

  lake env lean --run Probes.lean unused-hyps <Module>...

counterexample <Module> <Theorem> [<index>,...] (the COUNTEREXAMPLE probe): the theorem with the hypotheses at those binder indices dropped, tried on every assignment of small `Nat`/`Int`/`Bool` values
(0..3, -3..3, both booleans) that satisfies the remaining hypotheses; prints `counterexample<TAB>theorem<TAB>dropped<TAB>a=.., b=..` or `none<TAB>theorem<TAB>dropped`. `none` proves nothing (the range is small, other types are skipped);
a counterexample rejects a candidate generalisation without a proof attempt.

cx-sweep <Module>... (the COUNTEREXAMPLE probe over a whole library): for every theorem and every one of its propositional hypotheses, the generalisation with that one hypothesis dropped is tried on the
small values; prints `examined<TAB>theorems<TAB>candidates<TAB>out-of-reach<TAB>searched<TAB>rejected<TAB>undecided` and, per searched candidate, `rejected<TAB>theorem<TAB>index<TAB>values`, or
`open<TAB>theorem<TAB>index<TAB>assignments decided` (no counterexample, and the conclusion was DECIDED on that many assignments: evidence for the generalisation), or `undecided<TAB>theorem<TAB>index` (the conclusion
was never decidable by evaluation, an existential for instance: no evidence either way). The numbers are the answer to "how often is
a false generalisation caught without a proof attempt, and how much of the library is within the probe's reach" (a candidate is out of reach when a remaining binder is not Nat, Int or Bool).

unused-hyps (the HYPOTHESIS-DROPPING probe): for every theorem of the modules, the hypotheses (binders whose type is a proposition) that the PROOF NEVER USES. A hypothesis the proof term, the
types of the other binders and the conclusion do not mention can be dropped with the same proof: the theorem is then stated more strongly than needed, and the generalised statement is a candidate
(for tenro: deduplicated against `data/` by isnad shape, confirmed by full id). Nothing is searched and nothing is trusted: it reads the proof term. One line a finding:

  unused<TAB><theorem><TAB><module><TAB><binder index from 0><TAB><binder name><TAB><binder type>

and first one line `examined<TAB><theorems read><TAB><propositional hypotheses read>`, so that "no findings" can be told from "nothing looked at".

Theorems Lean generates or names internally (`_`, `eq_`, `proof_`, `match_`, `sizeOf_`) are not read.
-/
import Lean
open Lean Meta

def okName (n : Name) : Bool :=
  !n.isNum && !(n.isInternal || n.hasMacroScopes) &&
    (let s := n.getString!; !(s.startsWith "eq_" || s.startsWith "proof_" || s.startsWith "match_" || s.startsWith "sizeOf_" || s == "injEq"))

/-- the unused hypotheses of one theorem: (index among all the lambda binders, name, printed type) -/
def unusedHyps (ci : ConstantInfo) : MetaM (Array (Nat × Name × String) × Nat) := do
  let some value := (match ci with | .thmInfo t => some t.value | _ => none) | return (#[], 0)
  lambdaTelescope value fun xs body => do
    let mut out : Array (Nat × Name × String) := #[]
    let mut props := 0
    let concl ← inferType body
    for h : i in [0:xs.size] do
      let x := xs[i]
      let ty ← inferType x
      unless (← isProp ty) do continue
      props := props + 1
      let id := x.fvarId!
      if body.containsFVar id || concl.containsFVar id then continue
      -- another binder's type may depend on it (a hypothesis about a proof): then it is not droppable
      let mut dependedOn := false
      for j in [0:xs.size] do
        if j != i && (← inferType xs[j]!).containsFVar id then dependedOn := true
      if dependedOn then continue
      let un ← x.fvarId!.getUserName
      out := out.push (i, (if un.hasMacroScopes then `_ else un), toString (← ppExpr ty))
    return (out, props)

/-- is the proposition true? `none` when it cannot be decided by evaluation (no instance, a stuck term) -/
def decideProp (p : Expr) : MetaM (Option Bool) := do
  let some inst ← (try some <$> synthInstance (mkApp (mkConst ``Decidable) p) catch _ => pure none) | return none
  let r ← withDefault <| whnf (mkApp2 (mkConst ``Decidable.decide) p inst)
  if r.isConstOf ``Bool.true then return some true
  else if r.isConstOf ``Bool.false then return some false
  else return none

/-- the small values of a binder's type: `Nat`, `Int` and `Bool` only (anything else: the statement is out of this probe's reach) -/
def smallValues (ty : Expr) (bound : Nat) : MetaM (Option (Array Expr)) := do
  let ty ← whnf ty
  if ty.isConstOf ``Nat then return some ((List.range (bound + 1)).map (fun (i : Nat) => toExpr i)).toArray
  else if ty.isConstOf ``Int then return some ((List.range (2 * bound + 1)).map (fun (i : Nat) => toExpr (Int.ofNat i - Int.ofNat bound))).toArray
  else if ty.isConstOf ``Bool then return some #[toExpr true, toExpr false]
  else return none

/-- all assignments (an array of values per variable), at most `cap` of them -/
def assignments (domains : Array (Array Expr)) (cap : Nat) : Array (Array Expr) := Id.run do
  let mut acc : Array (Array Expr) := #[#[]]
  for d in domains do
    let mut next : Array (Array Expr) := #[]
    for a in acc do
      for v in d do
        if next.size < cap then next := next.push (a.push v)
    acc := next
  return acc

/-- the COUNTEREXAMPLE probe: the theorem's statement with the hypotheses at the binder indices `drop` removed, checked on all assignments of `Nat`/`Int`/`Bool` variables in a small range:
a counterexample is an assignment that satisfies every remaining hypothesis and falsifies the conclusion. A candidate generalisation (a hypothesis dropped) that has one is rejected without a
proof attempt. `none` is "no counterexample found", which proves nothing; a statement with a binder of another type is skipped. -/
def counterexample (ci : ConstantInfo) (drop : List Nat) (bound : Nat) (cap : Nat) : MetaM (Option (Option String × Nat)) :=
  forallTelescope ci.type fun xs concl => do
    let mut vars : Array Expr := #[]
    let mut domains : Array (Array Expr) := #[]
    let mut hyps : Array Expr := #[]
    for i in [0:xs.size] do
      let x := xs[i]!
      let ty ← inferType x
      if drop.contains i then
        unless (← isProp ty) do return none
        continue
      if (← isProp ty) then hyps := hyps.push x
      else
        let some d ← smallValues ty bound | return none
        vars := vars.push x
        domains := domains.push d
    for i in drop do
      let id := (xs[i]!).fvarId!
      if concl.containsFVar id || hyps.any (·.containsFVar id) then return none
    let mut decided := 0
    for vals in assignments domains cap do
      let sub (e : Expr) : Expr := e.replaceFVars vars vals
      let mut ok := true
      for h in hyps do
        match ← decideProp (sub (← inferType h)) with
        | some true => pure ()
        | _ => ok := false
      if !ok then continue
      let verdict ← decideProp (sub concl)
      if verdict.isSome then decided := decided + 1
      if verdict == some false then
        let names ← vars.mapM fun v => do
          let n ← v.fvarId!.getUserName
          pure (if n.hasMacroScopes then `_ else n)
        let shown ← vals.mapM fun v => do pure (toString (← ppExpr v))
        return some (some (", ".intercalate ((names.zip shown).toList.map fun (n, v) => s!"{n}={v}")), decided)
    return some (none, decided)

/-- the findings, and how much the probe LOOKED AT (theorems read, propositional hypotheses read): a probe that found nothing in nothing proves nothing, and the verdict says so -/
def probe (mods : List Name) : CoreM (Array String × Nat × Nat) := do
  let env ← getEnv
  let mut rows : Array (String × String × String) := #[]
  let mut theorems := 0
  let mut hyps := 0
  for (n, ci) in env.constants.toList do
    let .thmInfo _ := ci | continue
    let some idx := env.getModuleIdxFor? n | continue
    let some m := env.header.moduleNames[idx.toNat]? | continue
    if !mods.any (·.isPrefixOf m) || !okName n then continue
    let (found, props) ← (unusedHyps ci).run'
    theorems := theorems + 1
    hyps := hyps + props
    for (i, hn, ty) in found do
      rows := rows.push (m.toString, n.toString, s!"unused\t{n}\t{m}\t{i}\t{hn}\t{ty.replace "\n" " "}")
  return ((rows.qsort fun a b => a.1 < b.1 || (a.1 == b.1 && a.2.1 < b.2.1)).map (·.2.2), theorems, hyps)

/-- the COUNTEREXAMPLE probe over a library: every propositional hypothesis of every theorem dropped on its own (bound 3, at most 512 assignments each).
Returns the rejected candidates as lines and the counts (theorems, candidates, out of reach, searched, rejected). -/
def sweep (mods : List Name) : CoreM (Array String × Nat × Nat × Nat × Nat × Nat × Nat) := do
  let env ← getEnv
  let mut rows : Array (String × String × String) := #[]
  let mut theorems := 0
  let mut cands := 0
  let mut oor := 0
  let mut searched := 0
  let mut rejected := 0
  let mut undecided := 0
  for (n, ci) in env.constants.toList do
    let .thmInfo _ := ci | continue
    let some idx := env.getModuleIdxFor? n | continue
    let some m := env.header.moduleNames[idx.toNat]? | continue
    if !mods.any (·.isPrefixOf m) || !okName n then continue
    theorems := theorems + 1
    let props ← (forallTelescope ci.type fun xs _ => do
      let mut ps : Array Nat := #[]
      for i in [0:xs.size] do
        if (← isProp (← inferType xs[i]!)) then ps := ps.push i
      return ps).run'
    for i in props do
      cands := cands + 1
      match ← (counterexample ci [i] 3 512).run' with
      | none => oor := oor + 1
      | some (none, decided) =>
        searched := searched + 1
        if decided == 0 then
          undecided := undecided + 1
          rows := rows.push (m.toString, n.toString, s!"undecided\t{n}\t{i}")
        else
          rows := rows.push (m.toString, n.toString, s!"open\t{n}\t{i}\t{decided}")
      | some (some cx, _) =>
        searched := searched + 1
        rejected := rejected + 1
        rows := rows.push (m.toString, n.toString, s!"rejected\t{n}\t{i}\t{cx}")
  return ((rows.qsort fun a b => a.1 < b.1 || (a.1 == b.1 && a.2.1 < b.2.1)).map (·.2.2), theorems, cands, oor, searched, rejected, undecided)

unsafe def main (args : List String) : IO UInt32 := do
  enableInitializersExecution
  match args with
  | "unused-hyps" :: mods@(_ :: _) =>
    initSearchPath (← findSysroot)
    let env ← importModules (mods.toArray.map fun m => { module := m.toName }) {} (trustLevel := 0) (loadExts := true)
    let ctx : Core.Context := { fileName := "<probe>", fileMap := default, maxHeartbeats := 0 }
    let ((lines, theorems, hyps), _) ← (probe (mods.map String.toName)).toIO ctx { env }
    IO.println s!"examined\t{theorems}\t{hyps}"
    for l in lines do IO.println l
    IO.eprintln s!"probe: {lines.size} unused hypotheses among {hyps} in {theorems} theorems"
    return 0
  | "counterexample" :: mod :: thm :: rest =>
    -- Probes.lean counterexample <Module> <Theorem> [<index>,<index>...]: the theorem with the hypotheses at those binder indices dropped
    let drop := (rest.headD "").splitOn "," |>.filterMap String.toNat?
    initSearchPath (← findSysroot)
    let env ← importModules #[{ module := mod.toName }] {} (trustLevel := 0) (loadExts := true)
    let ctx : Core.Context := { fileName := "<probe>", fileMap := default, maxHeartbeats := 0 }
    let some ci := env.find? thm.toName | IO.eprintln s!"{thm}: no such declaration"; return 2
    let (r, _) ← ((counterexample ci drop 3 4096).run').toIO ctx { env }
    match r with
    | some (some cx, _) => IO.println s!"counterexample\t{thm}\t{",".intercalate (drop.map toString)}\t{cx}"
    | _ => IO.println s!"none\t{thm}\t{",".intercalate (drop.map toString)}"
    return 0
  | "cx-sweep" :: mods@(_ :: _) =>
    initSearchPath (← findSysroot)
    let env ← importModules (mods.toArray.map fun m => { module := m.toName }) {} (trustLevel := 0) (loadExts := true)
    let ctx : Core.Context := { fileName := "<probe>", fileMap := default, maxHeartbeats := 0 }
    let ((lines, th, cand, oor, searched, rej, und), _) ← (sweep (mods.map String.toName)).toIO ctx { env }
    IO.println s!"examined\t{th}\t{cand}\t{oor}\t{searched}\t{rej}\t{und}"
    for l in lines do IO.println l
    IO.eprintln s!"cx-sweep: {cand} candidate generalisations in {th} theorems: {oor} out of reach, {searched} searched, {rej} rejected, {und} undecided (no assignment decided the conclusion), {searched - rej - und} open with evidence"
    return 0
  | _ =>
    IO.eprintln "usage: lake env lean --run Probes.lean unused-hyps <Module>... | counterexample <Module> <Theorem> [<index>,...] | cx-sweep <Module>..."
    return 2
