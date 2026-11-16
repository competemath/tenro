import Fx.Lib
open Fx

/-- The problem: its name and the library lemmas it uses are what the scramble hides. -/
theorem problem_double_swap (p : Pt) (n : Nat) : double (n + 0) = 2 * n ∧ p.swap.swap = p := by
  refine ⟨?_, Pt.swap_swap p⟩
  rw [with_where n]
  exact double_eq n
