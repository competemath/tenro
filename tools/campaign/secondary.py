"""secondary.py - the cost axes of a campaign (eval/protocol.md section 2): the paired Wilcoxon signed-rank test on the log ratio of a cost (tokens, wall time) over the problems BOTH arms solved. Standard library only.

For a problem solved by both arms the cost ratio is r = hypothesis / baseline and d = ln r (d < 0: the hypothesis is cheaper). The test is the exact conditional one (every sign pattern of the ranks is equally likely under no difference, ties
get mid-ranks) while at most EXACT_MAX_N pairs differ, and the normal approximation with continuity correction above that.

  better      the median ratio is below 1 and the two-sided p < 0.05                           ("significantly better" in the Pareto rule)
  noninferior the one-sided test that the hypothesis costs no more than (1 + margin) times the baseline, p < 0.05
"""

from __future__ import annotations

import math
import statistics

ALPHA = 0.05
EXACT_MAX_N = 20


def _doubled_midranks(values: list[float]) -> list[int]:
    """the mid-ranks of |values|, doubled so that they are integers"""
    order = sorted(range(len(values)), key=lambda i: abs(values[i]))
    ranks = [0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and abs(values[order[j + 1]]) == abs(values[order[i]]):
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + 1) + (j + 1)  # twice the mean of the ranks i+1 .. j+1
        i = j + 1
    return ranks


def signed_rank(diffs: list[float]) -> dict:
    """{"n": nonzero differences, "p_lower": P(W+ <= observed), "p_upper": P(W+ >= observed), "p_two": two-sided}: W+ is the rank sum of the positive differences"""
    nz = [d for d in diffs if d != 0]
    n = len(nz)
    if n == 0:
        return {"n": 0, "p_lower": 1.0, "p_upper": 1.0, "p_two": 1.0}
    r2 = _doubled_midranks(nz)
    obs = sum(r for r, d in zip(r2, nz, strict=True) if d > 0)
    total = sum(r2)
    if n <= EXACT_MAX_N:
        counts = [0] * (total + 1)
        counts[0] = 1
        for r in r2:
            for s in range(total, r - 1, -1):
                counts[s] += counts[s - r]
        p_lower = sum(counts[: obs + 1]) / 2**n
        p_upper = sum(counts[obs:]) / 2**n
    else:
        mean, sd = total / 2, math.sqrt(sum(r * r for r in r2) / 4)
        phi = lambda z: 0.5 * (1 + math.erf(z / math.sqrt(2)))  # noqa: E731
        p_lower, p_upper = phi((obs - mean + 0.5) / sd), 1 - phi((obs - mean - 0.5) / sd)
    return {"n": n, "p_lower": p_lower, "p_upper": p_upper, "p_two": min(1.0, 2 * min(p_lower, p_upper))}


def axis(base: dict[str, float], hyp: dict[str, float], margin: float) -> dict:
    """one cost axis over the problems both arms solved; `base` and `hyp` map problem id -> cost (> 0)"""
    both = sorted(set(base) & set(hyp))
    d = [math.log(hyp[t]) - math.log(base[t]) for t in both]
    if not d:
        return {"n_pairs": 0, "median_ratio": None, "better": False, "noninferior": False, "better_p": None, "noninferior_p": None}
    shifted = signed_rank([x - math.log1p(margin) for x in d])
    two = signed_rank(d)
    median_ratio = math.exp(statistics.median(d))
    return {
        "n_pairs": len(d),
        "median_ratio": median_ratio,
        "better_p": two["p_two"],
        "better": median_ratio < 1 and two["p_two"] < ALPHA,
        "noninferior_p": shifted["p_lower"],
        "noninferior": shifted["p_lower"] < ALPHA,
        "margin": margin,
    }
