"""Shared test data, and raw-SQL helpers that don't depend on the db package's functions."""

import base64
import io
import struct
import uuid
import zlib
from types import SimpleNamespace

from PIL import Image


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def vec(*head: float, dims: int) -> list[float]:
    """The given numbers, then zeros up to `dims`."""
    return [float(x) for x in head] + [0.0] * (dims - len(head))


def png_bytes(width: int, height: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height)).save(buf, "PNG")
    return buf.getvalue()


def _unique_path(folder: str, extension: str) -> str:
    return f"data/{folder}/{uuid.uuid4().hex}.{extension}"


def insert_person(conn, name: str, relationship: str = "family") -> int:
    return conn.execute(
        "INSERT INTO people (name, relationship) VALUES (%s, %s) RETURNING id", (name, relationship)
    ).fetchone()[0]


def insert_photo(conn) -> int:
    return conn.execute(
        "INSERT INTO photos (file_path, width, height) VALUES (%s, 640, 480) RETURNING id",
        (_unique_path("photos", "jpg"),),
    ).fetchone()[0]


def insert_face(conn, photo_id, person_id=None, embedding=None, model="test") -> int:
    return conn.execute(
        "INSERT INTO face_samples (photo_id, person_id, box_x, box_y, box_width, box_height, model, embedding)"
        " VALUES (%s, %s, 0, 0, 50, 50, %s, %s::vector) RETURNING id",
        (photo_id, person_id, model, embedding if embedding is not None else vec(1.0, dims=128)),
    ).fetchone()[0]


def insert_voice(conn, person_id, embedding=None, model="test", audio_path=None) -> int:
    return conn.execute(
        "INSERT INTO voice_samples (person_id, audio_path, model, embedding)"
        " VALUES (%s, %s, %s, %s::vector) RETURNING id",
        (
            person_id,
            audio_path or _unique_path("voice", "wav"),
            model,
            embedding if embedding is not None else vec(1.0, dims=192),
        ),
    ).fetchone()[0]


def insert_fact(conn, person_id, text="Works as a nurse") -> int:
    return conn.execute(
        "INSERT INTO facts (person_id, text, source) VALUES (%s, %s, 'notes') RETURNING id",
        (person_id, text),
    ).fetchone()[0]


def _png(width: int, height: int) -> bytes:
    """A valid, all-black RGB PNG, built without any imaging library."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    rows = b"".join(b"\x00" + b"\x00\x00\x00" * width for _ in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


PNG_1x1 = _png(1, 1)


class FakeClaude:
    """Stands in for anthropic.Anthropic in Nova's tests: every tool_runner call ends on one
    message that says `reply`, without looking anything up."""

    def __init__(self, reply: str):
        self.reply = reply
        self.beta = self.messages = self  # so client.beta.messages.tool_runner(...) lands below

    def tool_runner(self, **kwargs):
        return [SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=self.reply)])]
