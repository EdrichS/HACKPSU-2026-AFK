"""python -m live: the patient's laptop during a visit."""

import argparse
import logging
import os
import sys
import threading
import time
from collections import deque
from pathlib import Path
from types import SimpleNamespace

from contract.live import UNKNOWN_SPEAKER
from db import people
from db.connect import DEFAULT_URL, DatabaseUnavailable, EmbedderMismatch, check_embedders, open_pool
from enroll import store
from enroll.cli import bold, dim, green, red, yellow
from live.presence import Presence
from live.visit import Visit, VisitResult, save_visit

MODEL = "claude-opus-5-5"  # Nova's brain; visit summaries are Gemini's (backend.gemini)

ROOT = Path(__file__).resolve().parents[1]
log = logging.getLogger("live")


def load_env() -> None:
    """ANTHROPIC_API_KEY (and friends) from the repo's gitignored .env, never overriding real env vars."""
    from voice_rec.cloud import load_dotenv

    load_dotenv(ROOT / ".env")
    load_dotenv()  # the voice package's own .env, if any


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m live",
        description="Open the camera and the microphone, name the people the database knows, keep the visit's "
        "transcript, summarize it into their cards, and answer questions as Nova.",
    )
    p.add_argument("--user", metavar="NAME", help="the app user's name, the person wearing the glasses (default: the person registered with `enroll --user`, else 'User')")
    cam = p.add_argument_group("camera")
    cam.add_argument("--camera", default="0", help="camera index or video source (default: %(default)s)")
    cam.add_argument("--no-camera", action="store_true", help="microphone only")
    cam.add_argument("--face-rate", type=float, default=3.0, help="look for faces at most this many times a second (default: %(default)s)")
    cam.add_argument("--face-upsample", type=int, default=0, help="detector upsampling: 0 is fast and finds faces within arm's reach to a couple of metres, 1 finds smaller faces at several times the cost (default: %(default)s)")
    cam.add_argument("--face-margin", type=float, default=0.05, help="a face is named only if the runner-up is at least this much farther (L2) (default: %(default)s)")
    mic = p.add_argument_group("microphone")
    mic.add_argument("--mic", help="input device index or name substring (default: the system default)")
    mic.add_argument("--no-mic", action="store_true", help="camera only")
    mic.add_argument("--voice-margin", type=float, default=0.10, help="a voice is named only if the runner-up is at least this much farther (cosine) (default: %(default)s)")
    mic.add_argument("--no-transcribe", action="store_true", help="name voices but don't transcribe (no visit summary, no Nova)")
    mic.add_argument("--audio-file", type=Path, metavar="FILE", help="play this recording through the pipeline instead of the microphone, then stop")
    mic.add_argument("--audio-speed", type=float, default=1.0, help="pace of --audio-file, as a multiple of real time (default: %(default)s)")
    out = p.add_argument_group("voice output")
    out.add_argument("--no-tts", action="store_true", help="print what would be spoken instead of saying it")
    out.add_argument("--tts-voice", metavar="DIR", help="Supertonic model folder (default: the first under hackpsu_voice_rec/models)")
    brain = p.add_argument_group("Claude")
    brain.add_argument("--model", default=MODEL, help="(default: %(default)s)")
    brain.add_argument("--nova-name", default="Nova", help="the wake word (default: %(default)s)")
    brain.add_argument("--no-nova", action="store_true", help="don't answer questions")
    brain.add_argument("--no-summary", action="store_true", help="don't summarize visits into the database")
    brain.add_argument("--visit-timeout", type=float, default=120.0, help="seconds of silence after which the visit ends and is summarized (default: %(default)s)")
    where = p.add_argument_group("where")
    where.add_argument("--database-url", default=os.environ.get("DATABASE_URL", DEFAULT_URL), help="(default: $DATABASE_URL or %(default)s)")
    where.add_argument("--log", type=Path, metavar="FILE", help="append the timestamped transcript to this file")
    p.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    return p


