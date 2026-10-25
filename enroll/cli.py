"""python -m enroll: register a person, with their face, voice and a few facts, in the database."""

import argparse
import math
import os
import sys
from pathlib import Path

import psycopg

from db import people
from db.connect import DEFAULT_URL, EmbedderMismatch, apply_schema, check_embedders
from db.errors import Conflict, NotFound
from enroll import store
from voice_rec.config import DEFAULT_EMBED_MODEL

NAME_MAX, RELATIONSHIP_MAX = 80, 40  # the people table's checks, and PersonIn's
DEFAULT_POSES = "front,left,right,up,down"
USE_COLOR = sys.stdout.isatty()

EXAMPLES = """\
examples:
  python -m enroll --user "Rose"
      registers the person wearing the glasses: records their voice, asks for a few facts
  python -m enroll "David" grandson
      registers a relative: asks whether to take photos, records 10 s of speech, asks for a few facts
  python -m enroll "David" grandson --photo d1.jpg d2.jpg --audio david.wav --context "He is a nurse."
      the same from files, no camera or microphone
  python -m enroll --list
"""


def _c(code: str, s: str) -> str:
    return f"\x1b[{code}m{s}\x1b[0m" if USE_COLOR else s


def bold(s): return _c("1", s)
def dim(s): return _c("2", s)
def green(s): return _c("32", s)
def yellow(s): return _c("33", s)
def red(s): return _c("31", s)


def say(text: str = "") -> None:
    print(text, flush=True)


def warn(text: str) -> None:
    print(yellow(text), flush=True)


def die(text: str, code: int = 1) -> int:
    print(red(f"error: {text}"), file=sys.stderr, flush=True)
    return code


def ask(prompt: str) -> str:
    return input(f"{prompt}: ").strip()


def confirm(prompt: str, default: bool = True) -> bool:
    answer = input(f"{prompt} [{'Y/n' if default else 'y/N'}] ").strip().lower()
    return default if not answer else answer in ("y", "yes")


def read_lines() -> str:
    """Lines typed until an empty one."""
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if not line.strip():
            break
        lines.append(line)
    return "\n".join(lines)


class StatusLine:
    """One terminal line rewritten in place; clear() it before printing anything else."""

    def __init__(self):
        self._width = 0

    def show(self, text: str) -> None:
        sys.stdout.write("\r" + text.ljust(self._width))
        sys.stdout.flush()
        self._width = max(self._width, len(text))

    def clear(self) -> None:
        if self._width:
            sys.stdout.write("\r" + " " * self._width + "\r")
            sys.stdout.flush()
            self._width = 0


