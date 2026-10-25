"""Live captions from Speechmatics real-time transcription, one session per /live connection.

The HUD's audio chunks are streamed to Speechmatics as they arrive. It answers with partial
transcripts (word by word, shown under the caption bar's cursor) and finished turns, each tagged
with a diarization label (S1, S2, ...). The labels are given names here by matching the audio
behind each one against voice_samples with the same matcher the local path uses; a label that
matches nobody is the wearer, as everywhere else. Finished turns feed the visit transcript and the
wake word exactly like local captions do.

Audio is the only thing that leaves the machine, and only while this mode is on: it needs a
Speechmatics key (SPEECHMATICS_API_KEY, SPEECHMATICS or SPEECHMATICS_KEY in the environment or
.env). Without one, or with NAMETAGS_CAPTIONS=local, captions come from the local Moonshine model.
"""

import asyncio
import logging
import os

import numpy as np

from contract.live import Error, PresentPerson
from voice_rec.cloud import LiveSession as SpeechmaticsSession
from voice_rec.cloud import api_key_from_env
from voice_rec.config import SAMPLE_RATE

log = logging.getLogger("backend.cloud")

MIN_AUDIO = 1.5  # seconds of a label's speech per matching attempt
VOTES_NEEDED = 2  # attempts that must agree before a borderline match names a label
CONFIDENT_DISTANCE = 0.40  # a match this close (cosine; the cutoff is 0.55) names the label on the first attempt
NOBODY_WEIGHT = 0.25  # an attempt that matched no one counts this much, so a later real match wins over it
RECENT_ATTEMPTS = 4  # only the last few attempts per label count: a long "nobody" run must not outvote a person enrolled since
MAX_AUDIO = 8.0  # the speaker model needs no more than this per attempt
MAX_SPEAKERS = 4
STOP_GRACE = 5.0  # seconds to let the last turn through when the connection closes
IDLE_TICK = 0.5  # how often a turn that has gone quiet is checked, even when no audio is arriving


def configured_key() -> str | None:
    """The Speechmatics key, unless NAMETAGS_CAPTIONS=local keeps captions on this machine."""
    if os.environ.get("NAMETAGS_CAPTIONS", "").strip().lower() == "local":
        return None
    return api_key_from_env()


class DbLabelNamer:
    """Turns Speechmatics' S1/S2/... labels into people from voice_samples.

    The audio behind a label is gathered until MIN_AUDIO seconds are in, then matched. A confident
    match (closer than CONFIDENT_DISTANCE) names the label at once; a borderline one is a vote, and
    the label is decided once a candidate has VOTES_NEEDED votes and more weight than any other
    (an attempt that matched nobody counts NOBODY_WEIGHT). Fits voice_rec.cloud.LiveSession's `namer`.
    """

    def __init__(self, identifier, min_audio: float = MIN_AUDIO, votes_needed: int = VOTES_NEEDED):
        self.identifier = identifier
        self.min_audio = min_audio
        self.votes_needed = votes_needed
        self._pending: dict[str, list[np.ndarray]] = {}
        self._attempts: dict[str, list[tuple[int | None, float]]] = {}  # label -> recent (person id or None, weight)
        self._candidates: dict[str, dict[int, PresentPerson]] = {}
        self._decided: dict[str, int | None] = {}  # label -> person id, or None for nobody known

    def offer(self, label: str, audio: np.ndarray) -> str | None:
        """Feed audio for a label; returns the name when this call decided or changed it."""
        buf = self._pending.setdefault(label, [])
        buf.append(np.asarray(audio, dtype=np.float32))
        if sum(len(b) for b in buf) / SAMPLE_RATE < self.min_audio:
            return None
        samples = np.concatenate(buf)[-int(MAX_AUDIO * SAMPLE_RATE) :]
        buf.clear()
        try:
            person, _, distance = self.identifier.identify(samples)
        except ValueError:  # too short for the speaker model after all
            return None
        key = person.person_id if person is not None else None
        if person is not None:
            self._candidates.setdefault(label, {})[key] = person
            if distance is not None and distance <= CONFIDENT_DISTANCE:
                return self._decide(label, key)  # clear enough: don't wait for a second attempt
        weight = (1.0 - distance) if (person is not None and distance is not None) else NOBODY_WEIGHT
        log.info("voice label %s: %s (distance %s, %.1fs of speech)", label, person.name if person else "nobody", f"{distance:.2f}" if distance is not None else "-", len(samples) / SAMPLE_RATE)
        attempts = self._attempts.setdefault(label, [])
        attempts.append((key, weight))
        del attempts[:-RECENT_ATTEMPTS]
        votes: dict[int | None, list[float]] = {}
        for k, w in attempts:
            votes.setdefault(k, []).append(w)
        totals = {k: sum(v) for k, v in votes.items()}
        best = max(totals, key=totals.get)
        if len(votes[best]) < self.votes_needed:
            return None
        if totals[best] <= max([w for k, w in totals.items() if k != best] or [0.0]):
            return None
        return self._decide(label, best)

    def _decide(self, label: str, key: int | None) -> str | None:
        """Record the decision; the name when it is new or changed (nobody -> None)."""
        if label in self._decided and self._decided[label] == key:
            return None
        self._decided[label] = key
        chosen = self.person_for(label)
        return chosen.name if chosen else None

    def decided(self, label: str) -> bool:
        return label in self._decided

    def person_for(self, label: str) -> PresentPerson | None:
        key = self._decided.get(label)
        return self._candidates.get(label, {}).get(key) if key is not None else None

    def name_for(self, label: str) -> str | None:
        person = self.person_for(label)
        return person.name if person else None


