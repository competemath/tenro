#!/usr/bin/env python3
"""power.py - sample sizes and the exact test of eval/protocol.md. Standard library only.

  power.py table                       the sample-size table the protocol prints (tests keep the protocol and this file equal)
  power.py n --delta D --psi P [--alpha A] [--power W]               problems needed to detect a gain of D when a fraction P of problems is solved by exactly one of the two systems
  power.py mcnemar B C                 the exact two-sided p-value for B problems only the hypothesis solves and C problems only the baseline solves

Paired design: every problem is run under both systems, so only the discordant problems carry information. psi = P(exactly one system solves a problem) and D = P(only the hypothesis) - P(only the baseline).
Superiority:      n = (z_{1-a/2} sqrt(psi) + z_{1-b} sqrt(psi - D^2))^2 / D^2                         (McNemar, normal approximation, Connor 1987)
Non-inferiority:  n = (z_{1-a} + z_{1-b})^2 psi / margin^2    for a true difference of 0 and a one-sided test of H0: D <= -margin   (the variance is bounded by psi)
"""

from __future__ import annotations

import argparse
import math
import sys
from statistics import NormalDist

Z = NormalDist().inv_cdf


def n_superiority(delta: float, psi: float, alpha: float = 0.05, power: float = 0.90) -> int:
    if not (0 < delta < psi <= 1):
        raise ValueError("need 0 < delta < psi <= 1")
    return math.ceil((Z(1 - alpha / 2) * math.sqrt(psi) + Z(power) * math.sqrt(psi - delta**2)) ** 2 / delta**2)


def n_noninferiority(margin: float, psi: float, alpha: float = 0.05, power: float = 0.90) -> int:
    if not (0 < margin <= psi <= 1):
        raise ValueError("need 0 < margin <= psi <= 1")
    return math.ceil((Z(1 - alpha) + Z(power)) ** 2 * psi / margin**2)


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact p-value: under no difference each discordant problem favours either system with probability 1/2."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2**n
    return min(1.0, 2 * tail)


PSIS = (0.10, 0.20, 0.30)
DELTAS = (0.02, 0.03, 0.05)
MARGINS = (0.01, 0.02)


def table() -> str:
    rows = ["| psi (discordant) | gain 0.02 | gain 0.03 | gain 0.05 | margin 0.01 | margin 0.02 |", "|---|---|---|---|---|---|"]
    for psi in PSIS:
        sup = [str(n_superiority(d, psi)) for d in DELTAS]
        non = [str(n_noninferiority(m, psi)) for m in MARGINS]
        rows.append(f"| {psi:.2f} | " + " | ".join(sup + non) + " |")
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("table")
    n = sub.add_parser("n")
    n.add_argument("--delta", type=float, required=True)
    n.add_argument("--psi", type=float, required=True)
    n.add_argument("--alpha", type=float, default=0.05)
    n.add_argument("--power", type=float, default=0.90)
    m = sub.add_parser("mcnemar")
    m.add_argument("b", type=int)
    m.add_argument("c", type=int)
    a = ap.parse_args(argv)
    if a.cmd == "table":
        print(table())
    elif a.cmd == "n":
        print(n_superiority(a.delta, a.psi, a.alpha, a.power))
    else:
        print(f"{mcnemar_exact(a.b, a.c):.6g}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
