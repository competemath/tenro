import Lean
import TenroProofs.Eviction
import TenroProofs.Lens
import TenroProofs.Normalise
open Lean Elab Command

/-!
# The audit: every theorem of this project uses only the three standard axioms

`#audit_proofs` walks every theorem declared in a `TenroProofs.*` module (not this one) and fails the build if one depends on an axiom other than `propext`, `Classical.choice`
and `Quot.sound` (so a `sorry`, which is `sorryAx`, or a native-code axiom such as `Lean.ofReduceBool`, stops it), or if the project holds no theorem at all (an empty audit proves nothing).
-/

/-- fail unless every theorem of the loaded `TenroProofs` modules uses only the standard axioms -/
elab "#audit_proofs" : command => do
  let env ← getEnv
  let allowed : List Name := [`propext, `Classical.choice, `Quot.sound]
  let mut checked : Nat := 0
  let mut bad : Array String := #[]
  for (n, ci) in env.constants.toList do
    let some idx := env.getModuleIdxFor? n | continue
    let m := env.header.moduleNames[idx.toNat]!
    if !(`TenroProofs).isPrefixOf m || m == `TenroProofs.Audit then continue
    if !ci.isTheorem || n.isInternal then continue
    checked := checked + 1
    let axs ← collectAxioms n
    for a in axs do
      if !allowed.contains a then bad := bad.push s!"{n} depends on {a}"
  if checked == 0 then throwError "audit: no theorem found (an empty audit proves nothing)"
  if !bad.isEmpty then throwError "audit: {"; ".intercalate bad.toList}"
  logInfo m!"audit: {checked} theorems, standard axioms only"

#audit_proofs
