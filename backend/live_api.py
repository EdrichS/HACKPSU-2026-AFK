"""The /live WebSocket: frames and audio in; who is present, captions and sentences to speak out.

One LiveSession per connection holds the room's state (who is present, the visit's transcript, the
voice segmenter). The heavy work runs on a worker thread so the event loop keeps serving. The
glasses or the browser capture the camera and the microphone and speak the `text` fields; the
server never touches audio devices.

Captions come one of two ways. With a Speechmatics key (backend/cloud_captions.py) the audio is
streamed to the cloud and comes back word by word: partial captions (`final: false`) while a
sentence is being said, then the finished turn. Otherwise the local Moonshine model transcribes
each utterance once the voice detector hears it end.
"""

import asyncio
import base64
import logging
import threading
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketDisconnected
from pydantic import ValidationError

from contract.embedders import Box
from contract.live import (
    Answer,
    Arrived,
    Audio,
    Caption,
    EndVisit,
    Error,
    Frame,
    UNKNOWN_SPEAKER,
    Present,
    PresentPerson,
    TrackedFace,
    Unknown,
    VisitSaved,
    Who,
    WhoAnswer,
    parse_client,
)
from db import context, people
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
STICKY_SECONDS = 2.0  # a named face keeps its name this long through frames the matcher is unsure about
STICKY_DISTANCE = 0.6  # ...when the new box's centre is within this many face widths of the named one
VISIT_IDLE_SECONDS = 120.0  # a visit with no word for this long is over (python -m live does the same)
UNRECOGNISED = "Unrecognised message; expected frame, audio, who or end_visit."


