"""Request and response models for the setup routes and the person-context routes."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from contract.embedders import Box


class Person(BaseModel):
    id: int
    name: str
    relationship: str
    face_count: int
    has_voice: bool
    small_context: str  # the card; empty until the first context update


class PersonIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    relationship: str = Field(min_length=1, max_length=40)


class PersonPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    relationship: str | None = Field(default=None, min_length=1, max_length=40)
    small_context: str | None = Field(default=None, max_length=300)


class NotesIn(BaseModel):
    text: str


class TranscriptLine(BaseModel):
    speaker: str
    text: str


class ConversationIn(BaseModel):
    lines: list[TranscriptLine]


class Fact(BaseModel):
    id: int
    text: str
    source: Literal["conversation", "notes"]
    created_at: datetime


class DetectedFace(BaseModel):
    face_id: int
    box: Box
    person_id: int | None


class PhotoOut(BaseModel):
    photo_id: int
    width: int
    height: int
    faces: list[DetectedFace]


class AssignIn(BaseModel):
    person_id: int | None  # null unlabels the face


class VoiceOut(BaseModel):
    voice_sample_id: int


class VoiceSample(BaseModel):
    voice_sample_id: int
    created_at: datetime
