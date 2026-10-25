"""Nearest-person matching: one SQL query, then decide() names someone, or doesn't.

Rule for the live layer: only "no_match" lets a face become eligible for "I don't recognize this
person" (after its wait). "not_sure" stays silent. Voice never triggers "unknown".
These functions are synchronous; the live connection calls them with asyncio.to_thread.
"""

import math
from dataclasses import dataclass
from typing import Literal

import psycopg
from psycopg import sql

TABLES = {"face": "face_samples", "voice": "voice_samples"}
OPERATORS = {"l2": "<->", "cosine": "<=>"}  # cosine distance = 1 - cosine similarity

# The nearest two people, each scored by their best sample. All unlabelled faces form one extra
# group whose id, name and relationship are NULL; decide() never names that group.
_NEAREST = """
SELECT p.id, p.name, p.relationship, p.small_context,
       MIN(s.embedding {op} %(q)s::vector) AS distance
FROM {samples} s
LEFT JOIN people p ON p.id = s.person_id
GROUP BY p.id
ORDER BY distance, p.id
LIMIT 2
"""


@dataclass(frozen=True)
class Candidate:
    person_id: int | None  # None for the group of unlabelled faces
    name: str | None
    relationship: str | None
    small_context: str | None
    distance: float


def nearest_people(
    conn: psycopg.Connection,
    kind: Literal["face", "voice"],
    metric: Literal["l2", "cosine"],
    embedding: list[float],
) -> list[Candidate]:
    if kind not in TABLES or metric not in OPERATORS:
        raise ValueError(f"unknown kind {kind!r} or metric {metric!r}")
    if not all(math.isfinite(x) for x in embedding) or not any(embedding):
        return []  # a zero or broken query has no direction to match
    query = sql.SQL(_NEAREST).format(samples=sql.Identifier(TABLES[kind]), op=sql.SQL(OPERATORS[metric]))
    return [Candidate(*row) for row in conn.execute(query, {"q": embedding})]


def decide(candidates: list[Candidate], cutoff: float, margin: float) -> Candidate | Literal["not_sure", "no_match"]:
    """Name the nearest person only when nothing else could plausibly be them."""
    if not candidates:
        return "no_match"
    best = candidates[0]
    if not (math.isfinite(best.distance) and best.distance < cutoff):
        return "no_match"
    if best.person_id is None:
        return "not_sure"
    if len(candidates) > 1 and not (candidates[1].distance - best.distance >= margin):
        return "not_sure"
    return best
