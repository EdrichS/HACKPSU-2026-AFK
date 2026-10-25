"""Command-line interface: voicerec enroll | listen | identify | list | remove | matrix | devices | reset."""
from __future__ import annotations

import argparse
import json
import queue
import re
import shutil
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from . import __version__
from .audio import Microphone, list_input_devices, load_audio, resolve_device, rms
from .config import DB_PATH, DEFAULT_EMBED_MODEL, DEFAULT_THRESHOLD, SAMPLE_RATE
from .embedder import SpeakerEmbedder
from .recognizer import Match, MultiMatch, MultiRecognizer, Recognizer, separated_embeddings
from .separator import DEFAULT_SEP_MODEL
from .transcriber import DEFAULT_ASR_MODEL
from .store import SpeakerStore
from .vad import SpeechSegmenter, segment_audio

# --------------------------------------------------------------------------- terminal
USE_COLOR = sys.stdout.isatty()
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _c(code: str, s: str) -> str:
    return f"\x1b[{code}m{s}\x1b[0m" if USE_COLOR else s


def bold(s): return _c("1", s)
def dim(s): return _c("2", s)
def green(s): return _c("32", s)
def red(s): return _c("31", s)
def yellow(s): return _c("33", s)
def cyan(s): return _c("36", s)


def plain_len(s: str) -> int:
    return len(_ANSI.sub("", s))


def score_bar(score: float, width: int = 20) -> str:
    filled = int(round(max(0.0, min(1.0, score)) * width))
    return "█" * filled + "░" * (width - filled)


def level_bar(level: float, width: int = 12) -> str:
    db = 20 * np.log10(level + 1e-9)
    frac = max(0.0, min(1.0, (db + 60) / 60))
    n = int(round(frac * width))
    return "▮" * n + "▯" * (width - n)


class StatusLine:
    """A single rewritable line at the bottom of the output (progress, meters)."""

    def __init__(self):
        self.enabled = sys.stdout.isatty()
        self._len = 0

    def show(self, text: str) -> None:
        if not self.enabled:
            return
        cols = shutil.get_terminal_size((100, 20)).columns
        if plain_len(text) >= cols:
            text = text[: cols - 1]
        pad = max(0, self._len - plain_len(text))
        sys.stdout.write("\r" + text + " " * pad)
        sys.stdout.flush()
        self._len = plain_len(text)

    def clear(self) -> None:
        if self.enabled and self._len:
            sys.stdout.write("\r" + " " * self._len + "\r")
            sys.stdout.flush()
        self._len = 0

    def println(self, text: str = "") -> None:
        self.clear()
        print(text)
        sys.stdout.flush()


def fmt_match(m: Match, name_width: int = 12) -> str:
    if not m.ranked:
        return yellow("no speakers enrolled")
    guess, score = m.ranked[0]
    if m.is_known:
        label = green(bold(guess.ljust(name_width)))
    else:
        label = red(bold("Unknown".ljust(name_width)))
    line = f"{label} {score_bar(score)} {score:.2f}"
    if not m.is_known:
        line += dim(f"  closest: {guess}")
    if m.runner_up:
        line += dim(f"  next: {m.runner_up[0]} {m.runner_up[1]:.2f}")
    return line


def fmt_multi(mm: MultiMatch, name_width: int = 12) -> str:
    if mm.n_talkers <= 1:
        # one voice: the plain path has no separation artifacts, trust it
        return fmt_match(mm.mixture, name_width)
    parts = []
    for t in mm.talkers:
        label = green(bold(t.speaker)) if t.is_known else red(bold("Unknown"))
        parts.append(f"{label} {t.score:.2f}")
    return cyan(bold(f"{mm.n_talkers} talkers")) + "  " + dim(" + ").join(parts)


def fmt_any(result, name_width: int) -> str:
    return fmt_multi(result, name_width) if isinstance(result, MultiMatch) else fmt_match(result, name_width)


def fmt_debug(result) -> list[str]:
    """Extra lines for --debug: raw scores of the whole mix (highest first), the winner's
    lead in the centered space, then the same for each separated stream."""
    def rank(r, lead=None):
        body = ", ".join(f"{n} {s:.2f}" for n, s in sorted(r, key=lambda x: -x[1])[:4])
        return body + (f"   lead {lead:+.2f}" if lead is not None else "")
    if isinstance(result, MultiMatch):
        m = result.mixture
        lines = [dim(f"      whole mix: {rank(m.ranked, m.margin)}  -> {m.speaker or 'Unknown'}")]
        for i, d in enumerate(result.details, 1):
            body = rank(d["ranked"]) if d["ranked"] else "-"
            lines.append(dim(f"      stream {i} ({d['share']:.0%}): {body}  -> {d['note']}"))
        return lines
    return [dim(f"      ranking: {rank(result.ranked, result.margin)}")]


def transcribe_result(transcriber, result, samples: np.ndarray) -> str:
    """Fill in text for a Match (whole utterance) or a MultiMatch (one per talker).
    Returns the one-line transcript used for the log file."""
    if isinstance(result, MultiMatch) and result.n_talkers >= 2:
        parts = []
        for tk in result.talkers:
            tk.text = transcriber.transcribe(tk.audio if tk.audio is not None else samples)
            parts.append(f"{tk.speaker or 'Unknown'}: {tk.text}")
        return " | ".join(parts)
    text = transcriber.transcribe(samples)
    if isinstance(result, MultiMatch):
        for tk in result.talkers:
            tk.text = text
        who = result.talkers[0].speaker if result.talkers else None
    else:
        result.text = text  # type: ignore[attr-defined]
        who = result.speaker
    return f"{who or 'Unknown'}: {text}"


def fmt_transcript(result, indent: int) -> list[str]:
    pad = " " * indent
    if isinstance(result, MultiMatch) and result.n_talkers >= 2:
        out = []
        for tk in result.talkers:
            name = green(tk.speaker) if tk.is_known else red("Unknown")
            out.append(f"{pad}{name}: {tk.text or dim('(nothing recognised)')}")
        return out
    text = result.talkers[0].text if isinstance(result, MultiMatch) and result.talkers else getattr(result, "text", None)
    return [f"{pad}{cyan('“' + text + '”') if text else dim('(nothing recognised)')}"]


def fmt_time(ts) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else "-"