class Session:
    """Everything the threads share."""

    def __init__(self, args, pool, user_name: str, user_id: int | None):
        self.args = args
        self.pool = pool
        self.user_name = user_name
        self.user_id = user_id
        self.presence = Presence(user_id=user_id)
        self.visit = Visit()
        self.visit_lock = threading.Lock()
        self.stop = threading.Event()
        self.lines: deque[str] = deque(maxlen=4)  # for the window
        self.mic_state = "mic: starting"
        self.nova_state = ""
        self.speaker = None
        self.assistant = None
        self.client = None  # Anthropic, for Nova only
        self.gemini = False  # whether visits can become facts and cards
        self.logfile = open(args.log, "a", encoding="utf-8") if args.log else None

    # -- output -----------------------------------------------------------------------------
    def say(self, text: str, who: str = "") -> None:
        """Speak `text` (on its own thread, so no camera frame waits for it) and show it."""
        print(f"{dim(time.strftime('%H:%M:%S'))}  {bold(who or 'app')}: {text}", flush=True)
        self.lines.append(f"{who or 'app'}: {text}")
        if self.speaker is not None:
            threading.Thread(target=self.speaker.say, args=(text,), daemon=True).start()

    def overlay(self) -> list[str]:
        here = self.presence.present()
        lines = ["Here: " + (", ".join(f"{p.name} ({p.relationship})" for p in here) or "nobody I know")]
        lines += [f"  {p.name}: {p.small_context}" for p in here if p.small_context][:2]
        lines.append(self.mic_state)
        lines += list(self.lines)
        if self.nova_state:
            lines.append(self.nova_state)
        return lines

    # -- the microphone's results ----------------------------------------------------------
    def on_level(self, level: float, speaking: bool) -> None:
        self.mic_state = "mic: speaking" if speaking else "mic: listening"

    def on_utterance(self, u) -> None:
        if self.assistant is not None and self.assistant.is_echo(u.text, u.t0, u.t1):
            return  # that was the app's own voice coming back through the microphone
        if u.person is not None:
            name = u.person.name
            text = self.presence.saw(u.person, "voice")
            if text:
                self.say(text)
            with self.visit_lock:
                self.visit.note(u.person)
        else:
            name = UNKNOWN_SPEAKER  # nobody we know, the wearer included: their own voice is enrolled like anyone's
        stamp = time.strftime("%H:%M:%S", time.localtime(u.t0))
        score = f"{u.distance:.2f}" if u.distance is not None else "-"
        print(f"{dim(stamp)}  {green(name) if u.person else yellow(name)}: {u.text or dim('(no words)')}  {dim(f'{u.verdict} {score} {u.t1 - u.t0:.1f}s')}", flush=True)
        if not u.text:
            return
        self.lines.append(f"{name}: {u.text}")
        with self.visit_lock:
            self.visit.add(name, u.person.person_id if u.person else None, u.text)
        if self.logfile is not None:
            self.logfile.write(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(u.t0))}  {name}: {u.text}\n")
            self.logfile.flush()
        if self.assistant is not None:
            self.assistant.on_turn(SimpleNamespace(text=u.text), name, u.t0, u.t1)

    # -- visits ------------------------------------------------------------------------------
    def end_visit(self, reason: str) -> None:
        with self.visit_lock:
            visit, self.visit = self.visit, Visit()
        if not visit.lines:
            return
        known = [p for pid, p in visit.people.items() if pid != self.user_id]
        print(f"\n{bold('visit over')} ({reason}): {len(visit.lines)} line(s), {', '.join(p.name for p in known) or 'no one known'}", flush=True)
        if not known:
            return
        if self.args.no_summary or not self.gemini:
            print(dim("  not summarized (" + ("--no-summary" if self.args.no_summary else "no GEMINI_API_KEY") + ")"), flush=True)
            return
        self.nova_state = "summarizing the visit..."
        for r in save_visit(self.pool, visit, self.user_id):
            self._report(r)
        self.nova_state = ""

    def _report(self, r: VisitResult) -> None:
        if r.updated is None:
            print(yellow(f"  {r.person.name}: nothing stored (Gemini failed, or nothing new was said)"), flush=True)
            return
        print(green(f"  {r.person.name}: {len(r.new_facts)} new fact(s)"), flush=True)
        for fact in r.new_facts:
            print(f"    + {fact}", flush=True)
        print(f"    card: {r.updated.small_context}", flush=True)

    def idle_watch(self) -> None:
        """Ends a visit after a long silence."""
        while not self.stop.wait(5.0):
            with self.visit_lock:
                quiet = time.time() - self.visit.last_line if self.visit.lines else 0.0
            if quiet > self.args.visit_timeout:
                self.end_visit(f"{self.args.visit_timeout:.0f}s of silence")

    def on_key(self, key: str) -> None:
        if key == "e":
            threading.Thread(target=self.end_visit, args=("you asked",), daemon=True).start()
        elif key == "w":
            self.say(self.presence.who_answer())


