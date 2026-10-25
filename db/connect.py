"""Connecting to Postgres, applying the schema, and refusing embedders the data doesn't fit."""

from pathlib import Path

import psycopg
from psycopg import conninfo, sql
from psycopg_pool import ConnectionPool, PoolTimeout

from contract.embedders import EmbedderSpec

DEFAULT_URL = "postgresql://nametags:nametags@localhost:5433/nametags"
RESET_COMMAND = "docker compose down -v && find data -type f -delete"
SCHEMA = Path(__file__).with_name("schema.sql")


class DatabaseUnavailable(RuntimeError):
    pass


class EmbedderMismatch(RuntimeError):
    pass


def apply_schema(conn: psycopg.Connection) -> None:
    conn.execute(SCHEMA.read_text())
    conn.commit()


def open_pool(url: str = DEFAULT_URL, timeout: float = 5.0) -> ConnectionPool:
    pool = ConnectionPool(url, open=False)
    try:
        pool.open(wait=True, timeout=timeout)
    except PoolTimeout:
        pool.close()
        params = conninfo.conninfo_to_dict(url)
        where = f"{params.get('host', 'localhost')}:{params.get('port', 5432)}"
        raise DatabaseUnavailable(
            f"Can't reach Postgres at {where}. Start it with: docker compose up -d --wait db"
        ) from None
    with pool.connection() as conn:
        apply_schema(conn)
    return pool


def check_embedders(conn: psycopg.Connection, face: EmbedderSpec, voice: EmbedderSpec) -> None:
    """Raise EmbedderMismatch if the stored embeddings can't be compared with these embedders'."""
    sizes = dict(conn.execute(
        """
        SELECT a.attrelid::regclass::text, a.atttypmod
        FROM pg_attribute a
        WHERE a.attrelid IN ('face_samples'::regclass, 'voice_samples'::regclass)
          AND a.attname = 'embedding'
        """
    ).fetchall())
    for table, kind, spec in (("face_samples", "face", face), ("voice_samples", "voice", voice)):
        if sizes[table] != spec.dimensions:
            raise EmbedderMismatch(
                f"{table}.embedding is vector({sizes[table]}) but the {kind} embedder returns "
                f"{spec.dimensions} numbers. Reset the database (deletes everything): {RESET_COMMAND}"
            )
        query = sql.SQL("SELECT DISTINCT model FROM {} ORDER BY model").format(sql.Identifier(table))
        others = [m for (m,) in conn.execute(query) if m != spec.model]
        if others:
            raise EmbedderMismatch(
                f"{table} holds samples from {', '.join(others)} but the {kind} embedder is "
                f"{spec.model}. Switch back to {others[0]}, or reset the database (deletes "
                f"everything): {RESET_COMMAND}"
            )
