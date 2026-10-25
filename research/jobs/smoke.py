"""Smoke test: word count over five lines, map -> reduceByKey, checked against a known answer."""
from collections import Counter

from session import spark

LINES = [
    "who is this",
    "that is david your grandson",
    "who is here",
    "david is here",
    "this is maria",
]

sc = spark("smoke").sparkContext
got = dict(
    sc.parallelize(LINES)
    .flatMap(lambda line: line.split())
    .map(lambda w: (w, 1))
    .reduceByKey(lambda a, b: a + b)
    .collect()
)
want = dict(Counter(w for line in LINES for w in line.split()))
assert got == want, (got, want)
print("smoke ok:", sorted(got.items(), key=lambda kv: (-kv[1], kv[0]))[:5])
