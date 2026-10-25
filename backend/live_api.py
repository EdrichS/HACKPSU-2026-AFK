"""The /live WebSocket: frames and audio in; who is present, captions and sentences to speak out.

One LiveSession per connection holds the room's state (who is present, the visit's transcript, the
voice segmenter). The heavy work runs on a worker thread so the event loop keeps serving. The
glasses or the browser capture the camera and the microphone and speak the `text` fields; the
server never touches audio devices.
"""

import asyncio
import base64
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from contract.live import (
    Answer,
    Arrived,
    Audio,
    Caption,
    EndVisit,
    Error,
    Frame,
    Present,
    PresentPerson,
    TrackedFace,
    Unknown,
    VisitSaved,
    Who,
    WhoAnswer,
    parse_client,
)
from db import context
from embedders.voice import decode_wav
from enroll import store
from enroll.mic import MIN_UTTERANCE
from live.faces import FaceIdentifier
from live.presence import Presence
from live.visit import Visit, render_transcript, save_visit
from live.voices import VoiceIdentifier
from voice_rec.config import SAMPLE_RATE

log = logging.getLogger("backend.live")
router = APIRouter(tags=["live"])

CARD_FACTS = 3  # bullets beside a name
FACTS_CACHE_SECONDS = 10.0
UNRECOGNISED = "Unrecognised message; expected frame, audio, who or end_visit."


