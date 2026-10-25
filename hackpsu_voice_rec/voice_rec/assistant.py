"""The voice assistant on top of `voicerec live`.

* A code name ("Nova"): say "hey Nova, ..." and it answers the question, out loud.
* Interjections (opt-in): after each committed sentence it may decide, with a strict
  policy, that it has something worth adding, and says it, one or two sentences.
* A natural voice (Supertonic locally, or Speechmatics TTS) with barge-in: say the code name while it talks and it stops.

Brain: Claude via the Anthropic SDK. Voice: Supertonic 3 (local) or Speechmatics TTS (cloud).
The running transcript (names included) is the context.
"""
from __future__ import annotations

import json
import os
import queue
import re
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Iterator

import numpy as np

from .cloud import ANON, load_dotenv
from .config import MODELS_DIR

DEFAULT_BRAIN = "claude-opus-5-5"
DEFAULT_VOICE_DIR = os.environ.get("VOICEREC_TTS_MODEL", "")  # resolved lazily: first models/sherpa-onnx-supertonic* found
STOP_WORDS = re.compile(r"\b(stop|shut up|be quiet|quiet|never ?mind|enough|cancel)\b", re.I)


# --------------------------------------------------------------------------- context
@dataclass
class ContextTurn:
    speaker: str
    text: str
    t: float
    assistant: bool = False


class Context:
    """Rolling transcript, oldest first, capped by turns and characters."""

    def __init__(self, max_turns: int = 80, max_chars: int = 14000):
        self.turns: deque[ContextTurn] = deque()
        self.max_turns = max_turns
        self.max_chars = max_chars

    def add(self, speaker: str, text: str, assistant: bool = False) -> None:
        text = text.strip()
        if not text:
            return
        self.turns.append(ContextTurn(speaker, text, time.time(), assistant))
        while len(self.turns) > self.max_turns or sum(len(t.text) for t in self.turns) > self.max_chars:
            self.turns.popleft()

    def render(self, code_name: str, last: int | None = None) -> str:
        turns = list(self.turns)[-last:] if last else list(self.turns)
        return "\n".join(f"{code_name + ' (you)' if t.assistant else t.speaker}: {t.text}" for t in turns) or "(nothing yet)"

    def since(self, t0: float) -> list[ContextTurn]:
        return [t for t in self.turns if t.t >= t0 and not t.assistant]


# --------------------------------------------------------------------------- wake word
class WakeWord:
    def __init__(self, name: str, aliases: Iterable[str] = ()):
        names = [name] + list(aliases)
        alts = "|".join(re.escape(n.strip()) for n in names if n.strip())
        # "hey Nova", "okay nova,", "Nova?" ... anywhere in the sentence; captures what follows
        self.rx = re.compile(rf"(?:\b(?:hey|hi|ok|okay|yo|hello|so)\b[,\s]*)?\b(?:{alts})\b[,.!?:;\s]*", re.I)
        self.name = name

    def find(self, text: str) -> tuple[bool, str]:
        """(heard, remainder) where remainder is the text after the code name."""
        m = self.rx.search(text or "")
        if not m:
            return False, text or ""
        return True, (text[m.end():] or "").strip()


