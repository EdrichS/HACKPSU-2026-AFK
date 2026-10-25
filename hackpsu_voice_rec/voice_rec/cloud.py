"""Cloud streaming mode: Speechmatics real-time transcription with speaker diarization and
speaker identification, streamed word by word, with local TitaNet profiles naming any
speaker the cloud only knows as S1, S2, ...

Two ways a speaker gets a name:
* Speechmatics identifiers enrolled with `voicerec cloud-enroll NAME` are sent with the
  session, and the service labels matching words with the name directly.
* For anonymous labels (S1, S2, ...), the audio behind each label is identified locally
  against `voicerec enroll` profiles and the label is renamed once the evidence agrees.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

import numpy as np

from .config import DATA_DIR, SAMPLE_RATE

CLOUD_DB = Path(os.environ.get("VOICEREC_CLOUD_DB", str(DATA_DIR / "cloud_speakers.json")))
DEFAULT_URL = os.environ.get("SPEECHMATICS_URL", "wss://eu2.rt.speechmatics.com/v2")  # .env may also set SPEECHMATICS_URL
ANON = re.compile(r"^(S\d+|UU)$")


ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
KEY_NAMES = ("SPEECHMATICS_API_KEY", "SPEECHMATICS", "SPEECHMATICS_KEY")


def load_dotenv(path: Path = ENV_FILE) -> None:
    """Minimal .env reader: KEY=VALUE lines (quotes optional, # comments). Never overrides a real env var."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip().removeprefix("export ").strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def api_key_from_env() -> str | None:
    load_dotenv()
    for name in KEY_NAMES:
        if os.environ.get(name):
            return os.environ[name]
    return None


# --------------------------------------------------------------------------- transcript pieces
@dataclass
class Word:
    text: str
    start: float
    end: float
    label: str  # diarization label: an enrolled name, or S1/S2/... (UU = unknown)
    is_eos: bool = False
    kind: str = "word"  # word | punctuation | entity
    confidence: float = 1.0

    @classmethod
    def from_result(cls, r: dict) -> "Word | None":
        alts = r.get("alternatives") or []
        if not alts:
            return None
        a = alts[0]
        return cls(
            text=a.get("content", ""),
            start=float(r.get("start_time", 0.0)),
            end=float(r.get("end_time", 0.0)),
            label=a.get("speaker") or "UU",
            is_eos=bool(r.get("is_eos", False)),
            kind=r.get("type", "word"),
            confidence=float(a.get("confidence", 1.0)),
        )


def join_words(words: Iterable[Word]) -> str:
    out = ""
    for w in words:
        if w.kind == "punctuation" or not out:
            out += w.text
        else:
            out += " " + w.text
    return out.strip()


@dataclass
class Turn:
    label: str
    words: list[Word] = field(default_factory=list)

    @property
    def start(self) -> float:
        return self.words[0].start if self.words else 0.0

    @property
    def end(self) -> float:
        return self.words[-1].end if self.words else 0.0

    @property
    def text(self) -> str:
        return join_words(self.words)


# --------------------------------------------------------------------------- cloud speaker store
class CloudSpeakerStore:
    """Speechmatics speaker identifiers per enrolled name (opaque strings, service-side voiceprints)."""

    def __init__(self, path: Path = CLOUD_DB):
        self.path = Path(path)
        self._speakers: dict[str, dict] = {}
        if self.path.exists():
            raw = json.loads(self.path.read_text())
            self._speakers = raw.get("speakers", {})

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"provider": "speechmatics", "speakers": self._speakers}, indent=1))
        tmp.replace(self.path)

    def names(self) -> list[str]:
        return sorted(self._speakers)

    def __len__(self) -> int:
        return len(self._speakers)

    def add(self, name: str, identifiers: list[str], replace: bool = False) -> None:
        rec = self._speakers.get(name)
        if rec and not replace:
            rec["identifiers"] = list(dict.fromkeys(rec["identifiers"] + identifiers))
            rec["updated"] = time.time()
        else:
            self._speakers[name] = {"identifiers": list(identifiers), "created": time.time(), "updated": time.time()}
        self.save()

    def remove(self, name: str) -> bool:
        if name in self._speakers:
            del self._speakers[name]
            self.save()
            return True
        return False

    def identifiers(self, name: str) -> list[str]:
        return list(self._speakers[name]["identifiers"])

    def known_speakers(self):
        """As SpeakerIdentifier objects for the session config (max 50 identifiers in total)."""
        from speechmatics.rt import SpeakerIdentifier

        out, budget = [], 50
        for n in self.names():
            ids = self.identifiers(n)[: max(0, budget)]
            if ids:
                out.append(SpeakerIdentifier(label=n, speaker_identifiers=ids))
                budget -= len(ids)
        return out


