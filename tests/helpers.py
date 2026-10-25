"""Shared test data."""

import base64
import struct
import zlib


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


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
