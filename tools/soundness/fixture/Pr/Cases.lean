namespace Pr

/-- the hypothesis `h` is never used: the theorem holds without it -/
theorem unused_hyp (a b : Nat) (h : a < b) : a + 0 = a := Nat.add_zero a

/-- both hypotheses are used -/
theorem used_hyps (a b : Nat) (h1 : a < b) (h2 : b < a + 2) : b = a + 1 := by omega

/-- one of two hypotheses is used; the other (the second) is not -/
theorem one_of_two (a b : Nat) (h1 : a ≤ b) (h2 : b ≤ a) : a = b := Nat.le_antisymm h1 h2

/-- the hypothesis is mentioned in the conclusion's type (a dependent statement), so it is not droppable -/
theorem dependent (p : Prop) (h : p) : ∀ (_ : p), True := fun _ => trivial

/-- an unused hypothesis behind a structural recursion helper -/
theorem unused_rec (n : Nat) (h : 0 < n) : n + 0 = n := by
  induction n with
  | zero => rfl
  | succ k _ => rfl

/-- no hypotheses at all -/
theorem none_here (n : Nat) : n = n := rfl

/-- a Prop-valued instance argument that is unused -/
theorem unused_inst (p : Prop) [Decidable p] (n : Nat) : n = n := rfl

/-- the hypothesis is needed: without it the statement is false at a = 0 -/
theorem cx_needs_hyp (a : Nat) (h : 0 < a) : a ≠ 0 := by omega

/-- over Bool and Int as well; dropping `h` gives a statement that is still true -/
theorem cx_bool_int (b : Bool) (n : Int) (h : n = n) : (b && true) = b := by simp

end Pr
