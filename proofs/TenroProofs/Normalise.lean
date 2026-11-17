/-!
# A model of the canon normaliser, proved (Tengai `TengaiNormalise.lean`, ADR-0004 invariant I2)

The real normaliser edits Lean SOURCE text at syntax-node positions; that part is tested against real Lean (a golden file, a second pass that changes nothing, `isDefEq` between each statement and its
normalised form). What can be proved is the LOGIC of the three rules on a small language that has exactly their shapes: Nat terms with `succ` and `+`, and statements built from `<`, `≤`, `>`, `≥`, `=`,
`≠`, `¬` and `∧`.

* `normF_idempotent`: normalising twice is normalising once (invariant I2);
* `normF_canonical`: the result has no `>`, no `≥`, no `¬ a = b` and no `succ`;
* `normF_sound`: the result means the same as the input, for every assignment of the variables (a rewrite never changes a statement).

What this does not show: that the Lean tool's text edits implement `norm` (a parenthesisation bug would be one, which is why the tool is also tested on Lean, and `isDefEq` compares the elaborated statements).
-/

namespace TenroProofs

inductive Tm where
  | var (i : Nat)
  | num (n : Nat)
  | succ (t : Tm)
  | add (a b : Tm)

inductive Fm where
  | lt (a b : Tm) | le (a b : Tm) | gt (a b : Tm) | ge (a b : Tm)
  | eq (a b : Tm) | ne (a b : Tm)
  | not (p : Fm) | and (p q : Fm)

def Tm.eval (ρ : Nat → Nat) : Tm → Nat
  | .var i => ρ i
  | .num n => n
  | .succ t => t.eval ρ + 1
  | .add a b => a.eval ρ + b.eval ρ

def Fm.eval (ρ : Nat → Nat) : Fm → Prop
  | .lt a b => a.eval ρ < b.eval ρ
  | .le a b => a.eval ρ ≤ b.eval ρ
  | .gt a b => a.eval ρ > b.eval ρ
  | .ge a b => a.eval ρ ≥ b.eval ρ
  | .eq a b => a.eval ρ = b.eval ρ
  | .ne a b => a.eval ρ ≠ b.eval ρ
  | .not p => ¬ p.eval ρ
  | .and p q => p.eval ρ ∧ q.eval ρ

/-- the rule `nat-succ`: `Nat.succ n` is `n + 1` -/
def Tm.norm : Tm → Tm
  | .var i => .var i
  | .num n => .num n
  | .succ t => .add t.norm (.num 1)
  | .add a b => .add a.norm b.norm

/-- the rules `gt-ge` and `not-eq` (and `nat-succ` below them) -/
def Fm.norm : Fm → Fm
  | .lt a b => .lt a.norm b.norm
  | .le a b => .le a.norm b.norm
  | .gt a b => .lt b.norm a.norm
  | .ge a b => .le b.norm a.norm
  | .eq a b => .eq a.norm b.norm
  | .ne a b => .ne a.norm b.norm
  | .not (.eq a b) => .ne a.norm b.norm
  | .not p => .not p.norm
  | .and p q => .and p.norm q.norm

/-- no `succ` -/
def Tm.canon : Tm → Prop
  | .var _ => True
  | .num _ => True
  | .succ _ => False
  | .add a b => a.canon ∧ b.canon

def Fm.isEq : Fm → Bool
  | .eq _ _ => true
  | _ => false

/-- no `>`, no `≥`, no `¬ a = b`, no `succ` -/
def Fm.canon : Fm → Prop
  | .lt a b => a.canon ∧ b.canon
  | .le a b => a.canon ∧ b.canon
  | .gt _ _ => False
  | .ge _ _ => False
  | .eq a b => a.canon ∧ b.canon
  | .ne a b => a.canon ∧ b.canon
  | .not p => p.isEq = false ∧ p.canon
  | .and p q => p.canon ∧ q.canon

theorem Tm.norm_canon : ∀ t : Tm, t.norm.canon
  | .var _ => trivial
  | .num _ => trivial
  | .succ t => ⟨Tm.norm_canon t, trivial⟩
  | .add a b => ⟨Tm.norm_canon a, Tm.norm_canon b⟩

theorem Tm.norm_of_canon : ∀ t : Tm, t.canon → t.norm = t
  | .var _, _ => rfl
  | .num _, _ => rfl
  | .succ _, h => h.elim
  | .add a b, ⟨ha, hb⟩ => by simp [Tm.norm, Tm.norm_of_canon a ha, Tm.norm_of_canon b hb]

