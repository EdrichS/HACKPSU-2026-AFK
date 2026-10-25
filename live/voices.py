"""The microphone side: speech -> who is talking (from voice_samples) -> the words (local ASR)."""

import logging
import threading
import time
from dataclasses import dataclass

import numpy as np

from contract.live import PresentPerson
from db.match import decide, nearest_people
from voice_rec.audio import Microphone, load_audio, resolve_device, rms
from voice_rec.config import SAMPLE_RATE
from voice_rec.vad import SpeechSegment, SpeechSegmenter

log = logging.getLogger("live.voices")

# voice_rec's rescue rule: a best match a little past the cutoff is still accepted when it leads
# the runner-up by a wide margin. With a small enrolled set that is almost always right.
RESCUE_FLOOR = 0.10
RESCUE_MARGIN = 0.20


@dataclass
class Utterance:
    t0: float  # wall-clock start
    t1: float
    samples: np.ndarray
    person: PresentPerson | None  # None unless the voice named someone in the database
    verdict: str  # "named", "not_sure" or "no_match"
    distance: float | None  # cosine distance to the nearest person's best sample
    text: str


def to_present(candidate) -> PresentPerson:
    return PresentPerson(
        person_id=candidate.person_id,
        name=candidate.name,
        relationship=candidate.relationship,
        small_context=candidate.small_context or "",
    )


def resolve_voice(candidates, cutoff: float, margin: float, present_ids=()) -> tuple:
    """db.match.decide, then two voice-only refinements: the rescue rule above, and, when two
    people are too close to call, the one the camera currently sees. Returns (Candidate or
    None, verdict)."""
    verdict = decide(candidates, cutoff, margin)
    if not isinstance(verdict, str):
        return verdict, "named"
    named = [c for c in candidates if c.person_id is not None]
    if not named:
        return None, verdict
    best = named[0]
    lead = named[1].distance - best.distance if len(named) > 1 else None
    if best.distance < cutoff + RESCUE_FLOOR and (lead is None or lead >= RESCUE_MARGIN):
        return best, "named"
    if verdict == "not_sure" and best.distance < cutoff:
        close = [c for c in named if c.distance < cutoff and c.distance - best.distance < margin]
        on_camera = [c for c in close if c.person_id in present_ids]
        if len(on_camera) == 1:
            return on_camera[0], "named"
    return None, verdict


class VoiceIdentifier:
    """One utterance -> the person it belongs to, from the voice_samples table.

    Nothing is cached: every utterance is matched against the table as it is now, so a person
    enrolled a moment ago is recognised at once. The camera is not needed; it only breaks ties.
    """

    def __init__(self, embedder, pool, margin: float = 0.10, presence=None):
        self.embedder = embedder
        self.pool = pool
        self.margin = margin
        self.presence = presence

    def identify(self, samples: np.ndarray) -> tuple[PresentPerson | None, str, float | None]:
        embedding = self.embedder.embed_samples(samples)
        with self.pool.connection() as conn:
            candidates = nearest_people(conn, "voice", self.embedder.spec.metric, embedding)
        present = {p.person_id for p in self.presence.present()} if self.presence is not None else ()
        candidate, verdict = resolve_voice(candidates, self.embedder.spec.cutoff, self.margin, present)
        nearest = candidates[0].distance if candidates else None
        if candidate is None:
            return None, verdict, nearest
        return to_present(candidate), verdict, candidate.distance


class VoiceListener(threading.Thread):
    """Reads the microphone (or a recording, paced like one), cuts it into utterances, names and
    transcribes each one. Independent of the camera: it runs the same with no face in view."""

    def __init__(
        self,
        identifier: VoiceIdentifier,
        transcriber,
        on_utterance,
        device=None,
        min_utterance: float = 0.8,
        max_speech: float = 10.0,
        on_level=None,
        source=None,  # an audio file to play through the pipeline instead of the microphone
        speed: float = 1.0,  # file playback pace, as a multiple of real time
        on_end=None,  # called when a file source runs out
    ):
        super().__init__(daemon=True, name="voice-listener")
        self.identifier = identifier
        self.transcriber = transcriber
        self.on_utterance = on_utterance
        self.device = device
        self.min_utterance = min_utterance
        self.max_speech = max_speech
        self.on_level = on_level
        self.source = source
        self.speed = speed
        self.on_end = on_end
        self.stop_event = threading.Event()
        self.error: Exception | None = None

    def run(self) -> None:
        try:
            if self.source is not None:
                self._run_file()
            else:
                self._run_mic()
        except Exception as e:  # noqa: BLE001  (surfaced by the main loop)
            self.error = e
            log.error("listening stopped: %s: %s", type(e).__name__, e)

    def _run_file(self) -> None:
        samples = load_audio(self.source)
        segmenter = SpeechSegmenter(min_silence=0.4, max_speech=self.max_speech)
        epoch = time.time()
        block = 1024
        for i in range(0, len(samples), block):
            if self.stop_event.is_set():
                break
            chunk = samples[i : i + block]
            if self.on_level is not None:
                self.on_level(rms(chunk), segmenter.is_speech)
            for segment in segmenter.feed(chunk):
                self._handle(segment, epoch)
            time.sleep(len(chunk) / SAMPLE_RATE / self.speed)
        for segment in segmenter.flush():
            self._handle(segment, epoch)
        if self.on_end is not None:
            self.on_end()

    def _run_mic(self) -> None:
        segmenter = SpeechSegmenter(min_silence=0.4, max_speech=self.max_speech)
        if True:
            with Microphone(resolve_device(self.device)) as mic:
                epoch = mic.started_at or time.time()
                while not self.stop_event.is_set():
                    for chunk in mic.pending():
                        if self.on_level is not None:
                            self.on_level(rms(chunk), segmenter.is_speech)
                        for segment in segmenter.feed(chunk):
                            self._handle(segment, epoch)
                    if segmenter.is_speech:
                        live = segmenter.current_speech()
                        if len(live) >= self.max_speech * SAMPLE_RATE:
                            # Silero only tries to end long segments; force a decision and go on.
                            self._handle(SpeechSegment(start=segmenter.current_start(), samples=live), epoch)
                            segmenter.reset()
                    time.sleep(0.02)
                for segment in segmenter.flush():
                    self._handle(segment, epoch)

    def _handle(self, segment: SpeechSegment, epoch: float) -> None:
        if segment.duration < self.min_utterance:
            return
        t0 = epoch + segment.start
        try:
            person, verdict, distance = self.identifier.identify(segment.samples)
        except ValueError:  # too short for the speaker model
            return
        text = self.transcriber.transcribe(segment.samples) if self.transcriber is not None else ""
        self.on_utterance(Utterance(t0, t0 + segment.duration, segment.samples, person, verdict, distance, text))