# --------------------------------------------------------------------------- local naming of S-labels
class AudioRing:
    """Recent audio with absolute timestamps so word spans can be cut out again."""

    def __init__(self, seconds: float = 180.0, sample_rate: int = SAMPLE_RATE):
        self.sr = sample_rate
        self.cap = int(seconds * sample_rate)
        self.buf = np.zeros(self.cap, dtype=np.float32)
        self.total = 0  # samples ever appended

    def append(self, x: np.ndarray) -> None:
        x = np.asarray(x, dtype=np.float32)
        n = len(x)
        if n >= self.cap:
            self.buf[:] = x[-self.cap :]
        else:
            pos = self.total % self.cap
            first = min(n, self.cap - pos)
            self.buf[pos : pos + first] = x[:first]
            if first < n:
                self.buf[: n - first] = x[first:]
        self.total += n

    def slice(self, t0: float, t1: float) -> np.ndarray:
        a, b = int(t0 * self.sr), int(t1 * self.sr)
        lo = max(a, self.total - self.cap, 0)
        hi = min(b, self.total)
        if hi <= lo:
            return np.zeros(0, dtype=np.float32)
        idx = np.arange(lo, hi) % self.cap
        return self.buf[idx]


class LabelNamer:
    """Turns S1/S2/... into enrolled names with the local speaker model.

    Audio behind each label is accumulated until there is `min_audio` seconds, identified,
    and counted as a vote. A label is renamed once a name has `votes_needed` votes and
    more weight than any other name (or than 'unknown')."""

    def __init__(self, recognizer, min_audio: float = 2.0, votes_needed: int = 2):
        self.rec = recognizer
        self.min_audio = min_audio
        self.votes_needed = votes_needed
        self._pending: dict[str, list[np.ndarray]] = {}
        self._votes: dict[str, dict[str | None, list[float]]] = {}
        self.names: dict[str, str] = {}

    def offer(self, label: str, audio: np.ndarray) -> str | None:
        """Feed audio for a label; returns the name if this call established or changed it."""
        if not ANON.match(label):
            return None
        buf = self._pending.setdefault(label, [])
        buf.append(np.asarray(audio, dtype=np.float32))
        total = sum(len(b) for b in buf) / SAMPLE_RATE
        if total < self.min_audio:
            return None
        x = np.concatenate(buf)[-int(8 * SAMPLE_RATE) :]
        buf.clear()
        try:
            m = self.rec.identify(x)
        except ValueError:
            return None
        votes = self._votes.setdefault(label, {})
        votes.setdefault(m.speaker, []).append(m.score if m.speaker else 1.0)
        weight = {n: sum(s) for n, s in votes.items()}
        best = max(weight, key=weight.get)
        if best is None or len(votes[best]) < self.votes_needed:
            return None
        if weight[best] <= max([w for n, w in weight.items() if n != best] or [0.0]):
            return None
        if self.names.get(label) != best:
            self.names[label] = best
            return best
        return None

    def name_for(self, label: str) -> str | None:
        return self.names.get(label)