theorem Tm.norm_sound (ρ : Nat → Nat) : ∀ t : Tm, t.norm.eval ρ = t.eval ρ
  | .var _ => rfl
  | .num _ => rfl
  | .succ t => by simp [Tm.norm, Tm.eval, Tm.norm_sound ρ t]
  | .add a b => by simp [Tm.norm, Tm.eval, Tm.norm_sound ρ a, Tm.norm_sound ρ b]

/-- normalising keeps equations as equations and everything else as something else (so `¬ p` is never turned into `¬ (a = b)` by an inner rewrite) -/
theorem Fm.isEq_norm : ∀ p : Fm, p.norm.isEq = p.isEq
  | .lt _ _ | .le _ _ | .gt _ _ | .ge _ _ | .eq _ _ | .ne _ _ | .and _ _ => rfl
  | .not q => by cases q <;> simp [Fm.norm, Fm.isEq]

theorem Fm.norm_not (q : Fm) (h : q.isEq = false) : (Fm.not q).norm = .not q.norm := by
  cases q <;> simp_all [Fm.norm, Fm.isEq]

/-- the normal form has none of the four forbidden shapes -/
theorem normF_canonical : ∀ p : Fm, p.norm.canon
  | .lt a b => ⟨Tm.norm_canon a, Tm.norm_canon b⟩
  | .le a b => ⟨Tm.norm_canon a, Tm.norm_canon b⟩
  | .gt a b => ⟨Tm.norm_canon b, Tm.norm_canon a⟩
  | .ge a b => ⟨Tm.norm_canon b, Tm.norm_canon a⟩
  | .eq a b => ⟨Tm.norm_canon a, Tm.norm_canon b⟩
  | .ne a b => ⟨Tm.norm_canon a, Tm.norm_canon b⟩
  | .and p q => ⟨normF_canonical p, normF_canonical q⟩
  | .not q => by
    cases hq : q.isEq with
    | true => cases q <;> simp_all [Fm.isEq, Fm.norm, Fm.canon, Tm.norm_canon]
    | false =>
      rw [Fm.norm_not q hq]
      exact ⟨by rw [Fm.isEq_norm, hq], normF_canonical q⟩

/-- a statement that is already canonical is not changed -/
theorem normF_of_canon : ∀ p : Fm, p.canon → p.norm = p
  | .lt a b, ⟨ha, hb⟩ => by simp [Fm.norm, Tm.norm_of_canon a ha, Tm.norm_of_canon b hb]
  | .le a b, ⟨ha, hb⟩ => by simp [Fm.norm, Tm.norm_of_canon a ha, Tm.norm_of_canon b hb]
  | .gt _ _, h => h.elim
  | .ge _ _, h => h.elim
  | .eq a b, ⟨ha, hb⟩ => by simp [Fm.norm, Tm.norm_of_canon a ha, Tm.norm_of_canon b hb]
  | .ne a b, ⟨ha, hb⟩ => by simp [Fm.norm, Tm.norm_of_canon a ha, Tm.norm_of_canon b hb]
  | .and p q, ⟨hp, hq⟩ => by simp [Fm.norm, normF_of_canon p hp, normF_of_canon q hq]
  | .not q, ⟨hq, hc⟩ => by rw [Fm.norm_not q hq, normF_of_canon q hc]

/-- INVARIANT I2: normalising twice is normalising once -/
theorem normF_idempotent (p : Fm) : p.norm.norm = p.norm :=
  normF_of_canon _ (normF_canonical p)

/-- a rewrite never changes what a statement says -/
theorem normF_sound (ρ : Nat → Nat) : ∀ p : Fm, p.norm.eval ρ ↔ p.eval ρ
  | .lt a b => by simp [Fm.norm, Fm.eval, Tm.norm_sound]
  | .le a b => by simp [Fm.norm, Fm.eval, Tm.norm_sound]
  | .gt a b => by simp [Fm.norm, Fm.eval, Tm.norm_sound]
  | .ge a b => by simp [Fm.norm, Fm.eval, Tm.norm_sound]
  | .eq a b => by simp [Fm.norm, Fm.eval, Tm.norm_sound]
  | .ne a b => by simp [Fm.norm, Fm.eval, Tm.norm_sound]
  | .and p q => by simp [Fm.norm, Fm.eval, normF_sound ρ p, normF_sound ρ q]
  | .not q => by
    cases hq : q.isEq with
    | true => cases q <;> simp_all [Fm.isEq, Fm.norm, Fm.eval, Tm.norm_sound]
    | false => rw [Fm.norm_not q hq]; simp [Fm.eval, normF_sound ρ q]

end TenroProofs