def die(msg: str, code: int = 1) -> int:
    print(red("error: ") + msg, file=sys.stderr)
    return code


# --------------------------------------------------------------------------- setup
def build(args) -> tuple[SpeakerEmbedder, SpeakerStore]:
    embedder = SpeakerEmbedder(args.model, num_threads=args.threads)
    sep_model = args.sep_model if getattr(args, "multi", False) else None
    store = SpeakerStore(Path(args.db), embedder.model_name, embedder.dim, sep_model=sep_model)
    if store.sep_model_mismatch:
        print(yellow(f"note: separation profiles in {store.path} were made with {store.sep_model_mismatch}; "
                     f"ignoring them for {sep_model}. Re-enroll with --multi to rebuild."), file=sys.stderr)
    return embedder, store


def name_width(store: SpeakerStore) -> int:
    return max([len(n) for n in store.names()] + [len("Unknown")]) + 1


def build_recognizer(args, embedder: SpeakerEmbedder, store: SpeakerStore) -> Recognizer:
    if getattr(args, "no_rescue", False):
        return Recognizer(embedder, store, args.threshold, rescue_margin=9.0, rescue_floor=0.0)
    return Recognizer(embedder, store, args.threshold)


def build_multi(args, rec: Recognizer) -> MultiRecognizer:
    from .separator import SpeechSeparator

    sep = SpeechSeparator(args.sep_model, device=args.sep_device)
    return MultiRecognizer(rec, sep, stream_threshold=args.stream_threshold)


# The Rainbow Passage: the standard phonetically balanced reading text used in speech
# research. The words matter far less than the amount of speech and the recording
# conditions, but this covers every English sound in about 35 seconds of reading.
ENROLL_TEXT = (
    "Hi, my name is {name}. When the sunlight strikes raindrops in the air, they act as a "
    "prism and form a rainbow. The rainbow is a division of white light into many beautiful "
    "colors. These take the shape of a long round arch, with its path high above, and its two "
    "ends apparently beyond the horizon. There is, according to legend, a boiling pot of gold "
    "at one end. People look, but no one ever finds it. When a man looks for something beyond "
    "his reach, his friends say he is looking for the pot of gold at the end of the rainbow."
)
ENROLL_TIPS = (
    "Tips: sit where you will sit during the demo, at the same distance from the laptop. "
    "After the passage, just keep talking naturally (about your project, your day) until the "
    "bar fills. Reading voice and talking voice differ, and the system will hear the latter."
)


# --------------------------------------------------------------------------- commands
def cmd_devices(args) -> int:
    devs = list_input_devices()
    if not devs:
        return die("no input devices found")
    print(bold("Input devices") + dim("  (pass --device INDEX or --device 'name substring')"))
    for d in devs:
        mark = green("*") if d["default"] else " "
        print(f" {mark} [{d['index']}] {d['name']}  {dim(str(int(d['default_samplerate'])) + ' Hz')}")
    return 0


def _summarize_enrollment(store: SpeakerStore, name: str, threshold: float) -> None:
    samples = store.samples(name)
    centroid = store.centroid(name)
    sims = samples @ centroid
    print(f"  samples: {len(samples)}   self-consistency: min {sims.min():.2f}  mean {sims.mean():.2f}")
    others = [n for n in store.names() if n != name]
    if others:
        _, C = store.centroids()
        idx = {n: i for i, n in enumerate(store.names())}
        close = sorted(((float(C[idx[o]] @ centroid), o) for o in others), reverse=True)
        s, o = close[0]
        # What matters is the gap between how this person scores against themselves and
        # how close the nearest other person is; under ~0.25 they will get mixed up.
        gap = float(sims.mean()) - s
        warn = yellow(f"  <- only {gap:.2f} below their self-score; enroll both in demo conditions") if gap < 0.25 else dim(f"  (gap {gap:.2f}, fine)")
        print(f"  most similar enrolled speaker: {o} ({s:.2f}){warn}")


def cmd_enroll(args) -> int:
    embedder, store = build(args)
    name = args.name.strip()
    if not name:
        return die("name must not be empty")
    if name in store and not args.replace:
        print(dim(f"{name} already enrolled with {store.info(name)['samples']} samples; adding more (use --replace to start over)"))

    utterances: list[np.ndarray] = []  # VAD-trimmed speech, one array per utterance
    if args.from_files:
        for f in args.from_files:
            audio = load_audio(f)
            segs = [s for s in segment_audio(audio) if s.duration >= 1.0]
            if not segs:
                print(yellow(f"  {f}: no speech found, skipped"))
                continue
            utterances += [s.samples for s in segs]
            print(f"  {f}: {sum(s.duration for s in segs):.1f}s of speech in {len(segs)} utterances")
    else:
        try:
            device = resolve_device(args.device)
        except ValueError as e:
            return die(str(e))
        target = float(args.seconds)
        text = ENROLL_TEXT
        if args.text:
            path = Path(args.text)
            text = path.read_text().strip() if path.is_file() else args.text
        print(bold(f"Enrolling {name}") + f"  (need ~{target:.0f}s of speech; Ctrl-C to stop early)")
        print(dim(ENROLL_TIPS))
        print(dim("Read this, then keep talking:"))
        print(dim("  “" + text.format(name=name) + "”"))
        print()
        seg = SpeechSegmenter(min_silence=0.4, max_speech=8.0)
        status = StatusLine()
        total = 0.0
        try:
            with Microphone(device) as mic:
                for chunk in mic.chunks():
                    for s in seg.feed(chunk):
                        if s.duration < 0.8:
                            continue
                        utterances.append(s.samples)
                        total += s.duration
                        status.println(dim(f"  + {s.duration:.1f}s utterance"))
                    live = seg.current_speech()
                    progress = min(1.0, (total + len(live) / SAMPLE_RATE) / target)
                    state = green("speaking ") if seg.is_speech else dim("listening")
                    status.show(f"  {score_bar(progress, 30)} {progress*100:3.0f}%  {state} {level_bar(rms(chunk))}")
                    if total >= target:
                        break
                for s in seg.flush():
                    if s.duration >= 0.8:
                        utterances.append(s.samples)
                        total += s.duration
        except KeyboardInterrupt:
            status.clear()
            for s in seg.flush():
                if s.duration >= 0.8:
                    utterances.append(s.samples)
                    total += s.duration
            if total < 3.0:
                print(yellow(f"\nstopped with only {total:.1f}s of speech; nothing saved"))
                return 1
            print(yellow(f"\nstopped early with {total:.1f}s of speech; saving what we have"))
        status.clear()
        print(f"  captured {total:.1f}s of speech in {len(utterances)} utterances")

    if not utterances:
        return die("no speech detected")
    speech = np.concatenate(utterances)
    embeddings = [embedder.embed(u) for u in utterances] + [embedder.embed(speech)]
    win = 3 * SAMPLE_RATE  # extra 3 s windows give the centroid more, varied support
    for i in range(0, len(speech) - win + 1, win):
        embeddings.append(embedder.embed(speech[i : i + win]))

    sep_embeddings: list[np.ndarray] = []
    if args.multi:
        from .separator import SpeechSeparator

        print(dim("  building separation-domain voiceprint ..."), flush=True)
        sep = SpeechSeparator(args.sep_model, device=args.sep_device)
        store.sep_model = sep.source
        sep_embeddings = separated_embeddings(embedder, sep, utterances)

    store.add(name, embeddings, replace=args.replace, sep_embeddings=sep_embeddings)
    extra = f", {len(sep_embeddings)} separation-domain" if sep_embeddings else ""
    print(green(bold(f"enrolled {name}")) + dim(f"  -> {store.path}  ({len(embeddings)} embeddings{extra})"))
    _summarize_enrollment(store, name, args.threshold)
    return 0