class LiveSession:
    def __init__(self, state, visit_idle: float = VISIT_IDLE_SECONDS):
        self.state = state
        self.pool = state.pool
        self.visit_idle = visit_idle
        with self.pool.connection() as conn:
            user = store.find_user(conn)
        self.user_id = user.id if user else None
        self.user_name = user.name if user else "User"
        self.presence = Presence(user_id=self.user_id)
        self.faces = FaceIdentifier(state.face_embedder, self.pool)
        self.voices = VoiceIdentifier(state.voice_embedder, self.pool, presence=self.presence)
        self.visit = Visit()
        self.audio_seconds = 0.0
        self.cloud = None  # a CloudCaptions while Speechmatics captions this connection
        self._partial: tuple[str, str] | None = None  # the partial caption on screen: (label, text)
        self._named: dict[int, tuple[PresentPerson, Box, float]] = {}  # person id -> (person, last box, when)
        self._label_lines: dict[str, list] = {}  # cloud label -> transcript lines said before it was named
        self._lock = threading.RLock()  # messages and cloud turns both change the room's state
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
    def safe_present(self) -> Present:
        """A present even when the database is unhappy, so every frame gets its answer."""
        try:
            return self.present()
        except Exception:  # noqa: BLE001
            log.exception("could not list who is present")
            return Present(people=[], faces=[])

    def on_frame(self, msg: Frame) -> list:
        try:
            detections = self.state.face_embedder.detect_faces(base64.b64decode(msg.jpeg))
        except Exception as e:  # noqa: BLE001  (a bad frame must not end the connection)
            return [self.safe_present(), Error(message=f"Bad frame: {type(e).__name__}: {e}")]
        out, tracked, unmatched = [], [], False
        now = time.monotonic()
        for face in detections:
            person, verdict, _ = self.faces.identify(face)
            if person is None:
                person = self.sticky_name(face.box, now)  # a turned head is still who it was a moment ago
            if person is not None:
                self._named[person.person_id] = (person, face.box, now)
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

    def sticky_name(self, box: Box, now: float) -> PresentPerson | None:
        """The person named at about this spot within STICKY_SECONDS, if any.

        The matcher answers "not sure" on a frame where the face is turned, or sits as close to a
        stranger's sample as to the person's own. Without this, every such frame would drop the
        tag and the card from the glasses for a moment."""
        cx, cy = box.x + box.width / 2, box.y + box.height / 2
        for person, last, when in self._named.values():
            if now - when > STICKY_SECONDS:
                continue
            lx, ly = last.x + last.width / 2, last.y + last.height / 2
            if ((lx - cx) ** 2 + (ly - cy) ** 2) ** 0.5 <= STICKY_DISTANCE * max(box.width, last.width):
                return person
        return None

    def on_audio(self, msg: Audio) -> list:
        try:
            samples = decode_wav(base64.b64decode(msg.wav))
        except Exception as e:  # noqa: BLE001
            return [Error(message=f"Bad audio: {type(e).__name__}: {e}")]
        if self.cloud is not None and self.cloud.active:
            self.cloud.feed(samples)  # captions come back through cloud_partial and cloud_turn
            self.audio_seconds += len(samples) / SAMPLE_RATE
            return []
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
            speaker, person_id = UNKNOWN_SPEAKER, None  # nobody we know, the wearer included: no name
        if not text:
            return out
        self.visit.add(speaker, person_id, text)
        end = start + len(samples) / SAMPLE_RATE
        log.info("caption %6.1fs  %s: %s", start, speaker, text)
        out.append(Caption(person_id=person_id, speaker=self.shown(speaker, person), text=text, start=start, end=end))
        return out + self.ask_nova(text, speaker)

    def shown(self, speaker: str, person: PresentPerson | None) -> str | None:
        """The caption's speaker row: only a matched voice has a name; the frontend shows "Someone" for null."""
        return speaker if person is not None else None

    def ask_nova(self, text: str, speaker: str) -> list:
        """A finished sentence that starts with the wake word is a question for Nova."""
        if self.nova is None:
            return []
        heard, question = self.wake.find(text)
        if not (heard and len(question.split()) >= 2):
            return []
        try:
            answer = self.nova.answer(question, speaker, render_transcript(self.visit.lines[-20:]))
        except Exception as e:  # noqa: BLE001
            log.error("Nova failed: %s: %s", type(e).__name__, e)
            answer = "Sorry, I couldn't answer that just now."
        return [Answer(question=question, text=answer)]

    # -- Speechmatics captions (backend/cloud_captions.py) -----------------------------------------
    def cloud_speaker(self, label: str) -> tuple[str, int | None, PresentPerson | None]:
        """Who a diarization label is: a person from voice_samples, else nobody (not the wearer)."""
        person = self.cloud.namer.person_for(label) if self.cloud is not None else None
        if person is not None:
            return person.name, person.person_id, person
        return UNKNOWN_SPEAKER, None, None

    def cloud_partial(self, label: str, text: str, now: float) -> list:
        """Words still being said: a caption that is not final, replaced by the next one. No database work."""
        text = text.strip()
        if not text:
            return []
        # The service's confirmed words trail its guesses by a word or two; showing the shorter
        # confirmed text after the longer guess makes the line shrink and regrow. Keep the guess.
        if self._partial is not None and self._partial[0] == label and self._partial[1].startswith(text) and self._partial[1] != text:
            return []
        self._partial = (label, text)
        speaker, person_id, person = self.cloud_speaker(label)
        return [Caption(person_id=person_id, speaker=self.shown(speaker, person), text=text, final=False, start=now, end=now)]

    def cloud_turn(self, label: str, text: str, start: float, end: float) -> list:
        """A finished turn: the same bookkeeping as a local utterance, on a worker thread.

        Nova and the visit summary take seconds, so they run outside the lock: a frame must never
        wait for them, or every tag on the glasses would blink out meanwhile."""
        if not text.strip():
            return []
        self._partial = None
        with self._lock:
            ended = self.take_idle_visit()
            speaker, person_id, person = self.cloud_speaker(label)
            if person is not None:
                arrival = self.presence.saw(person, "voice")
                if arrival:
                    out_arrival = Arrived(person=self.card(person), via="voice", text=arrival)
                else:
                    out_arrival = None
                self.visit.note(person)
            else:
                out_arrival = None
            line = self.visit.add(speaker, person_id, text)
            if person is None and line is not None:
                self._label_lines.setdefault(label, []).append(line)
            log.info("caption %6.1fs  %s: %s", start, speaker, text)
            caption = Caption(person_id=person_id, speaker=self.shown(speaker, person), text=text, start=start, end=end)
        out = self.save_ended(ended)
        if out_arrival is not None:
            out.append(out_arrival)
        out.append(caption)
        return out + self.ask_nova(text, speaker)

    def cloud_relabel(self, label: str) -> list:
        """A label just got its name: the lines it said before that are theirs in the transcript too,
        and they have arrived. (Captions already on screen stay as they were.)"""
        with self._lock:
            person = self.cloud.namer.person_for(label) if self.cloud is not None else None
            if person is None:
                return []
            for line in self._label_lines.pop(label, []):
                line.speaker, line.person_id = person.name, person.person_id
            self.visit.note(person)
            arrival = self.presence.saw(person, "voice")
            return [Arrived(person=self.card(person), via="voice", text=arrival)] if arrival else []

    def on_who(self) -> list:
        return [WhoAnswer(text=self.presence.who_answer())]

    def take_visit(self) -> Visit | None:
        """Close the visit and hand it over for saving (under the lock); None when nothing was said."""
        visit, self.visit = self.visit, Visit()
        self._label_lines.clear()
        return visit if visit.lines else None

    def take_idle_visit(self) -> Visit | None:
        """A visit nobody has spoken in for a while is over, even if the glasses stay on."""
        if self.visit.lines and time.time() - self.visit.last_line > self.visit_idle:
            return self.take_visit()
        return None

    def save_ended(self, visit: Visit | None) -> list:
        """The transcript goes to the context owner's Claude flow, once per visitor, and to a file.
        Runs outside the lock: Claude takes seconds."""
        if visit is None:
            return []
        self.save_transcript(visit)
        out = []
        for r in save_visit(self.pool, visit, self.user_id):
            if r.updated is not None:
                self._facts.pop(r.person.person_id, None)
                out.append(VisitSaved(person_id=r.person.person_id, name=r.person.name, new_facts=r.new_facts, small_context=r.updated.small_context))
        return out

    def save_transcript(self, visit: Visit) -> None:
        """NAMETAGS_DATA/visits/<start time>.txt: the speaker-labelled lines, for reading back a test.
        (Only facts and cards go in the database; the transcript itself is not stored there.)"""
        try:
            folder = self.state.data_dir / "visits"
            folder.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime(visit.started))
            who = ", ".join(p.name for p in visit.people.values()) or "nobody known"
            body = [f"visit started {stamp}, with: {who}", ""]
            body += [f"{time.strftime('%H:%M:%S', time.localtime(line.t))}  {line.speaker}: {line.text}" for line in visit.lines]
            (folder / f"{stamp}.txt").write_text("\n".join(body) + "\n", encoding="utf-8")
            log.info("visit transcript saved: %s (%d lines)", folder / f"{stamp}.txt", len(visit.lines))
        except OSError as e:
            log.error("could not save the visit transcript: %s", e)

    def end_visit(self) -> list:
        """For tests and the laptop program: close the visit and save it, in one go."""
        with self._lock:
            visit = self.take_visit()
        return self.save_ended(visit)

    def handle(self, msg) -> list:
        try:
            with self._lock:
                ended = self.take_idle_visit()
                if isinstance(msg, Frame):
                    out = self.on_frame(msg)
                elif isinstance(msg, Audio):
                    out = self.on_audio(msg)
                elif isinstance(msg, Who):
                    out = self.on_who()
                elif isinstance(msg, EndVisit):
                    ended = ended or self.take_visit()
                    out = []
                else:
                    return [Error(message=UNRECOGNISED)]
            return self.save_ended(ended) + out  # Claude, outside the lock
        except Exception as e:  # noqa: BLE001  (the socket must stay open; a frame always gets a present)
            log.exception("live message failed")
            answer = [self.safe_present()] if isinstance(msg, Frame) else []
            return answer + [Error(message=f"{type(e).__name__}: {e}")]

    def close(self) -> None:
        """The connection dropped: keep what the visit taught us."""
        try:
            self.end_visit()
        except Exception:  # noqa: BLE001
            log.exception("could not save the visit on close")
        if self.state.presence is self.presence:
            self.state.presence = None