def run(args) -> int:
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(name)s: %(message)s")
    logging.getLogger("httpx2").setLevel(logging.WARNING)
    load_env()
    try:
        pool = open_pool(args.database_url)
    except DatabaseUnavailable as e:
        print(red(f"error: {e}"), file=sys.stderr)
        return 1
    try:
        print(dim("loading the face and voice models..."), flush=True)
        from embedders.face import FaceRecEmbedder
        from embedders.voice import VoiceRecEmbedder
        from facerec import FaceConfig

        face = FaceRecEmbedder(config=FaceConfig(upsample=args.face_upsample))
        voice = VoiceRecEmbedder()
        with pool.connection() as conn:
            check_embedders(conn, face.spec, voice.spec)
            user = store.find_user(conn)
            known = people.list_people(conn)
        user_name = args.user or (user.name if user else "User")
        session = Session(args, pool, user_name, user.id if user else None)
        others = ", ".join(f"{p.name} ({p.relationship})" for p in known if not store.is_user_relationship(p.relationship)) or "none yet"
        print(bold("Nametags live") + dim(f"  user: {user_name}" + ("" if user else " (not registered; enroll --user to name their voice)") + f"  people: {others}"))

        listening = not args.no_mic or args.audio_file is not None
        transcriber = None
        if listening and not args.no_transcribe:
            from voice_rec.transcriber import Transcriber

            try:
                transcriber = Transcriber()
            except FileNotFoundError as e:
                print(yellow(f"no transcription: {e}"), flush=True)

        from live.nova import NovaBrain, make_speaker

        session.speaker = make_speaker(not args.no_tts, args.tts_voice, say=lambda t: None)
        if transcriber is not None and not args.no_summary:
            from backend import gemini

            gemini.load_env()
            session.gemini = bool(os.environ.get("GEMINI_API_KEY"))
            if not session.gemini:
                print(yellow("no GEMINI_API_KEY in the environment or .env: visits won't be summarized"), flush=True)
        if not args.no_nova and transcriber is not None:
            if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
                import anthropic

                session.client = anthropic.Anthropic()
            else:
                print(yellow("no ANTHROPIC_API_KEY in the environment or .env: no Nova"), flush=True)
        if session.client is not None and not args.no_nova:
            from voice_rec.assistant import Assistant, WakeWord

            brain = NovaBrain(session.client, pool, session.presence, args.nova_name, user_name, args.model)
            session.assistant = Assistant(
                args.nova_name,
                brain,
                session.speaker,
                WakeWord(args.nova_name, aliases=("nova", "nover", "novah")),
                on_say=lambda kind, text: _nova_said(session, kind, text),
                on_note=lambda text: print(dim(f"  {text}"), flush=True),
                ack=not args.no_tts,
            )

        listener = None
        if listening:
            from live.voices import VoiceIdentifier, VoiceListener

            listener = VoiceListener(
                VoiceIdentifier(voice, pool, args.voice_margin, presence=session.presence),
                transcriber,
                session.on_utterance,
                device=args.mic,
                on_level=session.on_level,
                source=args.audio_file,
                speed=args.audio_speed,
                on_end=session.stop.set,
            )
            listener.start()

        def check_listener() -> None:
            if listener is not None and listener.error is not None:
                raise listener.error
        threading.Thread(target=session.idle_watch, daemon=True).start()

        print(dim("Talk, or say the wake word and ask. In the window: q quits, e ends the visit, w asks who is here. Ctrl-C quits too.\n"), flush=True)
        try:
            if args.no_camera:
                while not session.stop.is_set():
                    check_listener()
                    time.sleep(0.2)
            else:
                from live.faces import FaceIdentifier, FaceWatcher

                watcher = FaceWatcher(face, FaceIdentifier(face, pool, args.face_margin), session.presence, source=args.camera, rate=args.face_rate)
                watcher.run(
                    session.stop,
                    session.overlay,
                    session.on_key,
                    on_arrival=lambda text, person: (session.say(text), _note_present(session, person)),
                    on_unknown=lambda text: session.say(text),
                    on_tick=check_listener,
                )
        except KeyboardInterrupt:
            print()
        finally:
            session.stop.set()
            if listener is not None:
                listener.stop_event.set()
                listener.join(timeout=5)
            session.end_visit("the session ended")
            if session.assistant is not None:
                session.assistant.wait_idle(timeout=15)
            if session.logfile is not None:
                session.logfile.close()
        return 0
    finally:
        pool.close()


def _note_present(session: Session, person) -> None:
    with session.visit_lock:
        session.visit.note(person)


def _nova_said(session: Session, kind: str, text: str) -> None:
    if kind == "answer":
        print(f"{dim(time.strftime('%H:%M:%S'))}  {bold(session.args.nova_name)}: {text}", flush=True)
        session.lines.append(f"{session.args.nova_name}: {text}")
        session.nova_state = ""
    elif kind == "sentence" and not session.nova_state:
        session.nova_state = f"{session.args.nova_name} is answering..."


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except KeyboardInterrupt:
        return 130
    except (EmbedderMismatch, ImportError, RuntimeError, ValueError, OSError) as e:
        print(red(f"error: {e}"), file=sys.stderr)
        return 1