def cmd_listen(args) -> int:
    embedder, store = build(args)
    if len(store) == 0:
        return die("no speakers enrolled yet. Run: voicerec enroll \"Your Name\"")
    try:
        device = resolve_device(args.device)
    except ValueError as e:
        return die(str(e))
    rec = build_recognizer(args, embedder, store)
    seg = SpeechSegmenter(min_silence=args.min_silence, max_speech=args.max_speech)
    width = name_width(store)
    jsonl = args.jsonl
    status = StatusLine()
    lock = threading.Lock()

    multi = None
    if args.multi:
        if not jsonl:
            print(dim("loading separation model ..."), flush=True)
        multi = build_multi(args, rec)
        if not store.has_sep_profiles():
            print(yellow("note: some speakers have no separation-domain voiceprint; re-enroll them with "
                         "`voicerec enroll NAME --multi` for better results with simultaneous talkers"), file=sys.stderr)
    identify = multi.identify if multi else rec.identify
    transcriber = None
    if args.transcribe:
        from .transcriber import Transcriber

        transcriber = Transcriber(args.asr_model, num_threads=args.threads)
    log = open(args.log, "a", encoding="utf-8") if args.log else None
    partial_window = int(args.partial_window * SAMPLE_RATE)
    partial_every = args.partial_every if args.partial_every is not None else (1.5 if multi else 0.75)
    mic = Microphone(device)

    def emit(kind: str, result, start: float, duration: float, transcript: str | None = None) -> None:
        wall_start = (mic.started_at or time.time()) + start
        with lock:
            if jsonl:
                ev = {"type": kind, "start": round(start, 2), "duration": round(duration, 2),
                      "wall_start": round(wall_start, 3), "ts": time.time()}
                if isinstance(result, MultiMatch):
                    ev.update(result.mixture.to_dict())  # keep the single-speaker fields for older consumers
                    ev.update(result.to_dict())
                    ev["speakers"] = result.names
                else:
                    ev.update(result.to_dict())
                if transcript is not None:
                    ev["text"] = transcript if isinstance(result, MultiMatch) and result.n_talkers >= 2 else getattr(result, "text", None) or (result.talkers[0].text if isinstance(result, MultiMatch) and result.talkers else "")
                print(json.dumps(ev), flush=True)
            elif kind == "final":
                stamp = dim(time.strftime("%H:%M:%S", time.localtime(wall_start)))
                status.println(f"{stamp} {fmt_any(result, width)} {dim(f'{duration:.1f}s')}")
                if transcript is not None:
                    for line in fmt_transcript(result, indent=9):
                        status.println(line)
                if args.debug:
                    for line in fmt_debug(result):
                        status.println(line)
            else:
                status.show(f"{dim('…')}        {fmt_any(result, width)}")

    # Identification runs on a worker thread so the microphone loop never falls behind.
    jobs: "queue.Queue[tuple | None]" = queue.Queue()
    busy = threading.Event()

    def worker() -> None:
        while True:
            job = jobs.get()
            if job is None:
                return
            kind, samples, start, duration = job
            busy.set()
            try:
                result = identify(samples)
                transcript = transcribe_result(transcriber, result, samples) if (transcriber and kind == "final") else None
            except ValueError:
                continue
            finally:
                busy.clear()
            emit(kind, result, start, duration, transcript)
            if log is not None and kind == "final" and transcript is not None:
                wall_start = (mic.started_at or time.time()) + start
                log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(wall_start))}  {transcript}\n")
                log.flush()

    def submit(kind: str, samples: np.ndarray, start: float, duration: float) -> None:
        if kind == "partial":
            if busy.is_set() or not jobs.empty():
                return  # never queue up stale provisional guesses
            if multi:
                samples = samples[-partial_window:]
        jobs.put((kind, samples, start, duration))

    threading.Thread(target=worker, daemon=True).start()

    if not jsonl:
        mode = f"  separation={multi.sep.source} on {multi.sep.device}  stream-threshold={multi.stream_threshold:.2f}" if multi else ""
        asr = f"  transcription={transcriber.kind}" if transcriber else ""
        print(bold("voicerec listen") + dim(f"  model={embedder.model_name}  threshold={args.threshold:.2f}{mode}{asr}"))
        print(dim("speakers: ") + ", ".join(store.names()))
        print(dim("Talk. Ctrl-C to stop.\n"))

    last_partial = 0.0
    last_meter = 0.0
    try:
        with mic:
            for chunk in mic.chunks():
                for s in seg.feed(chunk):
                    if s.duration >= args.min_utterance:
                        submit("final", s.samples, s.start, s.duration)
                now = time.time()
                if seg.is_speech:
                    live = seg.current_speech()
                    if len(live) >= args.max_speech * SAMPLE_RATE:
                        # Silero only *tries* to end long segments; force a decision and start over.
                        submit("final", live, seg.current_start(), len(live) / SAMPLE_RATE)
                        seg.reset()
                        last_partial = now
                    elif now - last_partial >= partial_every:
                        if len(live) >= 1.0 * SAMPLE_RATE:
                            submit("partial", live, seg.current_start(), len(live) / SAMPLE_RATE)
                        last_partial = now
                elif not jsonl and now - last_meter >= 0.1 and not busy.is_set():
                    with lock:
                        status.show(f"{dim('listening')} {level_bar(rms(chunk))}")
                    last_meter = now
    except KeyboardInterrupt:
        pass
    for s in seg.flush():
        if s.duration >= args.min_utterance:
            submit("final", s.samples, s.start, s.duration)
    jobs.put(None)
    for th in threading.enumerate():
        if th.name.startswith("Thread") and th is not threading.main_thread():
            th.join(timeout=30)
    with lock:
        status.clear()
    if log is not None:
        log.close()
    if mic.overflows and not jsonl:
        print(yellow(f"warning: {mic.overflows} audio buffer overflows; some audio was lost"))
    if not jsonl:
        print(dim("\nbye"))
    return 0