async def send_all(ws: WebSocket, outbox: asyncio.Queue) -> None:
    """The one place that writes to the socket: replies and cloud captions arrive from different tasks."""
    while True:
        message = await outbox.get()
        await ws.send_text(message.model_dump_json())


def known_names(pool) -> list[str]:
    with pool.connection() as conn:
        return [p.name for p in people.list_people(conn)]


async def start_cloud_captions(session: LiveSession, state, outbox: asyncio.Queue):
    """A Speechmatics session for this connection when a key is configured, else None."""
    key = getattr(state, "speechmatics_key", None)
    if not key:
        return None
    from backend.cloud_captions import CloudCaptions

    names = await asyncio.to_thread(known_names, session.pool)  # names transcribe better when the service expects them
    cloud = CloudCaptions(session, key, outbox, vocabulary=names + ["Nova"])
    session.cloud = cloud
    cloud.start()
    return cloud


@router.websocket("/live")
async def live(ws: WebSocket) -> None:
    await ws.accept()
    session = await asyncio.to_thread(LiveSession, ws.app.state)
    outbox: asyncio.Queue = asyncio.Queue()
    sender = asyncio.create_task(send_all(ws, outbox))
    cloud = await start_cloud_captions(session, ws.app.state, outbox)
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = parse_client(raw)
            except ValidationError:
                outbox.put_nowait(Error(message=UNRECOGNISED))
                continue
            if isinstance(msg, EndVisit) and cloud is not None:
                await cloud.flush()  # the sentence being said belongs to this visit
            for out in await asyncio.to_thread(session.handle, msg):
                outbox.put_nowait(out)
    except (WebSocketDisconnect, WebSocketDisconnected):
        pass
    finally:
        if cloud is not None:
            await cloud.stop()
        await asyncio.to_thread(session.close)
        sender.cancel()