# --------------------------------------------------------------------------- brains
class Brain:
    """Claude. One stable system prompt (cached), the transcript as the user turn."""

    def __init__(self, code_name: str, model: str = DEFAULT_BRAIN, persona: str | None = None, notes: str = ""):
        import anthropic

        load_dotenv()
        self.client = anthropic.Anthropic()  # ANTHROPIC_API_KEY from the environment / .env
        self.model = model
        # Adaptive thinking at low effort: measured time to first token is 0.6-0.7 s on
        # Opus 5.5, Sonnet 5.5 and Haiku 5.5 alike, and switching thinking off on Haiku was
        # slower, so there is nothing to gain from fiddling with it.
        self.thinking = None
        self.code_name = code_name
        self.notes = notes  # operator-supplied facts ("we are at HackPSU, demo at 3:45")
        self.participants: set[str] = set()
        self.system = persona or (
            f"You are {code_name}, a voice assistant sitting in on a live conversation between a few people "
            f"(a hackathon team). You hear a transcript with the speakers' names. You are spoken aloud by a "
            f"text-to-speech voice, so write exactly like a sharp, warm, quick-witted person talks: plain words, "
            f"short sentences, contractions, no lists, no markdown, no headings, no emoji, no stage directions. "
            f"Address people by name when it helps. Be concise: a direct question gets one to three sentences unless "
            f"someone asks for detail. If you don't know, say so in a few words. Never mention being an AI unless asked."
        )

    def warm_up(self) -> None:
        """Open the HTTPS connection now so the first real answer does not pay for it."""
        try:
            self.client.messages.count_tokens(model=self.model, messages=[{"role": "user", "content": "hi"}])
        except Exception:  # noqa: BLE001
            pass

    def _request(self, **kw):
        extra = {"thinking": self.thinking} if self.thinking else {}
        kw.setdefault("output_config", {"effort": "low"})
        return self.client.beta.messages.stream(
            model=self.model,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=[{"type": "text", "text": self.system, "cache_control": {"type": "ephemeral"}}],
            **extra,
            **kw,
        )

    def _situation(self) -> str:
        # Volatile facts go in the user turn, never in the (cached) system prompt.
        who = ", ".join(sorted(self.participants)) or "unknown so far"
        lines = [f"Now: {time.strftime('%A %B %d, %Y, %I:%M %p').replace(' 0', ' ')} (local time).",
                 f"People in the room so far: {who}."]
        if self.notes:
            lines.append(f"Notes from the operator: {self.notes}")
        return "\n".join(lines)

    def answer_stream(self, transcript: str, asker: str, question: str) -> Iterator[str]:
        prompt = (
            f"{self._situation()}\n\n"
            f"Conversation so far:\n{transcript}\n\n"
            f"{asker} just said to you: \"{question}\"\n\n"
            f"Reply to {asker} out loud. Use the conversation for context."
        )
        with self._request(max_tokens=600, messages=[{"role": "user", "content": prompt}]) as stream:
            for text in stream.text_stream:
                yield text

    def consider_interjection(self, transcript: str, fresh: str) -> str | None:
        """Strict policy: speak only when there is something specific and useful to add."""
        prompt = (
            f"{self._situation()}\n\n"
            f"Conversation so far:\n{transcript}\n\n"
            f"Most recent lines:\n{fresh}\n\n"
            f"Decide whether {self.code_name} should interject right now, unprompted. Interject ONLY if you can "
            f"add something specific and genuinely useful: correct a factual mistake, answer a question that was asked "
            f"and nobody answered, supply a fact or number someone is reaching for, or flag a real problem with a plan. "
            f"Never interject for small talk, agreement, encouragement, or to summarise. When in doubt, stay silent. "
            f"If you do interject: at most two short spoken sentences, start naturally (for example with the person's name)."
        )
        schema = {
            "type": "object",
            "properties": {"interject": {"type": "boolean"}, "text": {"type": "string"}, "why": {"type": "string"}},
            "required": ["interject", "text", "why"],
            "additionalProperties": False,
        }
        with self._request(
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
        ) as stream:
            msg = stream.get_final_message()
        text = next((b.text for b in msg.content if b.type == "text"), "")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
        return data["text"].strip() if data.get("interject") and data.get("text", "").strip() else None


class MockBrain:
    """Offline stand-in for tests: echoes the question, interjects on the word 'wrong'."""

    def __init__(self, code_name: str):
        self.code_name = code_name

    def answer_stream(self, transcript, asker, question):
        words = f"Sure {asker}. You asked: {question or 'nothing I could catch'}. The time is {time.strftime('%I:%M %p').lstrip('0')}.".split()
        for w in words:
            yield w + " "
            time.sleep(0.03)

    def consider_interjection(self, transcript, fresh):
        return "Quick note, that number sounds off to me." if "wrong" in fresh.lower() else None