def cmd_identify(args) -> int:
    embedder, store = build(args)
    if len(store) == 0:
        return die("no speakers enrolled yet")
    rec = build_recognizer(args, embedder, store)
    multi = build_multi(args, rec) if args.multi else None
    identify = multi.identify if multi else rec.identify
    transcriber = None
    if args.transcribe:
        from .transcriber import Transcriber

        transcriber = Transcriber(args.asr_model, num_threads=args.threads)
    width = name_width(store)
    rc = 0
    for f in args.files:
        try:
            audio = load_audio(f)
        except Exception as e:  # noqa: BLE001
            print(f"{f}: " + red(f"cannot read ({e})"))
            rc = 1
            continue
        segs = [s for s in segment_audio(audio) if s.duration >= args.min_utterance]
        if not segs:
            print(f"{f}: " + yellow("no speech found"))
            continue
        speech = np.concatenate([s.samples for s in segs])
        m = identify(speech)
        transcript = transcribe_result(transcriber, m, speech) if transcriber else None
        if args.jsonl:
            ev = {"file": str(f), "duration": round(len(speech) / SAMPLE_RATE, 2)}
            if isinstance(m, MultiMatch):
                ev.update(m.mixture.to_dict())
                ev.update(m.to_dict())
                ev["speakers"] = m.names
            else:
                ev.update(m.to_dict())
            if transcript is not None:
                ev["text"] = transcript
            print(json.dumps(ev))
        else:
            print(f"{cyan(str(f))}  {dim(f'{len(speech)/SAMPLE_RATE:.1f}s speech')}")
            print(f"  {fmt_any(m, width)}")
            if transcript is not None:
                for line in fmt_transcript(m, indent=4):
                    print(line)
            if args.debug:
                for line in fmt_debug(m):
                    print(line)
            if args.segments:
                for s in segs:
                    sm = identify(s.samples)
                    st = transcribe_result(transcriber, sm, s.samples) if transcriber else None
                    print(f"    {dim(f'{s.start:6.2f}s +{s.duration:4.1f}s')}  {fmt_any(sm, width)}")
                    if st is not None:
                        for line in fmt_transcript(sm, indent=8):
                            print(line)
    return rc


def cmd_list(args) -> int:
    _, store = build(args)
    if len(store) == 0:
        print(dim("no speakers enrolled"))
        return 0
    print(bold(f"{'name':<16} {'samples':>7} {'sep':>4}  {'consistency':>11}  {'enrolled':<16} {'updated':<16}"))
    for n in store.names():
        info = store.info(n)
        sims = store.samples(n) @ store.centroid(n)
        print(f"{n:<16} {info['samples']:>7} {info['sep_samples']:>4}  {sims.mean():>11.2f}  {fmt_time(info['created']):<16} {fmt_time(info['updated']):<16}")
    print(dim(f"\n{store.path}  model={store.model_name}"))
    return 0


def cmd_remove(args) -> int:
    _, store = build(args)
    if store.remove(args.name):
        print(f"removed {args.name}")
        return 0
    return die(f"{args.name!r} is not enrolled")


def cmd_reset(args) -> int:
    if not args.yes:
        return die("this deletes every enrolled speaker; re-run with --yes to confirm")
    path = Path(args.db)
    if path.exists():
        path.unlink()
        print(f"deleted {path}")
    else:
        print(dim("nothing to delete"))
    return 0


def cmd_matrix(args) -> int:
    _, store = build(args)
    names, C = store.centroids()
    if len(names) < 2:
        return die("need at least two enrolled speakers")
    S = C @ C.T
    self_score = {n: float((store.samples(n) @ store.centroid(n)).mean()) for n in names}
    w = max(len(n) for n in names) + 1
    print(bold("cosine similarity between enrolled speakers") + dim("  (diagonal: how each person scores against their own profile)"))
    print(" " * w + "".join(f"{n[:7]:>8}" for n in names))
    pairs = []
    for i, n in enumerate(names):
        row = ""
        for j in range(len(names)):
            v = self_score[n] if i == j else S[i, j]
            gap = min(self_score[names[i]], self_score[names[j]]) - v
            cell = f"{v:8.2f}"
            if i != j:
                pairs.append((gap, v, names[i], names[j]))
                if gap < 0.15:
                    cell = red(cell)
                elif gap < 0.25:
                    cell = yellow(cell)
            row += cell
        print(f"{n:<{w}}{row}")
    gap, v, a, b = min(pairs)
    verdict = red("will be confused") if gap < 0.15 else (yellow("close: enroll both in demo conditions") if gap < 0.25 else green("well separated"))
    print(f"\nclosest pair: {a} / {b} = {v:.2f}, {gap:.2f} below their self-scores  {verdict}")
    return 0


# --------------------------------------------------------------------------- cloud streaming
def _cloud_key(args) -> str | None:
    from .cloud import api_key_from_env

    key = args.api_key or api_key_from_env()
    if not key:
        die("a Speechmatics API key is needed: export SPEECHMATICS_API_KEY=... (free tier at portal.speechmatics.com) or pass --api-key")
    return key