# --------------------------------------------------------------------------- the live session
class LiveSession:
    def __init__(
        self,
        api_key: str,
        url: str = DEFAULT_URL,
        language: str = "en",
        model: str = "enhanced",
        max_speakers: int = 4,
        known_speakers=None,
        enable_partials: bool = True,
        max_delay: float = 1.0,
        speaker_sensitivity: float | None = None,
        prefer_current_speaker: bool = False,
        namer: LabelNamer | None = None,
        on_partial: Callable[[str, str], None] | None = None,  # (display name, text so far)
        on_turn: Callable[[Turn, str], None] | None = None,  # (turn, display name)
        on_event: Callable[[str, dict], None] | None = None,  # ("mapping"|"warning"|"error"|"info", payload)
        idle_flush: float = 2.5,
        extra_vocab: Iterable[str] = (),
        eou_silence: float | None = None,
    ):
        self.api_key = api_key
        self.url = url
        self.language = language
        self.model = model
        self.max_speakers = max(2, max_speakers)
        self.known_speakers = known_speakers or []
        self.enable_partials = enable_partials
        self.max_delay = max_delay
        self.speaker_sensitivity = speaker_sensitivity
        self.prefer_current_speaker = prefer_current_speaker
        self.namer = namer
        self.on_partial = on_partial or (lambda name, text: None)
        self.on_turn = on_turn or (lambda turn, name: None)
        self.on_event = on_event or (lambda kind, payload: None)
        self.idle_flush = idle_flush
        self.extra_vocab = [v for v in extra_vocab if v]
        self.eou_silence = eou_silence  # finalize the sentence after this much silence (voice-agent mode)
        self.ring = AudioRing()
        self.started_at: float | None = None  # wall-clock of the session handshake
        self.audio_epoch: float | None = None  # wall-clock of audio time 0 (mic start); set by the caller
        self.sent_samples = 0
        self.words_per_label: dict[str, int] = {}
        self._turn: Turn | None = None
        self._last_final_wall = 0.0
        self._speakers_result: asyncio.Future | None = None
        self._done: asyncio.Event | None = None
        self._client = None

    def wall(self, t: float) -> float:
        """Audio time (seconds) -> wall-clock."""
        return (self.audio_epoch or self.started_at or time.time()) + t

    # -- naming -------------------------------------------------------------
    def display_name(self, label: str) -> str:
        if not ANON.match(label):
            return label
        if self.namer and self.namer.name_for(label):
            return self.namer.name_for(label)
        return "Speaker " + label[1:] if label.startswith("S") else "Unknown"

    # -- transcript handling ------------------------------------------------
    def _flush_turn(self) -> None:
        turn, self._turn = self._turn, None  # reset first: a failing callback must not corrupt the next turn
        # a turn made only of punctuation is the tail of a sentence already printed: drop it
        if turn and any(w.kind != "punctuation" for w in turn.words):
            self.on_turn(turn, self.display_name(turn.label))

    def _on_final(self, message: dict) -> None:
        words = [w for w in (Word.from_result(r) for r in message.get("results", [])) if w]
        if not words:
            return
        # local naming: hand the audio behind each anonymous label to the namer
        if self.namer:
            spans: dict[str, list[tuple[float, float]]] = {}
            for w in words:
                if w.kind == "word" and ANON.match(w.label):
                    spans.setdefault(w.label, []).append((w.start, w.end))
            for label, ss in spans.items():
                audio = np.concatenate([self.ring.slice(a, b) for a, b in ss]) if ss else np.zeros(0, np.float32)
                if len(audio):
                    changed = self.namer.offer(label, audio)
                    if changed:
                        self.on_event("mapping", {"label": label, "speaker": changed})
        for w in words:
            self.words_per_label[w.label] = self.words_per_label.get(w.label, 0) + (w.kind == "word")
            if self._turn and w.label != self._turn.label and w.kind != "punctuation":
                self._flush_turn()
            if self._turn is None:
                if w.kind == "punctuation":
                    continue  # closes a sentence that was already flushed
                self._turn = Turn(w.label)
            self._turn.words.append(w)
            if w.is_eos and w.kind == "punctuation":
                self._flush_turn()  # sentence complete, punctuation included
        self._last_final_wall = time.time()
        if self._turn:
            self.on_partial(self.display_name(self._turn.label), self._turn.text)

    def _on_partial(self, message: dict) -> None:
        words = [w for w in (Word.from_result(r) for r in message.get("results", [])) if w]
        if not words:
            return
        if self._turn and words[0].label == self._turn.label:
            text = join_words(self._turn.words + words)
            label = self._turn.label
        else:
            text = join_words(words)
            label = words[-1].label
        self.on_partial(self.display_name(label), text)

    # -- session ------------------------------------------------------------
    def _config(self):
        from speechmatics.rt import AudioEncoding, AudioFormat, ConversationConfig, Model, SpeakerDiarizationConfig, TranscriptionConfig

        sdc = SpeakerDiarizationConfig(
            max_speakers=self.max_speakers,
            prefer_current_speaker=self.prefer_current_speaker,
            speaker_sensitivity=self.speaker_sensitivity,
            speakers=self.known_speakers or None,
        )
        kwargs = dict(
            language=self.language,
            diarization="speaker",
            speaker_diarization_config=sdc,
            enable_partials=self.enable_partials,
            max_delay=self.max_delay,
        )
        if self.model:
            kwargs["model"] = Model(self.model)
        if self.extra_vocab:
            kwargs["additional_vocab"] = [{"content": v} for v in self.extra_vocab]
        if self.eou_silence:
            kwargs["conversation_config"] = ConversationConfig(end_of_utterance_silence_trigger=self.eou_silence)
        return TranscriptionConfig(**kwargs), AudioFormat(encoding=AudioEncoding.PCM_S16LE, sample_rate=SAMPLE_RATE, chunk_size=4096)

    async def run(self, audio, stop: Callable[[], bool], pace: float = 0.0, get_speakers_at_end: bool = False) -> list[dict]:
        """Stream `audio` (an iterable or async iterable of float32 16 kHz blocks) until it
        ends or stop() is true. pace > 0 throttles file input to that multiple of real time.
        With get_speakers_at_end, asks for speaker identifiers (enrollment) and returns them."""
        from speechmatics.rt import AsyncClient, ServerMessageType

        loop = asyncio.get_running_loop()
        self._done = asyncio.Event()
        self._speakers_result = loop.create_future()
        client = AsyncClient(api_key=self.api_key, url=self.url)
        self._client = client

        def on_started(m):
            self.on_event("started", m)
            if get_speakers_at_end:
                # documented enrollment recipe: ask once, identifiers come back at the end
                asyncio.ensure_future(client.send_message({"message": "GetSpeakers", "final": True}))

        def on_speakers(m):
            if not self._speakers_result.done():
                self._speakers_result.set_result(m.get("speakers", []))

        client.on(ServerMessageType.RECOGNITION_STARTED, on_started)
        client.on(ServerMessageType.ADD_TRANSCRIPT, self._on_final)
        client.on(ServerMessageType.ADD_PARTIAL_TRANSCRIPT, self._on_partial)
        client.on(ServerMessageType.SPEAKERS_RESULT, on_speakers)
        client.on(ServerMessageType.END_OF_TRANSCRIPT, lambda m: self._done.set())
        client.on(ServerMessageType.ERROR, lambda m: self.on_event("error", m))
        client.on(ServerMessageType.WARNING, lambda m: self.on_event("warning", m))
        client.on(ServerMessageType.INFO, lambda m: self.on_event("info", m))

        async def blocks():
            if hasattr(audio, "__aiter__"):
                async for c in audio:
                    yield c
                return
            it = iter(audio)
            sentinel = object()
            while True:
                c = await loop.run_in_executor(None, next, it, sentinel)  # never block the receive loop
                if c is sentinel:
                    return
                yield c

        async def send(pending: np.ndarray) -> None:
            self.ring.append(pending)
            self.sent_samples += len(pending)
            await client.send_audio((np.clip(pending, -1.0, 1.0) * 32767).astype("<i2").tobytes())

        tcfg, afmt = self._config()
        speakers: list[dict] = []
        min_send = SAMPLE_RATE // 4  # ~250 ms per message keeps the message count sane
        try:
            await client.start_session(transcription_config=tcfg, audio_format=afmt)
            self.started_at = time.time()
            t0 = time.time()
            pending = np.zeros(0, dtype=np.float32)
            async for chunk in blocks():
                if stop():
                    break
                pending = np.concatenate([pending, np.asarray(chunk, dtype=np.float32)])
                self._idle_check()
                if len(pending) < min_send:
                    continue
                await send(pending)
                pending = np.zeros(0, dtype=np.float32)
                if pace:
                    ahead = self.sent_samples / SAMPLE_RATE / pace - (time.time() - t0)
                    if ahead > 0:
                        await asyncio.sleep(ahead)
            if len(pending):
                await send(pending)
            if get_speakers_at_end and self.words_per_label:
                # belt and braces: identifiers so far, in case the end-of-stream answer never comes
                await client.send_message({"message": "GetSpeakers", "final": False})
            await client.stop_session()
            try:
                await asyncio.wait_for(self._done.wait(), timeout=20)
            except asyncio.TimeoutError:
                self.on_event("warning", {"reason": "no EndOfTranscript within 20 s"})
            if get_speakers_at_end:
                try:
                    speakers = await asyncio.wait_for(asyncio.shield(self._speakers_result), timeout=10)
                except asyncio.TimeoutError:
                    self.on_event("warning", {"reason": "no SpeakersResult received"})
        finally:
            self._flush_turn()
            try:
                await client.close()
            except Exception:  # noqa: BLE001
                pass
        return speakers

    def _idle_check(self) -> None:
        """Print a turn that has gone quiet. Sentence-final punctuation can trail the last
        word by a couple of seconds, so wait a little longer when the turn has none yet."""
        if not (self._turn and self._last_final_wall):
            return
        quiet = time.time() - self._last_final_wall
        unfinished = self._turn.words and self._turn.words[-1].kind != "punctuation"
        if quiet > self.idle_flush + (1.5 if unfinished else 0.0):
            self._flush_turn()


# --------------------------------------------------------------------------- audio sources
def mic_blocks(mic, stop: Callable[[], bool]):
    """Generator over Microphone blocks that ends when stop() is true."""
    import queue as _q

    while not stop():
        try:
            yield mic._q.get(timeout=0.2)
        except _q.Empty:
            continue


def file_blocks(path, block: int = 4096):
    from .audio import load_audio

    x = load_audio(path)
    for i in range(0, len(x), block):
        yield x[i : i + block]
