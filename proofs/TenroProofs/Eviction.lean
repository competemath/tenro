/-!
# The eviction rule of the tawatur tier, proved

`tools/tawatur/admit.py` keeps at most three routes per statement. A full folder of three and a candidate make four routes; the folder keeps the best of the four triples. This file proves,
for the rule as a PURE FUNCTION (no Mathlib, no dependency: Lean core only), what the design (Tengai ADR-0002, point 5) says:

* `evict_optimal`: the kept triple scores at least as much as each of the four triples (the minimum pairwise divergence is maximal);
* `evict_not_worse`: so the folder never gets worse by an admission (its score does not decrease);
* `evict_stable`: if no triple containing the candidate scores strictly more, the folder is returned unchanged (an exact tie keeps the incumbents);
* `evict_contains_candidate`: the folder changes only to a triple that contains the candidate.

It is stated for ANY scoring of triples (`key : β → Nat`): the Python tool ranks triples by (minimum pairwise divergence, then compactness, then names); the proof for an arbitrary key covers
that lexicographic order too once it is encoded as a number, and the minimum-pairwise-divergence key is the instance `minPair3`. What is NOT proved here: that the Python code implements this
function (that is tested, `tests/`), and the real-number arithmetic of Jaccard (the scores are taken as given).
-/

namespace TenroProofs

/-- the first element of `xs` that is strictly better than the current best replaces it: on a tie the current best stays -/
def pick {β : Type} (key : β → Nat) : β → List β → β
  | init, [] => init
  | init, x :: xs => pick key (if key init < key x then x else init) xs

/-- one step of `pick`, stated as an equation so that each case of the comparison can be rewritten on its own -/
theorem pick_cons_pos {β : Type} (key : β → Nat) (init x : β) (xs : List β) (h : key init < key x) :
    pick key init (x :: xs) = pick key x xs := by
  simp [pick, h]

theorem pick_cons_neg {β : Type} (key : β → Nat) (init x : β) (xs : List β) (h : ¬ key init < key x) :
    pick key init (x :: xs) = pick key init xs := by
  simp [pick, h]

theorem pick_mem {β : Type} (key : β → Nat) : ∀ (xs : List β) (init : β), pick key init xs = init ∨ pick key init xs ∈ xs := by
  intro xs
  induction xs with
  | nil => intro init; simp [pick]
  | cons x xs ih =>
    intro init
    by_cases hc : key init < key x
    · rw [pick_cons_pos key init x xs hc]
      rcases ih x with h | h
      · right; rw [h]; exact List.mem_cons_self
      · right; exact List.mem_cons_of_mem _ h
    · rw [pick_cons_neg key init x xs hc]
      rcases ih init with h | h
      · left; exact h
      · right; exact List.mem_cons_of_mem _ h

/-- the key of the result is at least the key of the starting point -/
theorem pick_ge_init {β : Type} (key : β → Nat) : ∀ (xs : List β) (init : β), key init ≤ key (pick key init xs) := by
  intro xs
  induction xs with
  | nil => intro init; simp [pick]
  | cons x xs ih =>
    intro init
    by_cases hc : key init < key x
    · rw [pick_cons_pos key init x xs hc]
      have := ih x
      omega
    · rw [pick_cons_neg key init x xs hc]
      exact ih init

/-- the key of the result is at least the key of every element of the list -/
theorem pick_ge_mem {β : Type} (key : β → Nat) : ∀ (xs : List β) (init : β), ∀ y ∈ xs, key y ≤ key (pick key init xs) := by
  intro xs
  induction xs with
  | nil => intro init y hy; simp at hy
  | cons x xs ih =>
    intro init y hy
    by_cases hc : key init < key x
    · rw [pick_cons_pos key init x xs hc]
      rcases List.mem_cons.mp hy with rfl | hy'
      · exact pick_ge_init key xs y
      · exact ih x y hy'
    · rw [pick_cons_neg key init x xs hc]
      rcases List.mem_cons.mp hy with rfl | hy'
      · have := pick_ge_init key xs init
        omega
      · exact ih init y hy'

