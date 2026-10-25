#!/usr/bin/env python
"""Enroll synthetic voices from clips 1-2, test on clips 3-4, report accuracy and
the genuine/impostor score gap so DEFAULT_THRESHOLD can be chosen sensibly.

Usage: python scripts/eval_synthetic.py DATASET_DIR [--model models/x.onnx]
(DATASET_DIR comes from scripts/make_synthetic_speakers.sh)
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from voice_rec.audio import load_audio  # noqa: E402
from voice_rec.config import DEFAULT_EMBED_MODEL  # noqa: E402
from voice_rec.embedder import SpeakerEmbedder  # noqa: E402
from voice_rec.recognizer import Recognizer  # noqa: E402
from voice_rec.store import SpeakerStore  # noqa: E402
from voice_rec.vad import segment_audio  # noqa: E402


def clip_embeddings(embedder, path):
    audio = load_audio(path)
    segs = [s for s in segment_audio(audio) if s.duration >= 1.0]
    embs = [embedder.embed(s.samples) for s in segs]
    speech = np.concatenate([s.samples for s in segs]) if segs else audio
    embs.append(embedder.embed(speech))
    return embs, speech


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset")
    ap.add_argument("--model", default=DEFAULT_EMBED_MODEL)
    args = ap.parse_args()

    root = Path(args.dataset)
    voices = sorted(p.name for p in root.iterdir() if p.is_dir())
    embedder = SpeakerEmbedder(args.model)
    print(f"model: {embedder.model_name} (dim {embedder.dim}); voices: {', '.join(voices)}")

    # Embed everything once.
    enroll = {v: sum((clip_embeddings(embedder, root / v / f"s{i}.wav")[0] for i in (1, 2)), []) for v in voices}
    test = {v: [clip_embeddings(embedder, root / v / f"s{i}.wav")[1] for i in (3, 4)] for v in voices}

    with tempfile.TemporaryDirectory() as td:
        # Closed-set identification: everyone enrolled.
        store = SpeakerStore(Path(td) / "db.json", embedder.model_name, embedder.dim)
        for v in voices:
            store.add(v, enroll[v])
        rec = Recognizer(embedder, store, threshold=-1.0)
        genuine, impostor, correct, total = [], [], 0, 0
        print("\nclosed-set identification (clips 3-4):")
        for v in voices:
            for clip in test[v]:
                m = rec.identify(clip)
                total += 1
                ok = m.best_guess == v
                correct += ok
                genuine.append(dict(m.ranked)[v])
                impostor += [s for n, s in m.ranked if n != v]
                flag = "ok " if ok else "XX "
                print(f"  {flag}{v:<8} -> {m.best_guess:<8} {m.score:.3f}  margin {m.margin:+.3f}")
        print(f"  accuracy: {correct}/{total}")

        # Open-set: each voice left out of enrollment in turn, must come back Unknown.
        loo_best = []
        print("\nopen-set (leave-one-voice-out): best impostor score per held-out voice")
        for v in voices:
            s2 = SpeakerStore(Path(td) / f"db_{v}.json", embedder.model_name, embedder.dim)
            for u in voices:
                if u != v:
                    s2.add(u, enroll[u])
            r2 = Recognizer(embedder, s2, threshold=-1.0)
            best = max(r2.identify(clip).score for clip in test[v])
            loo_best.append(best)
            print(f"  {v:<8} best impostor {best:.3f}")

    # open-set *decisions* at the default threshold, including the margin rescue rule
    fa = 0
    for v in voices:
        s2 = SpeakerStore(Path(td) / f"db2_{v}.json", embedder.model_name, embedder.dim) if False else None
    with tempfile.TemporaryDirectory() as td2:
        for v in voices:
            s2 = SpeakerStore(Path(td2) / f"db_{v}.json", embedder.model_name, embedder.dim)
            for u in voices:
                if u != v:
                    s2.add(u, enroll[u])
            r2 = Recognizer(embedder, s2)
            fa += sum(r2.identify(clip).is_known for clip in test[v])
        fr = 0
        s3 = SpeakerStore(Path(td2) / "db_all.json", embedder.model_name, embedder.dim)
        for v in voices:
            s3.add(v, enroll[v])
        r3 = Recognizer(embedder, s3)
        fr = sum((not r3.identify(clip).is_known) or r3.identify(clip).speaker != v for v in voices for clip in test[v])
    print(f"\ndecisions at default threshold {r3.threshold:.2f} with margin rescue: "
          f"false rejects {fr}/{2*len(voices)}, strangers accepted {fa}/{2*len(voices)}")

    g, imp = np.array(genuine), np.array(impostor + loo_best)
    print("\nscore distributions")
    print(f"  genuine : min {g.min():.3f}  mean {g.mean():.3f}  max {g.max():.3f}")
    print(f"  impostor: min {imp.min():.3f}  mean {imp.mean():.3f}  max {imp.max():.3f}")
    print("\nthreshold sweep (false rejects / false accepts)")
    for t in np.arange(0.30, 0.81, 0.05):
        fr = int((g < t).sum())
        fa = int((imp >= t).sum())
        print(f"  {t:.2f}: FR {fr:>2}/{len(g)}  FA {fa:>3}/{len(imp)}")
    if g.min() > imp.max():
        print(f"\nclean separation; suggested threshold ~ {(g.min() + imp.max()) / 2:.2f}")
    else:
        print("\noverlap between genuine and impostor scores; pick threshold from the sweep")


if __name__ == "__main__":
    main()
