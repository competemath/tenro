/-! The fixture of the closure extractor: Lean core only, so that it builds in seconds. Each theorem is a fact the extractor is
held to (tools/closure/tests/test_closure_real.py), read from the REAL lean4export output of this file. -/

namespace Fx

/-- a definition and a theorem about it: the closure of the theorem passes through the definition -/
def double (n : Nat) : Nat := n + n

theorem double_eq (n : Nat) : double n = n + n := rfl

/-- one statement, three proofs. a and b are different routes; c is a with an unused `have` (padding) -/
theorem swap_a (p q : Prop) (h : p ∧ q) : q ∧ p := ⟨h.2, h.1⟩

theorem swap_b (p q : Prop) (h : p ∧ q) : q ∧ p := by
  obtain ⟨hp, hq⟩ := h
  exact And.intro hq hp

theorem swap_c (p q : Prop) (h : p ∧ q) : q ∧ p := by
  have unused : p ∨ ¬p := Classical.em p
  exact ⟨h.2, h.1⟩

/-- a used `have` is kept: its constant stays in the closure -/
theorem swap_d (p q : Prop) (h : p ∧ q) : q ∧ p := by
  have used : q := h.2
  exact ⟨used, h.1⟩

/-- two chained unused `have`s: the second is dead, and once it is gone so is the first -/
theorem swap_e (p q : Prop) (h : p ∧ q) : q ∧ p := by
  have h1 : p ∨ ¬p := Classical.em p
  have h2 : (p ∨ ¬p) ∨ False := Or.inl h1
  exact ⟨h.2, h.1⟩

/-- the control: a proof that really applies the lemma, so the extractor must keep it -/
theorem em_used (p : Prop) : p ∨ ¬p := Classical.em p

/-- a theorem that reaches a definition through its statement and its proof -/
theorem uses_double : double 2 = 4 := by decide

end Fx
