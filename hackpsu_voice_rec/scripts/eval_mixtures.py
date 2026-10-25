#!/usr/bin/env python
"""Simultaneous-talker evaluation on synthetic voices: separate -> identify.

Enrolls voices from clips 1-2, then mixes held-out clips 3-4 pairwise and checks
that both talkers are named, that a lone talker is reported as one talker, and
that a mix with an un-enrolled voice does not invent a wrong name.

Usage: python scripts/eval_mixtures.py DATASET_DIR [--holdout Moira Fred] [--stream-threshold 0.42]
"""
from __future__ import annotations

import argparse
import itertools
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from voice_rec.audio import load_audio  # noqa: E402
from voice_rec.config import DEFAULT_EMBED_MODEL, DEFAULT_THRESHOLD, SAMPLE_RATE  # noqa: E402
from voice_rec.embedder import SpeakerEmbedder  # noqa: E402
from voice_rec.recognizer import MultiRecognizer, Recognizer, separated_embeddings  # noqa: E402
from voice_rec.separator import SpeechSeparator  # noqa: E402
from voice_rec.store import SpeakerStore  # noqa: E402
from voice_rec.vad import segment_audio  # noqa: E402


def speech(path) -> np.ndarray:
    a = load_audio(path)
    segs = [s for s in segment_audio(a) if s.duration >= 1.0]
    return np.concatenate([s.samples for s in segs]) if segs else a


def norm(x, target=0.05):
    return (x * (target / (np.sqrt(np.mean(x**2)) + 1e-9))).astype(np.float32)


def mix(a, b, gain_b=1.0):
    n = min(len(a), len(b))
    return (norm(a)[:n] + gain_b * norm(b)[:n]) / (1 + gain_b)


def show(mm):
    return " + ".join(f"{t.speaker or 'Unknown'}:{t.score:.2f}({t.share:.0%})" for t in mm.talkers)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset")
    ap.add_argument("--model", default=DEFAULT_EMBED_MODEL)
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    ap.add_argument("--stream-threshold", type=float, default=None)
    ap.add_argument("--holdout", nargs="*", default=["Moira", "Fred"], help="voices kept un-enrolled")
    ap.add_argument("--no-sep-enroll", action="store_true", help="do not build separation-domain voiceprints (old behaviour)")
    args = ap.parse_args()

    root = Path(args.dataset)
    voices = sorted(p.name for p in root.iterdir() if p.is_dir())
    enrolled = [v for v in voices if v not in args.holdout]
    holdout = [v for v in voices if v in args.holdout]
    embedder = SpeakerEmbedder(args.model)
    sep = SpeechSeparator()
    print(f"embedder {embedder.model_name}; separator {sep.source} on {sep.device}")
    print(f"enrolled: {', '.join(enrolled)}   not enrolled: {', '.join(holdout) or '-'}")

    with tempfile.TemporaryDirectory() as td:
        store = SpeakerStore(Path(td) / "db.json", embedder.model_name, embedder.dim, sep_model=sep.source)
        for v in enrolled:
            clips = [speech(root / v / f"s{i}.wav") for i in (1, 2)]
            embs = [embedder.embed(x) for x in clips]
            seps = [] if args.no_sep_enroll else separated_embeddings(embedder, sep, clips)
            store.add(v, embs, sep_embeddings=seps)
        print(f"separation-domain voiceprints: {'no' if args.no_sep_enroll else 'yes'}")
        rec = Recognizer(embedder, store, args.threshold)
        multi = MultiRecognizer(rec, sep, stream_threshold=args.stream_threshold)
        print(f"threshold {rec.threshold:.2f}; stream threshold {multi.stream_threshold:.2f}\n")
        test = {v: [speech(root / v / f"s{i}.wav") for i in (3, 4)] for v in voices}

        genuine_stream, impostor_stream = [], []
        print("=== two enrolled talkers, equal loudness ===")
        ok = n = 0; times = []
        for a, b in itertools.combinations(enrolled, 2):
            for ia, ib in ((0, 1), (1, 0)):
                x = mix(test[a][ia], test[b][ib])
                t = time.time(); mm = multi.identify(x); times.append((time.time() - t) / (len(x) / SAMPLE_RATE))
                good = set(mm.names) == {a, b}; ok += good; n += 1
                genuine_stream += [t_.score for t_ in mm.talkers if t_.speaker in (a, b)]
                print(f"  {'ok ' if good else 'XX '}{a}+{b:<7} -> {show(mm)}")
        print(f"  both named: {ok}/{n}   separation+id cost: {np.mean(times):.2f}x audio duration\n")

        print("=== two enrolled talkers, second one 6 dB quieter ===")
        ok = n = 0
        for a, b in itertools.combinations(enrolled, 2):
            mm = multi.identify(mix(test[a][0], test[b][1], gain_b=0.5))
            good = set(mm.names) == {a, b}; ok += good; n += 1
            genuine_stream += [t_.score for t_ in mm.talkers if t_.speaker in (a, b)]
            print(f"  {'ok ' if good else 'XX '}{a}+{b:<7} -> {show(mm)}")
        print(f"  both named: {ok}/{n}\n")

        print("=== one enrolled talker alone (must report exactly one, the right one) ===")
        ok = n = 0
        for v in enrolled:
            for clip in test[v]:
                mm = multi.identify(norm(clip))
                good = mm.names == [v]; ok += good; n += 1
                print(f"  {'ok ' if good else 'XX '}{v:<7} -> {show(mm)}")
        print(f"  correct: {ok}/{n}\n")

        if holdout:
            print("=== enrolled + NOT enrolled talker (must name the enrolled one, must not invent a second name) ===")
            ok = n = 0
            for a in enrolled:
                for u in holdout:
                    mm = multi.identify(mix(test[a][0], test[u][1]))
                    names = set(mm.names)
                    good = a in names and names <= {a, "Unknown"}; ok += good; n += 1
                    impostor_stream += [t_.score for t_ in mm.talkers if t_.speaker != a]
                    print(f"  {'ok ' if good else 'XX '}{a}+{u}(?) -> {show(mm)}")
            print(f"  acceptable: {ok}/{n}\n")

        g = np.array(genuine_stream)
        if len(g):
            print(f"genuine scores on separated streams : min {g.min():.2f}  p10 {np.percentile(g, 10):.2f}  mean {g.mean():.2f}")
        im = np.array(impostor_stream)
        if len(im):
            print(f"impostor scores on separated streams: max {im.max():.2f}  p90 {np.percentile(im, 90):.2f}  mean {im.mean():.2f}")


if __name__ == "__main__":
    main()