class RawLabelSession(SpeechmaticsSession):
    """The voice package's session, with callbacks getting the raw diarization label, not a display name."""

    def display_name(self, label: str) -> str:
        return label


class CloudCaptions:
    """Streams one connection's audio to Speechmatics and turns its transcripts into messages.

    Lives on the event loop: `feed` may be called from any thread, the Speechmatics callbacks run
    on the loop, and anything that touches the database or Claude is handed to the LiveSession on
    a worker thread. Outgoing messages go to `outbox`, which the socket's sender task drains.
    """

    def __init__(self, session, api_key: str, outbox: asyncio.Queue, vocabulary=()):
        self.session = session
        self.outbox = outbox
        self.loop = asyncio.get_running_loop()
        self.queue: asyncio.Queue = asyncio.Queue()
        self.stopped = False
        self.failed = False
        self.task: asyncio.Task | None = None
        self.ticker: asyncio.Task | None = None
        self.turns: set[asyncio.Task] = set()
        self.namer = DbLabelNamer(session.voices)
        self.rt = RawLabelSession(
            api_key=api_key,
            max_speakers=MAX_SPEAKERS,
            enable_partials=True,
            namer=self.namer,
            on_partial=self._partial,
            on_turn=self._turn,
            on_event=self._event,
            extra_vocab=[v for v in vocabulary if v],
        )

    def start(self) -> None:
        self.task = self.loop.create_task(self._run())
        self.ticker = self.loop.create_task(self._tick())

    async def _tick(self) -> None:
        """The session only notices a turn has gone quiet when audio arrives; the mic is muted
        while the app speaks, so check on a clock too."""
        idle_check = getattr(self.rt, "_idle_check", None)
        while idle_check is not None and self.active:
            await asyncio.sleep(IDLE_TICK)
            try:
                idle_check()
            except Exception:  # noqa: BLE001
                log.exception("idle check failed")

    async def flush(self) -> None:
        """Finish the turn being said right now (before a visit ends) and deliver it."""
        if self.active:
            self.rt._flush_turn()
        if self.turns:
            await asyncio.gather(*self.turns, return_exceptions=True)

    async def _run(self) -> None:
        async def blocks():
            while True:
                block = await self.queue.get()
                if block is None:
                    return
                yield block

        try:
            await self.rt.run(blocks(), stop=lambda: self.stopped)
        except Exception as e:  # noqa: BLE001  (the connection goes on with local captions)
            self.failed = True
            log.error("Speechmatics session failed: %s: %s", type(e).__name__, e)
            self.outbox.put_nowait(Error(message=f"Live captions unavailable ({type(e).__name__}); captions continue locally."))

    @property
    def active(self) -> bool:
        return not self.failed and not self.stopped

    def feed(self, samples: np.ndarray) -> None:
        """Audio for the session, from any thread."""
        self.loop.call_soon_threadsafe(self.queue.put_nowait, np.asarray(samples, dtype=np.float32))

    async def stop(self) -> None:
        """End the session; the last turn is still delivered when it comes within STOP_GRACE."""
        self.stopped = True
        self.queue.put_nowait(None)
        if self.ticker is not None:
            self.ticker.cancel()
        if self.task is not None:
            try:
                await asyncio.wait_for(self.task, timeout=STOP_GRACE)
            except (asyncio.TimeoutError, asyncio.CancelledError, Exception):  # noqa: BLE001
                self.task.cancel()
        if self.turns:
            await asyncio.gather(*self.turns, return_exceptions=True)

    # -- Speechmatics callbacks, on the event loop -------------------------------------------------
    def _partial(self, label: str, text: str) -> None:
        now = self.rt.sent_samples / SAMPLE_RATE
        for message in self.session.cloud_partial(label, text, now):
            self.outbox.put_nowait(message)

    def _turn(self, turn, label: str) -> None:
        task = self.loop.create_task(self._finish_turn(label, turn.text, turn.start, turn.end))
        self.turns.add(task)
        task.add_done_callback(self.turns.discard)

    async def _finish_turn(self, label: str, text: str, start: float, end: float) -> None:
        try:
            messages = await asyncio.to_thread(self.session.cloud_turn, label, text, start, end)
        except Exception as e:  # noqa: BLE001
            log.exception("cloud turn failed")
            messages = [Error(message=f"{type(e).__name__}: {e}")]
        for message in messages:
            self.outbox.put_nowait(message)

    def _event(self, kind: str, payload) -> None:
        if kind in ("error", "warning"):
            log.warning("Speechmatics %s: %s", kind, payload)
        elif kind == "mapping":
            log.info("Speechmatics label %s is %s", payload.get("label"), payload.get("speaker"))
            task = self.loop.create_task(self._relabel(payload.get("label")))  # earlier lines were theirs too
            self.turns.add(task)
            task.add_done_callback(self.turns.discard)

    async def _relabel(self, label: str) -> None:
        try:
            messages = await asyncio.to_thread(self.session.cloud_relabel, label)
        except Exception:  # noqa: BLE001
            log.exception("relabel failed")
            return
        for message in messages:
            self.outbox.put_nowait(message)
