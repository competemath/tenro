/- A small library with namespaces, dot notation, `open`, an instance and a `where` lemma: the things a scramble must not break. -/
namespace Fx

structure Pt where
  x : Nat
  y : Nat

def Pt.swap (p : Pt) : Pt := { x := p.y, y := p.x }

theorem Pt.swap_swap (p : Pt) : p.swap.swap = p := by
  cases p
  rfl

/-- doubling -/
def double (n : Nat) : Nat := n + n

theorem double_eq (n : Nat) : double n = 2 * n := by
  unfold double
  omega

theorem double_add (a b : Nat) : double (a + b) = double a + double b := by
  simp only [double]
  omega

instance : Add Pt where
  add p q := { x := p.x + q.x, y := p.y + q.y }

theorem add_x (p q : Pt) : (p + q).x = p.x + q.x := rfl

theorem with_where (n : Nat) : n + 0 = n := aux n
where
  aux (m : Nat) : m + 0 = m := by simp

end Fx
