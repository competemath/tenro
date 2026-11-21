/-!
The shape of Mathlib's `Rat.instEncodable` (a definition whose value uses auxiliary proofs, `_proof_N`, of a structure with auto-param
fields, over structures with proof fields): the statements export (`lean4export --statements`, theorems as axioms of their type) must replay
through the kernel as the full export does. Compiled by the workflow `statements-repro`; nothing here is imported by anything else.
-/

structure Eqv (α β : Type) where
  toFun : α → β
  invFun : β → α
  left_inv : ∀ x, invFun (toFun x) = x := by intro x; first | rfl | simp
  right_inv : ∀ x, toFun (invFun x) = x := by intro x; first | rfl | simp

def ratEqv : Eqv Rat ((n : Int) × { d : Nat // 0 < d ∧ n.natAbs.Coprime d }) where
  toFun := fun ⟨a, b, c, d⟩ => ⟨a, ⟨b, ⟨Nat.pos_of_ne_zero c, d⟩⟩⟩
  invFun := fun ⟨a, ⟨b, c, d⟩⟩ => ⟨a, b, Nat.ne_of_gt c, d⟩
  left_inv := fun ⟨_, _, _, _⟩ => rfl
  right_inv := fun ⟨_, ⟨_, _, _⟩⟩ => rfl

theorem ratEqv_left (x : Rat) : ratEqv.invFun (ratEqv.toFun x) = x := ratEqv.left_inv x

/-! The same in the shape of Mathlib's `Equiv` (auto-param fields over `LeftInv`), by an anonymous constructor: the kernel has to compute through the auxiliary proof of
the conjunction (`And.rec` on `ratEqv2._proof_1 ..`) to check the definition, so a theorem stood as an axiom is not enough there. -/

def LeftInv {α β : Type} (g : β → α) (f : α → β) : Prop := ∀ x, g (f x) = x

structure Eqv2 (α β : Type) where
  toFun : α → β
  invFun : β → α
  left_inv : LeftInv invFun toFun := by intro x; first | rfl | simp
  right_inv : LeftInv toFun invFun := by intro x; first | rfl | simp

def ratEqv2 : Eqv2 Rat ((n : Int) × { d : Nat // 0 < d ∧ n.natAbs.Coprime d }) :=
  ⟨fun ⟨a, b, c, d⟩ => ⟨a, ⟨b, ⟨Nat.pos_of_ne_zero c, d⟩⟩⟩, fun ⟨a, ⟨b, c, d⟩⟩ => ⟨a, b, Nat.ne_of_gt c, d⟩, fun ⟨_, _, _, _⟩ => rfl, fun ⟨_, ⟨_, _, _⟩⟩ => rfl⟩