def _cloud_error(e: Exception) -> int:
    reason = str(e) or type(e).__name__
    hint = ""
    if "quota" in reason.lower():
        hint = " (another session is still open on this key; free accounts allow very few at once. Wait ~10 s and retry, and make sure no other `voicerec live` is running)"
    elif "auth" in reason.lower() or "401" in reason or "403" in reason:
        hint = " (check the key in .env)"
    return die(f"Speechmatics: {reason}{hint}")


def _install_sigint(stop: dict):
    """First Ctrl-C asks the stream to finish cleanly (so the last words arrive); second one kills."""
    import signal

    previous = signal.getsignal(signal.SIGINT)

    def handler(signum, frame):
        if stop["flag"]:
            raise KeyboardInterrupt
        stop["flag"] = True

    signal.signal(signal.SIGINT, handler)
    return lambda: signal.signal(signal.SIGINT, previous)


def _cloud_defaults(args, assistant_mode: bool = False) -> None:
    from .cloud import CLOUD_DB, DEFAULT_URL

    args.url = args.url or DEFAULT_URL
    args.cloud_db = args.cloud_db or str(CLOUD_DB)
    if args.max_delay is None:
        args.max_delay = 0.7 if assistant_mode else 1.0
    if getattr(args, "eou", None) is None and assistant_mode:
        args.eou = 0.5


def cmd_live(args) -> int:
    return _live(args)


def _live(args, assistant=None) -> int:
    import asyncio

    from .cloud import CloudSpeakerStore, LabelNamer, LiveSession, file_blocks, mic_blocks

    _cloud_defaults(args, assistant_mode=assistant is not None)
    key = _cloud_key(args)
    if not key:
        return 1
    cloud_store = CloudSpeakerStore(Path(args.cloud_db))
    known = [] if args.no_cloud_speakers else cloud_store.known_speakers()

    namer = None
    local_names: list[str] = []
    if not args.no_local_naming:
        try:
            embedder, store = build(args)
            if len(store):
                namer = LabelNamer(build_recognizer(args, embedder, store))
                local_names = store.names()
        except (FileNotFoundError, RuntimeError) as e:
            print(yellow(f"local naming off: {e}"), file=sys.stderr)

    jsonl = args.jsonl
    status = StatusLine()
    lock = threading.Lock()
    log = open(args.log, "a", encoding="utf-8") if args.log else None
    palette = {}
    colors = ["32", "36", "35", "33", "34", "92", "96", "95"]

    def paint(name: str) -> str:
        if name.startswith("Speaker ") or name == "Unknown":
            return _c("2", name)
        if name not in palette:
            palette[name] = colors[len(palette) % len(colors)]
        return _c(palette[name], bold(name))

    session: LiveSession | None = None

    def wall(t: float) -> float:
        return session.wall(t) if session else time.time()

    def hook(fn, *a) -> None:
        """Assistant hooks must never take the transcript down with them."""
        try:
            fn(*a)
        except Exception as e:  # noqa: BLE001
            print(yellow(f"assistant error: {type(e).__name__}: {e}"), file=sys.stderr)

    def on_partial(name: str, text: str) -> None:
        if assistant is not None:
            hook(assistant.on_partial, name, text)
            if assistant.is_echo_partial(text):
                return  # my own voice, provisionally transcribed: not worth showing
        if args.no_partials:
            return
        if jsonl:
            print(json.dumps({"type": "partial", "speaker": None if name.startswith("Speaker ") or name == "Unknown" else name, "display": name, "text": text, "ts": time.time()}), flush=True)
        else:
            status.show(f"{dim('…')} {paint(name)}: {text}")

    def on_turn(turn, name: str) -> None:
        generic = name.startswith("Speaker ") or name == "Unknown"
        if assistant is not None and assistant.is_echo(turn.text, wall(turn.start), wall(turn.end)):
            if args.debug and not jsonl:
                status.println(dim(f"         (echo of {assistant.code_name} ignored: {turn.text})"))
            return
        if jsonl:
            ev = {"type": "turn", "speaker": None if generic else name, "display": name, "label": turn.label,
                  "text": turn.text, "start": round(turn.start, 2), "end": round(turn.end, 2),
                  "wall_start": round(wall(turn.start), 3), "ts": time.time(),
                  "words": [{"w": w.text, "s": round(w.start, 2), "e": round(w.end, 2)} for w in turn.words if w.kind == "word"]}
            print(json.dumps(ev), flush=True)
        else:
            stamp = dim(time.strftime("%H:%M:%S", time.localtime(wall(turn.start))))
            status.println(f"{stamp} {paint(name)}: {turn.text}")
        if log is not None and not log.closed:
            log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(wall(turn.start)))}  {name}: {turn.text}\n")
            log.flush()
        if assistant is not None:
            hook(assistant.on_turn, turn, name, wall(turn.start), wall(turn.end))

    def on_say(kind: str, text: str) -> None:
        # "sentence": a sentence is starting to play -> show it now. "answer"/"interjection":
        # the whole thing, once done -> log + JSONL record (already shown on screen).
        with lock:
            if jsonl:
                print(json.dumps({"type": "assistant", "kind": kind, "speaker": assistant.code_name, "text": text, "ts": time.time()}), flush=True)
            elif kind == "sentence":
                stamp = dim(time.strftime("%H:%M:%S"))
                status.println(f"{stamp} {_c('35', bold(assistant.code_name))}: {text}")
            if kind != "sentence" and log is not None and not log.closed:
                log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {assistant.code_name}: {text}\n")
                log.flush()

    def on_note(text: str) -> None:
        with lock:
            if jsonl:
                print(json.dumps({"type": "note", "text": text, "ts": time.time()}), flush=True)
            else:
                status.println(dim(f"         {text}"))

    if assistant is not None:
        assistant.on_say = on_say
        assistant.on_note = on_note

    def on_event(kind: str, payload: dict) -> None:
        if kind == "mapping":
            msg = f"{payload['label']} sounds like {payload['speaker']}"
            if jsonl:
                print(json.dumps({"type": "mapping", **payload, "ts": time.time()}), flush=True)
            else:
                status.println(dim(f"         ({msg})"))
        elif kind == "started" and not jsonl:
            status.println(dim("connected; talk. Ctrl-C to stop.\n"))
        elif kind in ("warning", "error"):
            text = payload.get("reason") or payload.get("type") or json.dumps(payload)
            print((red if kind == "error" else yellow)(f"{kind}: {text}"), file=sys.stderr)

    session = LiveSession(
        key, url=args.url, language=args.language, model=args.cloud_model, max_speakers=args.max_speakers,
        known_speakers=known, enable_partials=not args.no_partials, max_delay=args.max_delay,
        speaker_sensitivity=args.sensitivity, prefer_current_speaker=args.prefer_current,
        namer=namer, on_partial=on_partial, on_turn=on_turn, on_event=on_event,
        extra_vocab=[assistant.code_name] + list(getattr(args, "alias", None) or []) if assistant is not None else [],
        eou_silence=getattr(args, "eou", None),
    )
    if not jsonl:
        title = f"voicerec assistant ({assistant.code_name})" if assistant is not None else "voicerec live"
        print(bold(title) + dim(f"  speechmatics {args.cloud_model}  max_delay={args.max_delay}s  max_speakers={args.max_speakers}"))
        if assistant is not None:
            print(dim(f"say “hey {assistant.code_name}, …” to ask; brain={getattr(assistant.brain, 'model', 'mock')}  voice={assistant.speaker.engine.name}  interject={'on' if assistant.interject else 'off'}"))
        print(dim("cloud-enrolled: ") + (", ".join(cloud_store.names()) if known else "none") + dim("   local profiles: ") + (", ".join(local_names) if namer else "off"))

    stop = {"flag": False}
    restore = _install_sigint(stop)
    mic = None
    try:
        if args.from_file:
            source, pace = file_blocks(args.from_file), args.pace
        else:
            try:
                device = resolve_device(args.device)
            except ValueError as e:
                return die(str(e))
            mic = Microphone(device)
            mic.__enter__()
            session.audio_epoch = mic.started_at  # audio time 0 is when the mic started filling its buffer
            source, pace = mic_blocks(mic, lambda: stop["flag"]), 0.0
        asyncio.run(session.run(source, lambda: stop["flag"], pace=pace))
        if assistant is not None and not stop["flag"]:
            assistant.wait_idle()  # the recording ended; let it finish its sentence
    except KeyboardInterrupt:
        pass
    except Exception as e:  # noqa: BLE001  (speechmatics.rt raises its own hierarchy)
        if type(e).__module__.startswith("speechmatics") or "websockets" in type(e).__module__:
            status.clear()
            return _cloud_error(e)
        raise
    finally:
        restore()
        if assistant is not None:
            assistant.speaker.stop()
        if mic is not None:
            mic.__exit__(None, None, None)
        status.clear()
        if log is not None:
            log.close()
    if not jsonl:
        print(dim("\nbye"))
    return 0