class LiveSession:
    def __init__(self, state):
        self.state = state
        self.pool = state.pool
        with self.pool.connection() as conn:
            user = store.find_user(conn)
        self.user_id = user.id if user else None
        self.user_name = user.name if user else "User"
        self.presence = Presence(user_id=self.user_id)
        self.faces = FaceIdentifier(state.face_embedder, self.pool)
        self.voices = VoiceIdentifier(state.voice_embedder, self.pool, presence=self.presence)
        self.visit = Visit()
        self.audio_seconds = 0.0
        self._facts: dict[int, tuple[float, list[str]]] = {}
        try:
            from voice_rec.vad import SpeechSegmenter

            self.segmenter = SpeechSegmenter(min_silence=0.4, max_speech=10.0)
        except FileNotFoundError as e:  # no VAD model: every audio message is one utterance
            log.warning("no VAD (%s); each audio message counts as one utterance", e)
            self.segmenter = None
        self.nova = self.wake = None
        if state.claude is not None:
            from live.nova import NovaBrain
            from voice_rec.assistant import WakeWord

            self.nova = NovaBrain(state.claude, self.pool, self.presence, "Nova", self.user_name)
            self.wake = WakeWord("Nova", aliases=("nova", "nover", "novah"))
        state.presence = self.presence

    # -- what the frontend shows ------------------------------------------------------------
    def card(self, person: PresentPerson) -> PresentPerson:
        """The person with the newest facts filled in (cached a few seconds)."""
        now = time.monotonic()
        cached = self._facts.get(person.person_id)
        if cached is None or now - cached[0] > FACTS_CACHE_SECONDS:
            with self.pool.connection() as conn:
                facts = [f.text for f in context.list_facts(conn, person.person_id)][-CARD_FACTS:]
            self._facts[person.person_id] = (now, facts)
            cached = self._facts[person.person_id]
        return PresentPerson(
            person_id=person.person_id,
            name=person.name,
            relationship=person.relationship,
            small_context=person.small_context,
            facts=cached[1],
        )

    def present(self) -> Present:
        return Present(people=[self.card(p) for p in self.presence.present()], faces=[])

    # -- messages ---------------------------------------------------------------------------
    def on_frame(self, msg: Frame) -> list:
        try:
            detections = self.state.face_embedder.detect_faces(base64.b64decode(msg.jpeg))
        except Exception as e:  # noqa: BLE001  (a bad frame must not end the connection)
            return [Error(message=f"Bad frame: {type(e).__name__}: {e}")]
        out, tracked, unmatched = [], [], False
        for face in detections:
            person, verdict, _ = self.faces.identify(face)
            if person is not None:
                text = self.presence.saw(person, "face")
                if text:
                    out.append(Arrived(person=self.card(person), via="face", text=text))
                    self.visit.note(person)
                tracked.append(TrackedFace(box=face.box, state="named", person_id=person.person_id))
            else:
                unmatched = unmatched or verdict == "no_match"
                tracked.append(TrackedFace(box=face.box, state="unsure", person_id=None))
        text = self.presence.unknown_face(unmatched)
        if self.presence.unknown_confirmed:
            tracked = [TrackedFace(box=f.box, state="unknown", person_id=None) if f.state == "unsure" else f for f in tracked]
        if text:
            out.append(Unknown())
        present = self.present()
        return [Present(people=present.people, faces=tracked)] + out

    def on_audio(self, msg: Audio) -> list:
        try:
            samples = decode_wav(base64.b64decode(msg.wav))
        except Exception as e:  # noqa: BLE001
            return [Error(message=f"Bad audio: {type(e).__name__}: {e}")]
        if self.segmenter is None:
            from voice_rec.vad import SpeechSegment

            segments = [SpeechSegment(start=self.audio_seconds, samples=samples)]
        else:
            segments = self.segmenter.feed(samples)
        self.audio_seconds += len(samples) / SAMPLE_RATE
        out = []
        for segment in segments:
            if segment.duration >= MIN_UTTERANCE:
                out += self.on_utterance(segment.start, segment.samples)
        return out

    def on_utterance(self, start: float, samples) -> list:
        out = []
        try:
            person, _, _ = self.voices.identify(samples)
        except ValueError:  # too short for the speaker model
            return out
        text = self.state.transcriber.transcribe(samples) if self.state.transcriber is not None else ""
        if person is not None:
            arrival = self.presence.saw(person, "voice")
            if arrival:
                out.append(Arrived(person=self.card(person), via="voice", text=arrival))
            self.visit.note(person)
            speaker, person_id = person.name, person.person_id
        else:
            speaker, person_id = self.user_name, self.user_id  # an unknown voice is the wearer's
        if not text:
            return out
        self.visit.add(speaker, person_id, text)
        end = start + len(samples) / SAMPLE_RATE
        out.append(Caption(person_id=person_id, speaker=speaker, text=text, start=start, end=end))
        if self.nova is not None:
            heard, question = self.wake.find(text)
            if heard and len(question.split()) >= 2:
                try:
                    answer = self.nova.answer(question, speaker, render_transcript(self.visit.lines[-20:]))
                except Exception as e:  # noqa: BLE001
                    log.error("Nova failed: %s: %s", type(e).__name__, e)
                    answer = "Sorry, I couldn't answer that just now."
                out.append(Answer(question=question, text=answer))
        return out

    def on_who(self) -> list:
        return [WhoAnswer(text=self.presence.who_answer())]

    def end_visit(self) -> list:
        """The transcript goes to the context owner's Gemini flow, once per visitor."""
        visit, self.visit = self.visit, Visit()
        if not visit.lines:
            return []
        out = []
        for r in save_visit(self.pool, visit, self.user_id):
            if r.updated is not None:
                self._facts.pop(r.person.person_id, None)
                out.append(VisitSaved(person_id=r.person.person_id, name=r.person.name, new_facts=r.new_facts, small_context=r.updated.small_context))
        return out

    def handle(self, msg) -> list:
        try:
            if isinstance(msg, Frame):
                return self.on_frame(msg)
            if isinstance(msg, Audio):
                return self.on_audio(msg)
            if isinstance(msg, Who):
                return self.on_who()
            if isinstance(msg, EndVisit):
                return self.end_visit()
        except Exception as e:  # noqa: BLE001  (the socket must stay open)
            log.exception("live message failed")
            return [Error(message=f"{type(e).__name__}: {e}")]
        return [Error(message=UNRECOGNISED)]

    def close(self) -> None:
        """The connection dropped: keep what the visit taught us."""
        try:
            self.end_visit()
        except Exception:  # noqa: BLE001
            log.exception("could not save the visit on close")
        if self.state.presence is self.presence:
            self.state.presence = None


@router.websocket("/live")
async def live(ws: WebSocket) -> None:
    await ws.accept()
    session = await asyncio.to_thread(LiveSession, ws.app.state)
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = parse_client(raw)
            except ValidationError:
                await ws.send_text(Error(message=UNRECOGNISED).model_dump_json())
                continue
            for out in await asyncio.to_thread(session.handle, msg):
                await ws.send_text(out.model_dump_json())
    except WebSocketDisconnect:
        pass
    finally:
        await asyncio.to_thread(session.close)