# --------------------------------------------------------------------------- voices
class SupertonicVoice:
    """Supertonic 3 (Supertone) through sherpa-onnx: fast, natural, fully local English voice."""

    def __init__(self, model_dir: str | None = None, speed: float = 1.0, num_threads: int = 4):
        import glob

        import sherpa_onnx

        d = Path(model_dir or DEFAULT_VOICE_DIR or next(iter(sorted(glob.glob(str(MODELS_DIR / "sherpa-onnx-supertonic*")))), ""))
        if not d.is_dir():
            raise FileNotFoundError("no Supertonic model folder under models/ (scripts/download_models.sh fetches one)")

        def pick(stem: str) -> str:
            hits = sorted(glob.glob(str(d / f"{stem}*.onnx")))
            if not hits:
                raise FileNotFoundError(f"{stem}*.onnx missing in {d}")
            return hits[0]

        cfg = sherpa_onnx.OfflineTtsConfig(
            model=sherpa_onnx.OfflineTtsModelConfig(
                supertonic=sherpa_onnx.OfflineTtsSupertonicModelConfig(
                    duration_predictor=pick("duration_predictor"), text_encoder=pick("text_encoder"),
                    vector_estimator=pick("vector_estimator"), vocoder=pick("vocoder"),
                    tts_json=str(d / "tts.json"), unicode_indexer=str(d / "unicode_indexer.bin"),
                    voice_style=str(d / "voice.bin"),
                ),
                num_threads=num_threads,
            ),
            max_num_sentences=1,
        )
        if not cfg.validate():
            raise FileNotFoundError(f"Supertonic model files missing in {d}")
        self._tts = sherpa_onnx.OfflineTts(cfg)
        self.sample_rate = self._tts.sample_rate
        self.speed = speed
        self.name = f"supertonic:{d.name}"

    def synthesize(self, text: str) -> np.ndarray:
        audio = self._tts.generate(text, sid=0, speed=self.speed)
        return np.asarray(audio.samples, dtype=np.float32)


class SpeechmaticsVoice:
    """Speechmatics TTS (cloud, same key as `live`): sarah, theo or megan. 16 kHz PCM."""

    sample_rate = 16000

    def __init__(self, voice: str = "sarah", api_key: str | None = None):
        from speechmatics.tts import Voice

        from .cloud import api_key_from_env

        self.api_key = api_key or api_key_from_env()
        if not self.api_key:
            raise RuntimeError("no Speechmatics key for the voice")
        self.voice = Voice(voice.lower())
        self.name = f"speechmatics:{self.voice.value}"

    def synthesize(self, text: str) -> np.ndarray:
        import asyncio

        from speechmatics.tts import AsyncClient, OutputFormat

        async def go() -> bytes:
            async with AsyncClient(api_key=self.api_key) as client:
                async with await client.generate(text=text, voice=self.voice, output_format=OutputFormat.RAW_PCM_16000) as resp:
                    return b"".join([ch async for ch in resp.content.iter_chunked(4096)])

        pcm = asyncio.run(go())
        return np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0


class SayVoice:
    """macOS `say` as a last resort (robotic, but always there)."""

    sample_rate = 22050

    def __init__(self, voice: str = "Samantha", rate: int = 190):
        self.voice, self.rate, self.name = voice, rate, f"say:{voice}"

    def synthesize(self, text: str) -> np.ndarray:
        import subprocess
        import tempfile

        import soundfile as sf

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        subprocess.run(["say", "-v", self.voice, "-r", str(self.rate), "-o", path, "--data-format=LEF32@22050", text], check=True)
        x, sr = sf.read(path, dtype="float32")
        os.unlink(path)
        return x if x.ndim == 1 else x.mean(axis=1)