def cmd_assistant(args) -> int:
    from .assistant import Assistant, Brain, MockBrain, SayVoice, Speaker, SpeechmaticsVoice, SupertonicVoice, WakeWord

    name = args.name.strip()
    if args.brain == "mock":
        brain = MockBrain(name)
    else:
        try:
            brain = Brain(name, model=args.brain, notes=args.context_note or "")
        except Exception as e:  # noqa: BLE001
            return die(f"cannot start the brain: {e}. Put ANTHROPIC_API_KEY=... in .env")
    engine = None
    order = {"auto": ["supertonic", "speechmatics", "say"], "supertonic": ["supertonic"], "speechmatics": ["speechmatics"], "say": ["say"]}[args.voice_engine]
    errors = []
    for kind in order:
        try:
            if kind == "supertonic":
                engine = SupertonicVoice(args.tts_model or None, speed=args.speed)
            elif kind == "speechmatics":
                engine = SpeechmaticsVoice(args.voice)
            else:
                engine = SayVoice(args.say_voice)
            break
        except Exception as e:  # noqa: BLE001
            errors.append(f"{kind}: {e}")
    if engine is None:
        return die("no voice available: " + "; ".join(errors))
    if errors:
        print(yellow("voice fallback: " + "; ".join(errors)), file=sys.stderr)
    speaker = Speaker(engine, device=args.output_device)
    try:
        engine.synthesize("Ready.")  # warm the synthesizer so the first real reply is not slower
    except Exception:  # noqa: BLE001
        pass
    # The laptop must actually be audible. Say so loudly, or fix it when asked to.
    from .assistant import output_state, set_output

    state = output_state()
    if state and (state["muted"] or state["volume"] == 0):
        if args.unmute:
            set_output(args.unmute)
            print(dim(f"output was {'muted' if state['muted'] else 'at volume 0'}; set to {args.unmute}"))
        else:
            print(yellow("WARNING: system output is muted / at volume 0, so the assistant will be silent. "
                         "Unmute, or run with --unmute 50"), file=sys.stderr)
    assistant = Assistant(
        name, brain, speaker, WakeWord(name, args.alias or []),
        interject=args.interject, interject_cooldown=args.interject_cooldown, ack=args.ack,
    )
    if hasattr(brain, "warm_up"):
        threading.Thread(target=brain.warm_up, daemon=True).start()  # TLS handshake off the critical path
    if not args.no_greet:
        spoken = speaker.say(f"{name} here.")
        if speaker.last_error:
            print(yellow(f"voice playback failed: {speaker.last_error} (try --output-device, see `voicerec devices`)"), file=sys.stderr)
        elif not spoken:
            print(yellow("voice test produced no audio"), file=sys.stderr)
    return _live(args, assistant)