/-- if no element of the list is strictly better than the starting point, the starting point is the result -/
theorem pick_stable {β : Type} (key : β → Nat) : ∀ (xs : List β) (init : β), (∀ x ∈ xs, key x ≤ key init) → pick key init xs = init := by
  intro xs
  induction xs with
  | nil => intro init _; simp [pick]
  | cons x xs ih =>
    intro init h
    have hx : ¬ key init < key x := by have := h x List.mem_cons_self; omega
    rw [pick_cons_neg key init x xs hx]
    exact ih init (fun y hy => h y (List.mem_cons_of_mem _ hy))

/-! ## The four triples of a full folder and a candidate -/

variable {α : Type}

/-- the minimum pairwise score of three routes, for a symmetric score `d` of two routes (here: how far apart they are on their weaker axis) -/
def minPair3 (d : α → α → Nat) (t : α × α × α) : Nat :=
  min (d t.1 t.2.1) (min (d t.1 t.2.2) (d t.2.1 t.2.2))

/-- the folder `(a, b, c)` and the candidate `e`: the incumbent triple first, then the three triples that contain `e` -/
def candidates (a b c e : α) : List (α × α × α) := [(a, b, e), (a, c, e), (b, c, e)]

/-- the folder kept after the candidate `e` is offered to the full folder `(a, b, c)`, ranked by any key -/
def evict (key : α × α × α → Nat) (a b c e : α) : α × α × α := pick key (a, b, c) (candidates a b c e)

/-- the kept triple is the incumbent or one of the three with the candidate (so nothing outside the four routes is ever kept) -/
theorem evict_mem (key : α × α × α → Nat) (a b c e : α) :
    evict key a b c e = (a, b, c) ∨ evict key a b c e ∈ candidates a b c e :=
  pick_mem key _ _

/-- OPTIMAL: the kept triple has a key at least as large as each of the four triples -/
theorem evict_optimal (key : α × α × α → Nat) (a b c e : α) :
    key (a, b, c) ≤ key (evict key a b c e) ∧ ∀ t ∈ candidates a b c e, key t ≤ key (evict key a b c e) :=
  ⟨pick_ge_init key _ _, pick_ge_mem key _ _⟩

/-- an admission never makes the folder worse -/
theorem evict_not_worse (key : α × α × α → Nat) (a b c e : α) : key (a, b, c) ≤ key (evict key a b c e) :=
  (evict_optimal key a b c e).1

/-- STABLE: when no triple with the candidate is strictly better, the folder is returned unchanged -/
theorem evict_stable (key : α × α × α → Nat) (a b c e : α)
    (h : ∀ t ∈ candidates a b c e, key t ≤ key (a, b, c)) : evict key a b c e = (a, b, c) :=
  pick_stable key _ _ h

/-- the folder changes only to a triple that contains the candidate: every triple of `candidates` ends in `e` -/
theorem evict_contains_candidate (key : α × α × α → Nat) (a b c e : α) :
    evict key a b c e = (a, b, c) ∨ (evict key a b c e).2.2 = e := by
  rcases evict_mem key a b c e with h | h
  · exact Or.inl h
  · right
    simp only [candidates, List.mem_cons, List.not_mem_nil, or_false] at h
    rcases h with h | h | h <;> rw [h]

/-- the instance of the design: the key is the minimum pairwise score, so the kept triple MAXIMISES it over the four triples and the folder's minimum pairwise divergence never decreases -/
theorem evict_maximises_min_pair (d : α → α → Nat) (a b c e : α) :
    minPair3 d (a, b, c) ≤ minPair3 d (evict (minPair3 d) a b c e) ∧
      ∀ t ∈ candidates a b c e, minPair3 d t ≤ minPair3 d (evict (minPair3 d) a b c e) :=
  evict_optimal (minPair3 d) a b c e

end TenroProofs
