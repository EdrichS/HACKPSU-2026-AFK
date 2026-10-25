"""The interfaces the face and voice owners implement, and the checks they run on them."""

import math
from typing import Literal, Protocol

from pydantic import BaseModel


class Box(BaseModel):
    """A face's position in integer pixels of the submitted image, origin at the top left."""

    x: int
    y: int
    width: int
    height: int


class EmbedderSpec(BaseModel):
    dimensions: int
    metric: Literal["l2", "cosine"]
    cutoff: float  # a distance: a match must be strictly under it
    model: str  # names the embedder, so samples from different models are never compared


class FaceDetection(BaseModel):
    box: Box
    embedding: list[float]


class FaceEmbedder(Protocol):
    spec: EmbedderSpec

    def detect_faces(self, image: bytes) -> list[FaceDetection]:
        """Every face in a JPEG or PNG, with its box and embedding."""
        ...


class VoiceEmbedder(Protocol):
    spec: EmbedderSpec

    def embed_voice(self, wav: bytes) -> list[float]:
        """The embedding of a WAV clip (16 kHz, mono, 16-bit)."""
        ...


def check_face_embedder(e: FaceEmbedder, image: bytes) -> None:
    """Raise AssertionError if `e` breaks the contract on `image`."""
    _check_spec(e.spec)
    for face in e.detect_faces(image):
        box = face.box
        if box.x < 0 or box.y < 0:
            raise AssertionError(f"box {box} starts outside the image")
        if box.width <= 0 or box.height <= 0:
            raise AssertionError(f"box {box} has no area")
        _check_embedding(face.embedding, e.spec)


def check_voice_embedder(e: VoiceEmbedder, wav: bytes) -> None:
    """Raise AssertionError if `e` breaks the contract on `wav`."""
    _check_spec(e.spec)
    _check_embedding(e.embed_voice(wav), e.spec)


def _check_spec(spec: EmbedderSpec) -> None:
    if not spec.cutoff > 0:
        raise AssertionError(f"cutoff must be above 0, got {spec.cutoff}")
    if not spec.model.strip():
        raise AssertionError("model must name the embedder")


def _check_embedding(embedding: list[float], spec: EmbedderSpec) -> None:
    if len(embedding) != spec.dimensions:
        raise AssertionError(f"expected {spec.dimensions} numbers, got {len(embedding)}")
    if not all(math.isfinite(x) for x in embedding):
        raise AssertionError("every number in an embedding must be finite")
    if not any(x != 0 for x in embedding):
        raise AssertionError("an embedding can't be all zeros")