def cmd_cloud_enroll(args) -> int:
    import asyncio

    from .cloud import CloudSpeakerStore, LiveSession, file_blocks, mic_blocks

    _cloud_defaults(args)
    cloud_store = CloudSpeakerStore(Path(args.cloud_db))
    if args.list:
        if not len(cloud_store):
            print(dim("nobody cloud-enrolled yet"))
        for n in cloud_store.names():
            print(f"{n:<16} {len(cloud_store.identifiers(n))} identifier(s)")
        return 0
    if args.remove:
        return 0 if cloud_store.remove(args.remove) else die(f"{args.remove!r} is not cloud-enrolled")
    if not args.name:
        return die("give a NAME to enroll (or --list / --remove NAME)")
    key = _cloud_key(args)
    if not key:
        return 1
    name = args.name.strip()
    status = StatusLine()

    def on_partial(_n, text):
        status.show(f"{dim('…')} {text}")

    def on_turn(turn, _n):
        status.println(dim(f"  heard: {turn.text}"))

    def on_event(kind, payload):
        if kind in ("warning", "error"):
            print((red if kind == "error" else yellow)(f"{kind}: {payload.get('reason') or json.dumps(payload)}"), file=sys.stderr)

    session = LiveSession(key, url=args.url, language=args.language, model=args.cloud_model, max_speakers=2,
                          known_speakers=[], max_delay=args.max_delay, namer=None,
                          on_partial=on_partial, on_turn=on_turn, on_event=on_event)
    stop = {"flag": False}
    restore = _install_sigint(stop)
    mic = None
    deadline = time.time() + args.seconds
    try:
        if args.from_file:
            source, pace = file_blocks(args.from_file), args.pace
            print(bold(f"Cloud-enrolling {name}") + dim(f" from {args.from_file}"))
        else:
            try:
                device = resolve_device(args.device)
            except ValueError as e:
                return die(str(e))
            print(bold(f"Cloud-enrolling {name}") + f"  talk for {args.seconds:.0f} seconds, alone (Ctrl-C to stop early)")
            print(dim("  “" + ENROLL_TEXT.format(name=name) + "”\n"))
            mic = Microphone(device)
            mic.__enter__()
            source, pace = mic_blocks(mic, lambda: stop["flag"] or time.time() > deadline), 0.0
        speakers = asyncio.run(session.run(source, lambda: stop["flag"] or (mic is not None and time.time() > deadline), pace=pace, get_speakers_at_end=True))
    except KeyboardInterrupt:
        speakers = []
    except Exception as e:  # noqa: BLE001
        if type(e).__module__.startswith("speechmatics") or "websockets" in type(e).__module__:
            status.clear()
            return _cloud_error(e)
        raise
    finally:
        restore()
        if mic is not None:
            mic.__exit__(None, None, None)
        status.clear()
    if not speakers:
        return die("the service returned no speaker identifiers (too little speech?)")
    counts = session.words_per_label
    # the enrolled person is whoever said the most words; anything else was noise or a bystander
    best = max(speakers, key=lambda sp: counts.get(sp["label"], 0))
    ids = list(best.get("speaker_identifiers", []))
    others = [sp["label"] for sp in speakers if sp is not best]
    if not ids:
        return die("empty identifier list from the service")
    cloud_store.add(name, ids, replace=args.replace)
    print(green(bold(f"cloud-enrolled {name}")) + dim(f"  {len(ids)} identifier(s) from label {best['label']} ({counts.get(best['label'], 0)} words) -> {cloud_store.path}"))
    if others:
        print(yellow(f"  note: the service also heard {', '.join(others)}; make sure only {name} was talking"))
    return 0


