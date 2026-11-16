#!/usr/bin/env python3
"""probe_schema.py <export.ndjson> - print, for every kind of line of a lean4export file, a count and the first example. A tool for reading the
format when it changes (the parser in closure.py pins version 3.x); it reads nothing but the file."""
import json
import sys
from collections import Counter

counts: Counter[str] = Counter()
first: dict[str, str] = {}
with open(sys.argv[1], "rb") as f:
    for n, line in enumerate(f):
        o = json.loads(line)
        shape = ",".join(sorted(o))
        counts[shape] += 1
        first.setdefault(shape, line.decode()[:400].rstrip())
for shape, c in counts.most_common():
    print(f"{c:7d}  {shape}\n         {first[shape]}")