def bar(fraction: float, width: int = 30) -> str:
    filled = int(round(max(0.0, min(1.0, fraction)) * width))
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def level(rms_value: float, width: int = 12) -> str:
    db = 20 * math.log10(max(rms_value, 1e-6))
    filled = int(round(max(0.0, min(1.0, (db + 50) / 50)) * width))
    return "|" * filled + "." * (width - filled)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m enroll",
        description="Register a person for Nametags: their face (optional), their voice, and a few facts.",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("name", nargs="?", help="the person's name (asked for if missing)")
    p.add_argument("relationship", nargs="?", help="who they are to the user: son, daughter, friend (asked for if missing)")
    p.add_argument("--user", action="store_true", help="register the user of the app, the person wearing the glasses: no relationship, and no photos unless --face or --photo is given")
    p.add_argument("-y", "--yes", action="store_true", help="never ask: add to an existing person, skip the webcam unless --face is given")
    p.add_argument("--list", action="store_true", help="show who is enrolled and exit")

    face = p.add_argument_group("face (optional)")
    face.add_argument("--face", action="store_true", help="take photos with the webcam without asking")
    face.add_argument("--skip-face", action="store_true", help="no photos")
    face.add_argument("--photo", type=Path, nargs="+", metavar="FILE", help="enroll from these JPEG or PNG files instead of the webcam")
    face.add_argument("--poses", default=DEFAULT_POSES, help="head poses to photograph, comma-separated (default: %(default)s)")
    face.add_argument("--shots", type=int, default=1, help="photos per pose (default: %(default)s)")
    face.add_argument("--camera", default="0", help="camera index or video source (default: %(default)s)")
    face.add_argument("--no-window", action="store_true", help="no pop-up windows: photos are taken as soon as a face holds still, and the recording runs in the terminal")

    voice = p.add_argument_group("voice")
    voice.add_argument("--skip-voice", action="store_true", help="no recording")
    voice.add_argument("--audio", type=Path, metavar="FILE", help="enroll from this recording (WAV, FLAC, OGG...) instead of the microphone")
    voice.add_argument("--seconds", type=float, default=10.0, help="seconds of speech to collect (default: %(default)s)")
    voice.add_argument("--mic", help="input device index or name substring (default: the system default)")
    voice.add_argument("--window", type=float, default=4.0, help="also store each WINDOW-second slice as its own sample; 0 keeps only the whole recording (default: %(default)s)")
    voice.add_argument("--voice-model", default=DEFAULT_EMBED_MODEL, metavar="ONNX", help="speaker model (default: TitaNet small, 192 numbers)")

    ctx = p.add_argument_group("context")
    ctx.add_argument("--context", metavar="TEXT", help="facts about the person, a sentence each")
    ctx.add_argument("--context-file", type=Path, metavar="FILE", help="read the facts from this text file")
    ctx.add_argument("--no-context", action="store_true", help="don't ask for facts")

    where = p.add_argument_group("where")
    where.add_argument("--database-url", default=os.environ.get("DATABASE_URL", DEFAULT_URL), help="(default: $DATABASE_URL or %(default)s)")
    where.add_argument("--data-dir", type=Path, default=Path(os.environ.get("NAMETAGS_DATA", "data")), help="photos and recordings go under here, where the backend keeps its own (default: $NAMETAGS_DATA or %(default)s)")
    return p


def connect(url: str) -> psycopg.Connection:
    try:
        conn = psycopg.connect(url, autocommit=True, connect_timeout=5)
    except psycopg.OperationalError as e:
        raise RuntimeError(
            f"can't reach Postgres at {url}: {str(e).strip()}\nStart it with: docker compose up -d --wait db"
        ) from None
    apply_schema(conn)
    return conn


def list_people(conn: psycopg.Connection) -> int:
    rows = people.list_people(conn)
    if not rows:
        say(dim("nobody is enrolled yet"))
        return 0
    say(bold(f"{'id':>3}  {'name':<20} {'relationship':<14} {'faces':>5}  {'voice':<5}  card"))
    for p in sorted(rows, key=lambda p: (not store.is_user_relationship(p.relationship), p.id)):
        voice = "yes" if p.has_voice else "no"
        relationship = "* user" if store.is_user_relationship(p.relationship) else p.relationship
        say(f"{p.id:>3}  {p.name:<20} {relationship:<14} {p.face_count:>5}  {voice:<5}  {p.small_context}")
    if store.find_user(conn) is None:
        warn("no app user yet; register them with: python -m enroll --user NAME")
    else:
        say(dim("* the user of the app, the person wearing the glasses"))
    return 0


def choose_user_mode() -> bool:
    say("Who are you registering?")
    say("  1. the user of the app, the person wearing the glasses")
    say("  2. a relative or friend of the user")
    return ask("1 or 2") == "1"