class Speaker:
    """Plays synthesized speech sentence by sentence on a worker thread; stoppable at once."""

    def __init__(self, engine, device=None, gain: float = 0.9):
        self.engine = engine
        self.device = device
        self.gain = gain
        self._stop = threading.Event()
        self._speaking = threading.Event()
        self.windows: deque[tuple[float, float]] = deque(maxlen=50)  # wall-clock spans of own speech
        self.recent_texts: deque[tuple[float, str]] = deque(maxlen=20)  # (wall-clock, sentence) I said
        self._lock = threading.Lock()
        self.last_error: str | None = None
        self.cache: dict[str, np.ndarray] = {}  # pre-synthesized short phrases (fillers)

    def preload(self, phrases: Iterable[str]) -> None:
        for ph in phrases:
            try:
                self.cache[ph] = self.engine.synthesize(ph)
            except Exception:  # noqa: BLE001
                pass

    @property
    def speaking(self) -> bool:
        return self._speaking.is_set()

    def stop(self) -> None:
        self._stop.set()  # the playback loop checks this between 50 ms chunks and closes its own stream

    def heard_myself(self, t0: float, t1: float, text: str = "", margin: float = 0.6) -> bool:
        """Did [t0, t1] (wall-clock) mostly overlap something I was saying, or does the text
        look like my own recent words? Either is enough: it is my voice through the mic."""
        span = max(1e-3, t1 - t0)
        overlap = 0.0
        for a, b in self.windows:
            overlap += max(0.0, min(t1, b + margin) - max(t0, a - 0.2))
        timing = overlap / span
        words = set(_words(text))
        sim = 0.0
        for when, said in self.recent_texts:
            if t0 - when > 45:
                continue
            mine = set(_words(said))
            if mine and words:
                sim = max(sim, len(words & mine) / len(words))
        # My own speech is clean TTS, so the recognizer gets its words right: a strong text
        # match is decisive. Timing alone is not: a person talking over me must get through.
        if sim >= 0.5:
            return True
        return timing >= 0.4 and (sim >= 0.2 or len(words) < 4)

    def say_stream(self, pieces: Iterable[str], on_sentence: Callable[[str], None] | None = None) -> str:
        """Consume a text stream, speak it sentence by sentence while the rest is still arriving.
        on_sentence fires as each sentence starts playing. Returns the text actually spoken
        (cut short by stop())."""
        import sounddevice as sd

        with self._lock:
            self._stop.clear()
            self._speaking.set()
            spoken: list[str] = []
            q: "queue.Queue[tuple[str, np.ndarray] | None]" = queue.Queue(maxsize=4)

            def synth_worker(sentences: Iterator[str]) -> None:
                try:
                    for s in sentences:
                        if self._stop.is_set():
                            break
                        try:
                            audio = self.cache.get(s)
                            if audio is None:
                                audio = self.engine.synthesize(s)
                        except Exception:  # noqa: BLE001
                            continue
                        if len(audio):
                            q.put((s, audio))
                finally:
                    q.put(None)

            threading.Thread(target=synth_worker, args=(_sentences(pieces, self._stop),), daemon=True).start()
            try:
                while True:
                    item = q.get()
                    if item is None or self._stop.is_set():
                        break
                    sentence, audio = item
                    t0 = time.time()
                    self.windows.append((t0, t0 + len(audio) / self.engine.sample_rate))
                    self.recent_texts.append((t0, sentence))
                    spoken.append(sentence)
                    if on_sentence:
                        on_sentence(sentence)
                    self._play(np.clip(audio * self.gain, -1, 1).astype(np.float32))
            finally:
                self._speaking.clear()
            return " ".join(spoken).strip()

    def _play(self, audio: np.ndarray) -> None:
        """Write the audio to our own output stream in 50 ms chunks so stop() takes effect
        within a chunk, without touching sounddevice's global default stream from another thread."""
        import sounddevice as sd

        sr = self.engine.sample_rate
        chunk = max(256, sr // 20)
        try:
            with sd.OutputStream(samplerate=sr, channels=1, dtype="float32", device=self.device, latency="low") as out:
                for i in range(0, len(audio), chunk):
                    if self._stop.is_set():
                        break
                    out.write(audio[i : i + chunk])
        except Exception as e:  # noqa: BLE001
            self.last_error = f"{type(e).__name__}: {e}"

    def say(self, text: str, on_sentence: Callable[[str], None] | None = None) -> str:
        return self.say_stream([text], on_sentence)


_SENT_END = re.compile(r"(?<=[.!?])\s+|\n+")
_CLAUSE_END = re.compile(r"(?<=[,;:])\s+")
_WORD = re.compile(r"[a-z0-9']+")
_STOP = set("a an the and or but so to of in on at for with is are was were be been it its it's this that "
            "these those i you he she we they me him her us them my your his our their what which who when "
            "where why how do does did not no yes ok okay oh um uh like just really very can could would should".split())


def _words(text: str) -> list[str]:
    """Content words only: stopwords shared with my own speech must not make a human sound like me."""
    return [w for w in _WORD.findall((text or "").lower()) if w not in _STOP]


ACK_WORDS = ["Sure.", "Okay.", "Mm-hm.", "Right."]


def _sentences(pieces: Iterable[str], stop: threading.Event, first_clause: int = 14, idle_flush: float = 0.15) -> Iterator[str]:
    """Regroup a token stream into speakable chunks, flushing early so audio starts fast.

    * every complete sentence goes out as soon as its end is seen;
    * the very first chunk may end at a clause boundary (comma, colon) once it has
      `first_clause` characters;
    * a buffer that already ends in sentence-final punctuation goes out after `idle_flush`
      seconds without new tokens, so the last sentence never waits for the stream to close.
    """
    q: "queue.Queue[object]" = queue.Queue()
    done = object()

    def pump() -> None:
        try:
            for piece in pieces:
                q.put(piece)
        except Exception as e:  # noqa: BLE001
            q.put(e)
        finally:
            q.put(done)

    threading.Thread(target=pump, daemon=True).start()
    buf = ""
    first = True
    while True:
        try:
            item = q.get(timeout=idle_flush)
        except queue.Empty:
            if buf.strip() and buf.rstrip()[-1] in ".!?":
                yield buf.strip()
                buf, first = "", False
            continue
        if item is done:
            break
        if isinstance(item, Exception):
            raise item
        if stop.is_set():
            return
        buf += str(item)
        while True:
            m = _SENT_END.search(buf)
            if first and not m:
                mc = next((c for c in _CLAUSE_END.finditer(buf) if c.start() >= first_clause), None)
                if mc:
                    yield buf[: mc.start()].strip()
                    buf, first = buf[mc.end():], False
                    continue
            if not m:
                break
            chunk = buf[: m.start()].strip()
            yield chunk
            buf, first = buf[m.end():], chunk in ACK_WORDS  # a filler does not count as the first chunk
    if buf.strip():
        yield buf.strip()


def output_state() -> dict | None:
    """macOS: {'volume': 0-100, 'muted': bool} for the system output, else None."""
    import platform
    import subprocess

    if platform.system() != "Darwin":
        return None
    try:
        out = subprocess.run(["osascript", "-e", "get volume settings"], capture_output=True, text=True, timeout=5).stdout
    except Exception:  # noqa: BLE001
        return None
    m = re.search(r"output volume:(\d+).*output muted:(true|false)", out)
    return {"volume": int(m.group(1)), "muted": m.group(2) == "true"} if m else None


def set_output(volume: int) -> None:
    import subprocess

    subprocess.run(["osascript", "-e", "set volume output muted false", "-e", f"set volume output volume {int(volume)}"], check=False, timeout=5)


# --------------------------------------------------------------------------- the assistant
class Assistant:
    def __init__(
        self,
        code_name: str,
        brain,
        speaker: Speaker,
        wake: WakeWord,
        interject: bool = False,
        interject_cooldown: float = 45.0,
        question_window: float = 8.0,
        on_say: Callable[[str, str], None] | None = None,  # (kind: "answer"|"interjection", text)
        on_note: Callable[[str], None] | None = None,
        ack: bool = False,
        ack_after: float = 0.45,
    ):
        self.ack = ack  # say a short "Sure." if the first token has not arrived after ack_after seconds
        self.ack_after = ack_after
        self._ack_words = ACK_WORDS
        if ack:
            speaker.preload(self._ack_words)  # instant, no synthesis on the critical path
        self.code_name = code_name
        self.brain = brain
        self.speaker = speaker
        self.wake = wake
        self.interject = interject
        self.cooldown = interject_cooldown
        self.question_window = question_window
        self.on_say = on_say or (lambda kind, text: None)
        self.on_note = on_note or (lambda text: None)
        self.context = Context()
        self._asker: str | None = None  # waiting for this person's question after a bare wake word
        self._armed_at = 0.0
        self._last_spoke = 0.0
        self._busy = threading.Lock()
        self._last_interject_check = 0.0
        self._seen_turns = 0

    # -- hooks from the live session ----------------------------------------
    def on_partial(self, name: str, text: str) -> None:
        if self.speaker.speaking:
            heard, _ = self.wake.find(text)
            if heard or STOP_WORDS.search(text or ""):
                self.speaker.stop()
                self.on_note("(interrupted)")

    def is_echo(self, text: str, wall_start: float, wall_end: float) -> bool:
        if self.wake.find(text)[0]:
            return False  # the code name is how people interrupt me; it is never my echo
        return self.speaker.heard_myself(wall_start, wall_end, text)

    def is_echo_partial(self, text: str) -> bool:
        """For provisional text: while I am talking, anything that is not my name is almost
        certainly me; afterwards, only text that matches what I just said."""
        if self.wake.find(text)[0]:
            return False
        if self.speaker.speaking:
            return True
        now = time.time()
        return self.speaker.heard_myself(now - 0.1, now, text)

    def on_turn(self, turn, name: str, wall_start: float, wall_end: float) -> None:
        if self.is_echo(turn.text, wall_start, wall_end):
            return  # that was me, coming back through the microphone
        text = turn.text
        heard, question = self.wake.find(text)
        self.context.add(name, text)
        if hasattr(self.brain, "participants") and not name.startswith("Speaker ") and name != "Unknown":
            self.brain.participants.add(name)
        if heard:
            if self.speaker.speaking:
                self.speaker.stop()
            if question and len(question.split()) >= 2:
                self._spawn(self._answer, name, question, wall_end)
            else:
                self._asker, self._armed_at = name, time.time()
                self.on_note(f"(listening for {name}'s question)")
            return
        if self._asker and name == self._asker and time.time() - self._armed_at <= self.question_window:
            self._asker = None
            self._spawn(self._answer, name, text, wall_end)
            return
        if self._asker and time.time() - self._armed_at > self.question_window:
            self._asker = None
        if self.interject:
            self._spawn(self._maybe_interject)

    # -- actions ------------------------------------------------------------
    def _spawn(self, fn, *args) -> None:
        threading.Thread(target=fn, args=args, daemon=True).start()

    def _answer(self, asker: str, question: str, question_end: float | None = None) -> None:
        with self._busy:
            t_q = time.time()
            stt = f"{t_q - question_end:.1f} s to hear it, " if question_end else ""
            self.on_note(f"({asker} asked: {question})")
            marks: dict[str, float] = {}

            def timed_pieces():
                src = self.brain.answer_stream(self.context.render(self.code_name), asker, question)
                if self.ack:
                    # prefetch on a thread; if the brain is slow to start, fill the gap with a word
                    import random

                    q: "queue.Queue[str | None]" = queue.Queue()

                    def pump():
                        try:
                            for piece in src:
                                q.put(piece)
                        except Exception as e:  # noqa: BLE001
                            q.put(f"\x00{type(e).__name__}: {e}")
                        finally:
                            q.put(None)

                    threading.Thread(target=pump, daemon=True).start()
                    try:
                        first = q.get(timeout=self.ack_after)
                    except queue.Empty:
                        yield random.choice(self._ack_words) + " "
                        first = q.get()
                    piece = first
                    while piece is not None:
                        if piece.startswith("\x00"):
                            raise RuntimeError(piece[1:])
                        marks.setdefault("token", time.time())
                        yield piece
                        piece = q.get()
                    return
                for piece in src:
                    marks.setdefault("token", time.time())
                    yield piece

            def on_sentence(sentence: str) -> None:
                now = time.time()
                is_ack = self.ack and "token" not in marks
                if "sound" not in marks:
                    marks["sound"] = now
                    if is_ack:
                        self.on_note(f"(first sound after {stt}{now - t_q:.1f} s: a filler while the model starts)")
                if not is_ack and "answer_audio" not in marks:
                    marks["answer_audio"] = now
                    brain = marks.get("token", now) - t_q
                    voice = now - marks.get("token", t_q)
                    self.on_note(f"(first answer word after {stt}{brain:.1f} s thinking, {voice:.1f} s voice)")
                self.on_say("sentence", sentence)

            try:
                spoken = self.speaker.say_stream(timed_pieces(), on_sentence=on_sentence)
            except Exception as e:  # noqa: BLE001
                self.on_note(f"(brain error: {type(e).__name__}: {str(e)[:120]})")
                return
            if spoken:
                self.context.add(self.code_name, spoken, assistant=True)
                self.on_say("answer", spoken)
            self._last_spoke = time.time()

    def wait_idle(self, timeout: float = 20.0) -> None:
        """Let an answer in progress finish (used when the audio source ends)."""
        deadline = time.time() + timeout
        while time.time() < deadline and (self._busy.locked() or self.speaker.speaking):
            time.sleep(0.1)

    def _maybe_interject(self) -> None:
        now = time.time()
        if now - self._last_spoke < self.cooldown or now - self._last_interject_check < 6.0:
            return
        if not self._busy.acquire(blocking=False):
            return
        try:
            self._last_interject_check = now
            fresh_turns = self.context.since(now - 30)
            if len(fresh_turns) < 2:
                return
            fresh = "\n".join(f"{t.speaker}: {t.text}" for t in fresh_turns[-6:])
            try:
                text = self.brain.consider_interjection(self.context.render(self.code_name), fresh)
            except Exception as e:  # noqa: BLE001
                self.on_note(f"(brain error: {type(e).__name__}: {str(e)[:120]})")
                return
            if not text:
                return
            spoken = self.speaker.say(text, on_sentence=lambda s: self.on_say("sentence", s))
            if spoken:
                self.context.add(self.code_name, spoken, assistant=True)
                self.on_say("interjection", spoken)
            self._last_spoke = time.time()
        finally:
            self._busy.release()
