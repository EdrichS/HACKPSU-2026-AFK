#!/usr/bin/env python
"""End-to-end test of the live microphone path, no human required (macOS only).

Runs the real `voicerec listen --jsonl` process, plays a few sentences through
the speakers with `say`, and checks that each one was attributed to the right
enrolled voice (or to Unknown for voices that were never enrolled).

Usage: python scripts/loopback_test.py --db DB.json Karen Daniel ?Moira
       python scripts/loopback_test.py --db DB.json --multi Karen+Daniel Rishi+?Moira Karen
A '+' plays two voices at the same time (simultaneous talkers); '?' marks a voice
that is not enrolled and must come back as Unknown.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time

SENTENCE = "Hello there, this is a live microphone test. Can you tell who is talking right now?"
ENROLL_SENTENCES = [
    "The quick brown fox jumps over the lazy dog while the sun sets slowly behind the distant mountains.",
    "Please remember to bring your laptop charger and a water bottle to the hackathon tomorrow morning.",
    "I think the weather this weekend will be perfect for a long hike along the river trail.",
    "Our team spent the entire night debugging the audio pipeline before the final presentation.",
]


def common_flags(args) -> list[str]:
    flags = []
    if args.db:
        flags += ["--db", args.db]
    if args.device:
        flags += ["--device", args.device]
    return flags


def enroll_via_speakers(voice: str, args) -> bool:
    """Run the real mic enrollment while `say` reads sentences through the speakers."""
    cmd = [sys.executable, "-m", "voice_rec", "enroll", voice, "--seconds", str(args.enroll_seconds), "--replace"] + common_flags(args)
    if args.multi:
        cmd.append("--multi")
    print(f"\nenrolling {voice} through the speakers ...")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    time.sleep(2.5)
    for sentence in ENROLL_SENTENCES:
        if proc.poll() is not None:
            break
        subprocess.run(["say", "-v", voice, sentence], check=True)
        time.sleep(1.0)
    if proc.poll() is None:
        time.sleep(1.0)
    if proc.poll() is None:
        proc.send_signal(signal.SIGINT)
    try:
        out, _ = proc.communicate(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, _ = proc.communicate()
    for line in out.splitlines():
        print("  |", line)
    return proc.returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("voices", nargs="+", help="macOS voices to play; '?Moira' = not enrolled, 'Karen+Daniel' = both at once")
    ap.add_argument("--multi", action="store_true", help="run listen --multi (simultaneous-talker mode)")
    ap.add_argument("--transcribe", action="store_true", help="run listen --transcribe and show what was heard")
    ap.add_argument("--db", default=None)
    ap.add_argument("--threshold", type=float, default=None)
    ap.add_argument("--device", default=None)
    ap.add_argument("--enroll-first", action="store_true", help="enroll each non-'?' voice through the speakers first (tests mic enrollment)")
    ap.add_argument("--enroll-seconds", type=float, default=8)
    args = ap.parse_args()

    if args.enroll_first:
        done = set()
        for spec in args.voices:
            for part in spec.split("+"):
                if not part.startswith("?") and part not in done:
                    done.add(part)
                    if not enroll_via_speakers(part, args):
                        print(f"enrollment of {part} failed")
                        return 2

    cmd = [sys.executable, "-m", "voice_rec", "listen", "--jsonl"] + common_flags(args)
    if args.multi:
        cmd.append("--multi")
    if args.transcribe:
        cmd.append("--transcribe")
    if args.threshold is not None:
        cmd += ["--threshold", str(args.threshold)]

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
    events: list[dict] = []

    def reader():
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                print("  listener said:", line)
                continue
            ev["_t"] = time.time()
            events.append(ev)
            if ev["type"] == "final":
                if "talkers" in ev:
                    who = " + ".join(f"{t['speaker'] or 'Unknown'} {t['score']:.2f}" for t in ev["talkers"])
                    print(f"  heard -> [{ev['n_talkers']} talker(s)] {who}  ({ev['duration']}s)")
                    for t in ev["talkers"]:
                        if t.get("text") is not None:
                            print(f"           {t['speaker'] or 'Unknown'}: {t['text']!r}")
                else:
                    print(f"  heard -> {ev['speaker'] or 'Unknown':<10} score {ev['score']:.2f}  ({ev['duration']}s)")
                    if ev.get("text") is not None:
                        print(f"           said: {ev['text']!r}")

    threading.Thread(target=reader, daemon=True).start()
    time.sleep(8 if args.multi else 2.5)  # model load + stream start
    if proc.poll() is not None:
        print("listener exited early:", proc.stderr.read())
        return 2

    windows = []
    for spec in args.voices:
        parts = spec.split("+")
        voices = [p.lstrip("?") for p in parts]
        expected = {None if p.startswith("?") else p.lstrip("?") for p in parts}
        label = " + ".join(f"{v}{' (not enrolled)' if p.startswith('?') else ''}" for p, v in zip(parts, voices))
        print(f"\nplaying {label}{' simultaneously' if len(voices) > 1 else ''} ...")
        t0 = time.time()
        procs = [subprocess.Popen(["say", "-v", v, SENTENCE if i == 0 else ENROLL_SENTENCES[-1]]) for i, v in enumerate(voices)]
        for p in procs:
            p.wait()
        time.sleep(1.5)  # let the VAD close the utterance
        windows.append((spec, expected, t0, time.time()))

    # let the listener work through any backlog before stopping it
    deadline = time.time() + 15
    while time.time() < deadline:
        n = len(events)
        time.sleep(2.0)
        if len(events) == n:
            break
    proc.send_signal(signal.SIGINT)
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()

    print("\nresults")
    failures = 0
    for spec, expected, t0, t1 in windows:
        # match by when the utterance actually started (listener reports wall_start), not when it was printed
        finals = [e for e in events if e["type"] == "final" and t0 - 0.5 <= e.get("wall_start", e["_t"]) <= t1]
        if not finals:
            print(f"  FAIL {spec:<16} nothing detected (speakers muted? mic too far?)")
            failures += 1
            continue
        best = max(finals, key=lambda e: e["duration"])
        if "talkers" in best:
            got = {t["speaker"] for t in best["talkers"]}
            shown = " + ".join(f"{t['speaker'] or 'Unknown'} {t['score']:.2f} ({t['share']:.0%})" for t in best["talkers"])
        else:
            got = {best["speaker"]}
            shown = f"{best['speaker'] or 'Unknown'} {best['score']:.2f}  margin {best['margin']:+.2f}"
        ok = got == expected
        failures += not ok
        want = " + ".join(sorted(n or "Unknown" for n in expected))
        print(f"  {'ok  ' if ok else 'FAIL'} {spec:<16} want {want:<18} got {shown}")
        if not ok and "talkers" in best:
            for t in best["talkers"]:
                print(f"         stream {t['speaker'] or 'Unknown':<8} ranked {t['ranked']}")
            print(f"         whole mix: {best['mixture']['speaker'] or 'Unknown'} {best['mixture']['score']:.2f} ranked {best['mixture']['ranked'][:3]}")
    print(f"\n{len(windows) - failures}/{len(windows)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