def enroll_faces(conn, args, person, face, interactive: bool) -> None:
    images: list[tuple[str, bytes]] = []
    if args.photo:
        images = [(path.name, path.read_bytes()) for path in args.photo]
    elif args.skip_face:
        return
    else:
        if args.user and not args.face:
            return  # the glasses never see the wearer's face
        wanted = args.face or (interactive and confirm("Take photos with the webcam now? (optional)", default=True))
        if not wanted:
            return
        from enroll.camera import capture_poses

        poses = [p.strip() for p in args.poses.split(",") if p.strip()]
        say(bold("Photos") + dim("  a camera window opens: one photo per head pose, it says what to do"))
        shots = capture_poses(
            face.recognizer, poses=poses, shots_per_pose=args.shots, source=args.camera, display=not args.no_window, say=say
        )
        images = [(shot.pose, shot.jpeg) for shot in shots]
    if not images:
        warn("  no photos")
        return
    say(dim("  finding and encoding faces..."))
    for label, data in images:
        try:
            saved = store.save_photo_of(conn, args.data_dir, person.id, data, face)
        except ValueError as e:
            warn(f"  {label}: {e}")
            continue
        if saved is None:
            warn(f"  {label}: no face found, not stored")
        elif saved.face_id is None:
            warn(
                f"  {label}: {saved.faces_found} faces of similar size; stored as photo {saved.photo_id} "
                "with no label. Label it in the setup UI."
            )
        else:
            others = f"  ({saved.faces_found - 1} other face(s) left unlabelled)" if saved.faces_found > 1 else ""
            say(green(f"  {label}: face {saved.face_id} labelled in photo {saved.photo_id}") + dim(f"{others}  -> {saved.path}"))


def enroll_voice(conn, args, person, voice) -> None:
    from embedders.voice import encode_wav
    from enroll.mic import PASSAGE, TIPS, record_speech, speech_from_file, windows
    from voice_rec.config import SAMPLE_RATE

    if args.audio:
        speech = speech_from_file(args.audio)
        say(bold("Voice") + f"  {args.audio}: {len(speech) / SAMPLE_RATE:.1f}s of speech")
    elif not args.no_window:
        from enroll.voice_window import record_in_window

        say(bold("Voice") + dim(f"  a window opens: click the red button, read the passage, keep talking until the bar fills ({args.seconds:.0f}s of speech)"))
        speech = record_in_window(person.name, args.seconds, device=args.mic)
        if speech is None:
            warn("  recording cancelled; no voice stored")
            return
        say(f"  {len(speech) / SAMPLE_RATE:.1f}s of speech recorded")
    else:
        say(bold("Voice") + f"  need {args.seconds:.0f}s of speech; Ctrl-C stops early")
        say(dim("  " + TIPS))
        say(dim("  Read this, then keep talking:"))
        say(dim("  " + PASSAGE.format(name=person.name)))
        status = StatusLine()

        def show(progress: float, speaking: bool, rms_value: float) -> None:
            state = "speaking " if speaking else "listening"
            status.show(f"  {bar(progress)} {progress * 100:3.0f}%  {state} {level(rms_value)}")

        try:
            speech = record_speech(args.seconds, device=args.mic, show=show)
        finally:
            status.clear()
        say(f"  {len(speech) / SAMPLE_RATE:.1f}s of speech recorded")
    clips = [speech] + (windows(speech, args.window) if args.window > 0 else [])
    ids = [store.save_voice_of(conn, args.data_dir, person.id, encode_wav(clip), voice) for clip in clips]
    say(green(f"  stored {len(ids)} voice sample(s)") + dim(f"  ids {ids}  -> {args.data_dir / 'voice'}"))


def enroll_context(conn, args, person, interactive: bool) -> None:
    if args.no_context:
        return
    text = args.context
    if text is None and args.context_file:
        text = args.context_file.read_text()
    if text is None and interactive:
        say(bold("Context") + dim("  a few facts, a sentence each: who they are to the patient, what they do, what to talk about"))
        say(dim("  Finish with an empty line; an empty first line skips this."))
        text = read_lines()
    if not text or not text.strip():
        return
    if notes_via_claude(args.database_url, person.id, text):
        return
    updated = store.save_context_of(conn, person.id, text)
    say(green(f"  {len(store.split_facts(text))} fact(s) stored as typed") + dim(f"  card: {updated.small_context}"))