# --------------------------------------------------------------------------- argparse
def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--model", default=DEFAULT_EMBED_MODEL, help="speaker embedding ONNX model (default: %(default)s)")
    common.add_argument("--db", default=str(DB_PATH), help="speaker database JSON (default: %(default)s)")
    common.add_argument("--threads", type=int, default=2, help="ONNX runtime threads")
    common.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD, help="min cosine similarity to accept a match (default: %(default)s)")
    common.add_argument("--no-rescue", action="store_true", help="strict mode: never accept a best match under --threshold, even when it leads the runner-up by a wide margin")
    common.add_argument("--debug", action="store_true", help="print the full ranking for every utterance (and every separated stream with --multi)")

    mic = argparse.ArgumentParser(add_help=False)
    mic.add_argument("--device", default=None, help="input device index or name substring (see `voicerec devices`)")

    asr = argparse.ArgumentParser(add_help=False)
    asr.add_argument("--transcribe", "-t", action="store_true", help="also transcribe what each identified talker said")
    asr.add_argument("--asr-model", default=DEFAULT_ASR_MODEL, help="sherpa-onnx speech-to-text model folder (default: %(default)s)")

    multi = argparse.ArgumentParser(add_help=False)
    multi.add_argument("--multi", action="store_true", help="simultaneous-talker mode: separate the mixture, then identify each voice; at enrollment also builds the separation-domain voiceprint (needs: pip install -e '.[separation]')")
    multi.add_argument("--sep-model", default=DEFAULT_SEP_MODEL, help="SpeechBrain separation model (default: %(default)s)")
    multi.add_argument("--sep-device", default=None, help="torch device for separation: mps or cpu (default: auto)")
    multi.add_argument("--stream-threshold", type=float, default=None, help="min similarity for a separated stream against the separation-domain voiceprint (default: threshold + 0.07)")

    p = argparse.ArgumentParser(prog="voicerec", description="Speaker recognition from the microphone.")
    p.add_argument("--version", action="version", version=f"voicerec {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("devices", help="list microphones", parents=[])
    s.set_defaults(fn=cmd_devices)

    s = sub.add_parser("enroll", help="record a person and save their voiceprint", parents=[common, mic, multi])
    s.add_argument("name")
    s.add_argument("--seconds", type=float, default=20, help="seconds of speech to collect (default: %(default)s; more is better)")
    s.add_argument("--text", default=None, help="your own passage to read (a string, or a path to a text file); {name} is replaced")
    s.add_argument("--from", dest="from_files", nargs="+", metavar="FILE", help="enroll from audio files instead of the mic")
    s.add_argument("--replace", action="store_true", help="discard existing samples for this name")
    s.set_defaults(fn=cmd_enroll)

    s = sub.add_parser("listen", help="identify whoever is talking, live", parents=[common, mic, multi, asr])
    s.add_argument("--jsonl", action="store_true", help="emit one JSON object per event instead of pretty output")
    s.add_argument("--log", metavar="FILE", help="with --transcribe, append a timestamped 'Name: text' transcript to this file")
    s.add_argument("--partial-every", type=float, default=None, help="seconds between provisional guesses while someone talks (default: 0.75, or 1.5 with --multi)")
    s.add_argument("--partial-window", type=float, default=3.0, help="with --multi, provisional guesses look at the last N seconds")
    s.add_argument("--min-utterance", type=float, default=0.8, help="ignore speech shorter than this (seconds)")
    s.add_argument("--min-silence", type=float, default=0.4, help="silence that ends an utterance (seconds)")
    s.add_argument("--max-speech", type=float, default=8.0, help="force a decision after this many seconds of continuous speech (default: %(default)s)")
    s.set_defaults(fn=cmd_listen)

    s = sub.add_parser("identify", help="identify the speaker(s) in audio files", parents=[common, multi, asr])
    s.add_argument("files", nargs="+")
    s.add_argument("--segments", action="store_true", help="also score each VAD segment")
    s.add_argument("--min-utterance", type=float, default=0.8)
    s.add_argument("--jsonl", action="store_true")
    s.set_defaults(fn=cmd_identify)

    cloud = argparse.ArgumentParser(add_help=False)
    cloud.add_argument("--api-key", default=None, help="Speechmatics API key (default: $SPEECHMATICS_API_KEY)")
    cloud.add_argument("--url", default=None, help="Speechmatics realtime endpoint (default: $SPEECHMATICS_URL or wss://eu2.rt.speechmatics.com/v2)")
    cloud.add_argument("--language", default="en")
    cloud.add_argument("--cloud-model", default="enhanced", choices=["standard", "enhanced", "melia-1"], help="Speechmatics model (default: %(default)s)")
    cloud.add_argument("--max-delay", type=float, default=None, help="seconds the service may wait before committing words, 0.7-4 (default: 1.0; 0.7 for the assistant)")
    cloud.add_argument("--eou", type=float, default=None, metavar="SECONDS", help="finalize a sentence after this much silence (default: off for live, 0.5 for the assistant)")
    cloud.add_argument("--cloud-db", default=None, help="cloud speaker identifier file (default: data/cloud_speakers.json)")
    cloud.add_argument("--from", dest="from_file", metavar="FILE", help="stream an audio file instead of the mic")
    cloud.add_argument("--pace", type=float, default=4.0, help="with --from, send at N x real time (default: %(default)s)")

    livep = argparse.ArgumentParser(add_help=False)
    livep.add_argument("--max-speakers", type=int, default=4, help="how many un-enrolled speakers to tell apart (default: %(default)s)")
    livep.add_argument("--sensitivity", type=float, default=None, help="speaker sensitivity 0-1; lower = stick to enrolled speakers")
    livep.add_argument("--prefer-current", action="store_true", help="make the service hold onto the current speaker across turn boundaries (steadier labels, slower hand-overs)")
    livep.add_argument("--no-partials", action="store_true", help="no provisional words while people talk")
    livep.add_argument("--no-local-naming", action="store_true", help="do not name S1/S2 speakers with the local voice profiles")
    livep.add_argument("--no-cloud-speakers", action="store_true", help="ignore cloud-enrolled identifiers")
    livep.add_argument("--jsonl", action="store_true", help="one JSON object per partial / turn / mapping event")
    livep.add_argument("--log", metavar="FILE", help="append a timestamped 'Name: text' transcript to this file")

    s = sub.add_parser("live", help="cloud streaming: live transcript with named speakers (Speechmatics)", parents=[common, mic, cloud, livep])
    s.set_defaults(fn=cmd_live)

    s = sub.add_parser("assistant", help="a voice assistant in the conversation: a code name to call it, optional interjections", parents=[common, mic, cloud, livep])
    s.add_argument("--name", default="Nova", help="the code name people say to address it (default: %(default)s)")
    s.add_argument("--alias", action="append", metavar="WORD", help="other spellings the recognizer might produce for the name (repeatable)")
    s.add_argument("--brain", default="claude-opus-5-5", help="Claude model id (default: %(default)s; claude-sonnet-5-5 and claude-haiku-5-5 answer faster), or 'mock' for an offline stand-in")
    s.add_argument("--interject", action="store_true", help="let it speak up unprompted when it has something specific to add")
    s.add_argument("--context-note", metavar="TEXT", help="facts the assistant should know (venue, schedule, what the project is)")
    s.add_argument("--ack", action="store_true", help="say a quick 'Sure.' when the model takes more than half a second to start, so it never feels like dead air")
    s.add_argument("--interject-cooldown", type=float, default=45, help="seconds of silence from it between unprompted remarks (default: %(default)s)")
    s.add_argument("--voice-engine", choices=["auto", "supertonic", "speechmatics", "say"], default="auto", help="auto = Supertonic (local), then Speechmatics TTS, then macOS say")
    s.add_argument("--voice", default="sarah", help="Speechmatics TTS voice: sarah, theo or megan")
    s.add_argument("--speed", type=float, default=1.0, help="speaking rate multiplier (Supertonic)")
    s.add_argument("--tts-model", default=None, help="Supertonic model folder (default: first models/sherpa-onnx-supertonic*)")
    s.add_argument("--say-voice", default="Samantha", help="macOS voice for the fallback engine")
    s.add_argument("--output-device", default=None, help="sounddevice output device for the voice (default: system output)")
    s.add_argument("--unmute", type=int, metavar="VOLUME", default=None, help="macOS: unmute and set the output volume (0-100) on start")
    s.add_argument("--no-greet", action="store_true", help="skip the spoken greeting at start (it doubles as an audio check)")
    s.set_defaults(fn=cmd_assistant)

    s = sub.add_parser("cloud-enroll", help="teach the cloud service a voice (Speechmatics speaker identifiers)", parents=[mic, cloud])
    s.add_argument("name", nargs="?")
    s.add_argument("--seconds", type=float, default=25, help="how long to record (default: %(default)s)")
    s.add_argument("--replace", action="store_true", help="discard this name's existing identifiers")
    s.add_argument("--list", action="store_true", help="show cloud-enrolled names")
    s.add_argument("--remove", metavar="NAME", help="forget a cloud-enrolled name")
    s.set_defaults(fn=cmd_cloud_enroll)

    s = sub.add_parser("list", help="show enrolled speakers", parents=[common])
    s.set_defaults(fn=cmd_list)

    s = sub.add_parser("remove", help="forget a speaker", parents=[common])
    s.add_argument("name")
    s.set_defaults(fn=cmd_remove)

    s = sub.add_parser("matrix", help="how similar enrolled speakers are to each other", parents=[common])
    s.set_defaults(fn=cmd_matrix)

    s = sub.add_parser("reset", help="delete the whole speaker database", parents=[common])
    s.add_argument("--yes", action="store_true")
    s.set_defaults(fn=cmd_reset)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except FileNotFoundError as e:
        return die(str(e))
    except RuntimeError as e:  # includes ModelMismatch and SeparationUnavailable
        return die(str(e))
    except KeyboardInterrupt:
        print()
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
