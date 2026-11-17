/-!
# The lens model, proved (Tengai ADR-0003, `tools/lens/lens.py`)

A change of version is a map on statement ids that may split one id into several (what the split lost is kept as a residual, which plays no part in these laws). Written as a total
function `ι → List ι` (an id the lens does not mention maps to itself) the laws the design relies on are theorems here, in Lean core with no dependency:

* `Invertible`: no two different ids lead to the same new id, i.e. the lift back is a FUNCTION. This is exactly the condition `inverse` of `lens.py` enforces, and because the model is total it also
  covers the case the Python only catches at acceptance time (an id the lens leaves alone that another one is mapped onto).
* `comp_invertible`: two invertible lenses compose to an invertible lens. So a long chain of migrations can be summarised by composing, and nothing is lost on the way.
* `comp_assoc`, `comp_pure`: composition is associative with the identity lens as a unit. So a SKIP lens (a block of consecutive migrations composed once, so that going from version 1 to version n takes
  about log n compositions rather than n) gives exactly the same lens as composing one step at a time, in whatever grouping.
* `lift_comp`: the acceptance test (lift a migrated id back, get the original id) passes for a composition when it passes for the parts.

Not proved here: that `lens.py` implements this model (it is tested), and anything about the residuals.
-/

namespace TenroProofs

/-- a migration on statement ids: every old id and the new ids it became (`[x]` for an unchanged id) -/
abbrev Lens (ι : Type) := ι → List ι

/-- the lens that changes nothing -/
def Lens.pure {ι : Type} : Lens ι := fun x => [x]

/-- first `g`, then `f` -/
def Lens.comp {ι : Type} (f g : Lens ι) : Lens ι := fun x => (g x).flatMap f

/-- the lift back is a function: a new id comes from at most one old id -/
def Invertible {ι : Type} (f : Lens ι) : Prop := ∀ x x' y, y ∈ f x → y ∈ f x' → x = x'

theorem pure_invertible {ι : Type} : Invertible (Lens.pure : Lens ι) := by
  intro x x' y h h'
  simp only [Lens.pure, List.mem_singleton] at h h'
  rw [← h, ← h']

theorem mem_comp {ι : Type} (f g : Lens ι) (x y : ι) :
    y ∈ Lens.comp f g x ↔ ∃ m, m ∈ g x ∧ y ∈ f m := by
  simp [Lens.comp, List.mem_flatMap]

/-- composition keeps invertibility -/
theorem comp_invertible {ι : Type} {f g : Lens ι} (hf : Invertible f) (hg : Invertible g) :
    Invertible (Lens.comp f g) := by
  intro x x' y h h'
  obtain ⟨m, hm, hy⟩ := (mem_comp f g x y).mp h
  obtain ⟨m', hm', hy'⟩ := (mem_comp f g x' y).mp h'
  have : m = m' := hf m m' y hy hy'
  subst this
  exact hg x x' m hm hm'

theorem flatMap_pure {ι : Type} : ∀ l : List ι, l.flatMap Lens.pure = l
  | [] => rfl
  | x :: xs => by simp [Lens.pure, flatMap_pure xs]

/-- the identity lens is a unit on both sides -/
theorem comp_pure_left {ι : Type} (f : Lens ι) : Lens.comp Lens.pure f = f := by
  funext x
  exact flatMap_pure (f x)

theorem comp_pure_right {ι : Type} (f : Lens ι) : Lens.comp f Lens.pure = f := by
  funext x
  simp [Lens.comp, Lens.pure]

/-- composition is associative: a skip lens built by grouping a block of migrations is the lens of the whole chain, in any grouping -/
theorem comp_assoc {ι : Type} (f g h : Lens ι) :
    Lens.comp (Lens.comp f g) h = Lens.comp f (Lens.comp g h) := by
  funext x
  show (h x).flatMap (fun m => (g m).flatMap f) = ((h x).flatMap g).flatMap f
  rw [List.flatMap_assoc]

/-- the acceptance test of a composition is the acceptance tests of its parts: if `m` is the unique source of `y` under `f`, and `x` the unique source of `m` under `g`, then `x` is the unique source of `y` under `f ∘ g` -/
theorem lift_comp {ι : Type} {f g : Lens ι} (hf : Invertible f) (hg : Invertible g) {x m y : ι}
    (hm : m ∈ g x) (hy : y ∈ f m) :
    y ∈ Lens.comp f g x ∧ ∀ x', y ∈ Lens.comp f g x' → x' = x :=
  ⟨(mem_comp f g x y).mpr ⟨m, hm, hy⟩, fun x' h' => (comp_invertible hf hg) x' x y h' ((mem_comp f g x y).mpr ⟨m, hm, hy⟩)⟩

/-- a chain of lenses, applied first to last -/
def Lens.chain {ι : Type} : List (Lens ι) → Lens ι
  | [] => Lens.pure
  | f :: fs => Lens.comp (Lens.chain fs) f

/-- a chain of invertible lenses is invertible (any number of migrations in a row) -/
theorem chain_invertible {ι : Type} : ∀ fs : List (Lens ι), (∀ f ∈ fs, Invertible f) → Invertible (Lens.chain fs)
  | [], _ => pure_invertible
  | f :: fs, h => comp_invertible (chain_invertible fs (fun g hg => h g (List.mem_cons_of_mem _ hg))) (h f List.mem_cons_self)

/-- grouping a chain into two blocks and composing the blocks gives the chain: the skip lens of a block is correct -/
theorem chain_append {ι : Type} : ∀ (as bs : List (Lens ι)), Lens.chain (as ++ bs) = Lens.comp (Lens.chain bs) (Lens.chain as)
  | [], bs => by simp [Lens.chain, comp_pure_right]
  | f :: as, bs => by
    simp only [List.cons_append, Lens.chain]
    rw [chain_append as bs, comp_assoc]

end TenroProofs