def notes_via_claude(database_url: str, person_id: int, text: str) -> bool:
    """Facts and a card the context owner's way (backend.context_ai), when ANTHROPIC_API_KEY is set.

    Returns False when Claude is off or added nothing, so the caller stores the notes as typed."""
    from backend import context_ai

    if not context_ai.configured():
        return False
    import psycopg_pool

    from db import context

    say(dim("  asking Claude to turn the notes into facts and a card..."))
    pool = psycopg_pool.ConnectionPool(database_url, min_size=1, max_size=2, open=True)
    try:
        with pool.connection() as c:
            before = {f.id for f in context.list_facts(c, person_id)}
        updated = context_ai.update_context(pool, person_id, text, "notes")
        with pool.connection() as c:
            added = [f.text for f in context.list_facts(c, person_id) if f.id not in before]
    finally:
        pool.close()
    if not added:
        warn("  Claude added nothing; storing the notes as typed")
        return False
    say(green(f"  {len(added)} fact(s) stored"))
    for fact in added:
        say(f"    + {fact}")
    say(dim(f"  card: {updated.small_context}"))
    return True


def run(args) -> int:
    interactive = sys.stdin.isatty() and not args.yes
    with connect(args.database_url) as conn:
        if args.list:
            return list_people(conn)
        if interactive and not (args.user or args.name or args.relationship):
            args.user = choose_user_mode()
        name = (args.name or (ask("Name") if interactive else "")).strip()
        if args.user:
            relationship = store.USER_RELATIONSHIP
        else:
            relationship = (args.relationship or (ask("Relationship to the user (son, daughter, friend...)") if interactive else "")).strip()
            args.user = store.is_user_relationship(relationship)  # "Rose user" means the same as --user
        if not 1 <= len(name) <= NAME_MAX:
            return die(f"the name must be 1-{NAME_MAX} characters")
        if not 1 <= len(relationship) <= RELATIONSHIP_MAX:
            return die(f"the relationship must be 1-{RELATIONSHIP_MAX} characters")

        say(dim("loading the face and voice models..."))
        from embedders.face import FaceRecEmbedder
        from embedders.voice import VoiceRecEmbedder
        from facerec.enroll import ENROLL_JITTERS

        face = FaceRecEmbedder(num_jitters=ENROLL_JITTERS)
        voice = VoiceRecEmbedder(model_path=str(args.voice_model))
        check_embedders(conn, face.spec, voice.spec)  # the tables must hold this size, from these models

        person = store.find_person(conn, name, relationship)
        if person is None:
            if not args.user and store.find_user(conn) is None:
                warn("no app user is registered yet; register them with: python -m enroll --user NAME")
            with conn.transaction():
                person = people.create_person(conn, name, relationship)
            if args.user:
                say(green(f"the app user, person {person.id}: {person.name}"))
            else:
                say(green(f"new person {person.id}: {person.name}, {person.relationship}"))
        else:
            has_voice = "yes" if person.has_voice else "no"
            say(f"{person.name}, {person.relationship} is already enrolled: {person.face_count} face(s), voice {has_voice}")
            if interactive and not confirm("Add these samples to them?", default=True):
                return 1
            say(dim(f"adding to person {person.id}"))

        enroll_faces(conn, args, person, face, interactive)
        if not args.skip_voice:
            enroll_voice(conn, args, person, voice)
        enroll_context(conn, args, person, interactive)

        person = people.get_person(conn, person.id)
        say()
        who = "the app user" if args.user else person.relationship
        say(bold("done") + f"  person {person.id}: {person.name}, {who}")
        say(f"  faces: {person.face_count}   voice: {'yes' if person.has_voice else 'no'}")
        if person.small_context:
            say(f"  card: {person.small_context}")
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except KeyboardInterrupt:
        print()
        return 130
    except (EmbedderMismatch, Conflict, NotFound, ImportError, RuntimeError, ValueError, OSError) as e:
        return die(str(e))
