#!/usr/bin/env python
"""A stand-in for the Speechmatics real-time WebSocket API, for testing without a key.

It speaks the same protocol (StartRecognition, binary AddAudio, AddPartialTranscript,
AddTranscript, GetSpeakers/SpeakersResult, EndOfStream/EndOfTranscript) and emits a
scripted transcript whose words are spread over speaker spans, as the audio time passes.

Usage: python scripts/fake_speechmatics.py --port 8765 --script spans.json
spans.json: [{"label": "S1", "start": 0.0, "end": 5.0, "text": "hello there ..."}, ...]
If the client enrolls known speakers whose identifiers match "fake-id-<label>", words of
that label are tagged with the client's name instead, like the real service would.
"""
from __future__ import annotations

import argparse
import asyncio
import json

import websockets

SR = 16000
BYTES_PER_SEC = SR * 2


def build_words(spans):
    words = []
    for sp in spans:
        toks = sp["text"].split()
        dur = (sp["end"] - sp["start"]) / max(1, len(toks))
        for i, tok in enumerate(toks):
            t0 = sp["start"] + i * dur
            words.append({"label": sp["label"], "text": tok.rstrip(".,?!"), "start": round(t0, 2), "end": round(t0 + dur * 0.9, 2),
                          "punct": tok[-1] if tok[-1] in ".,?!" else None, "eos": tok.endswith((".", "?", "!"))})
    return words


def result_items(words, name_of):
    items = []
    for w in words:
        items.append({"type": "word", "start_time": w["start"], "end_time": w["end"], "is_eos": bool(w["eos"]) and not w["punct"],
                      "alternatives": [{"content": w["text"], "confidence": 0.95, "speaker": name_of(w["label"])}]})
        if w["punct"]:
            items.append({"type": "punctuation", "start_time": w["end"], "end_time": w["end"], "is_eos": bool(w["eos"]),
                          "attaches_to": "previous", "alternatives": [{"content": w["punct"], "confidence": 1.0, "speaker": name_of(w["label"])}]})
    return items


async def serve(ws, spans):
    words = build_words(spans)
    known = {}  # identifier -> client label
    received = 0
    seq = 0
    sent_final_upto = 0
    last_partial_at = 0.0
    speakers_at_end = False

    def speakers_result():
        labels = sorted({w["label"] for w in words[:sent_final_upto]} or {w["label"] for w in words})
        return json.dumps({"message": "SpeakersResult", "speakers": [{"label": name_of(l), "speaker_identifiers": [f"fake-id-{l}"]} for l in labels]})
    name_of = lambda label: known.get(f"fake-id-{label}", label)  # noqa: E731
    async for msg in ws:
        if isinstance(msg, bytes):
            received += len(msg)
            seq += 1
            await ws.send(json.dumps({"message": "AudioAdded", "seq_no": seq}))
            t = received / BYTES_PER_SEC
            # finals: every 2 s of audio, all words that ended more than 0.5 s ago (max_delay-ish)
            due = [w for w in words[sent_final_upto:] if w["end"] <= t - 0.5]
            if due and (t - (due[0]["start"]) >= 2.0 or any(w["eos"] for w in due)):
                await ws.send(json.dumps({"message": "AddTranscript",
                                          "metadata": {"start_time": due[0]["start"], "end_time": due[-1]["end"], "transcript": " ".join(w["text"] for w in due)},
                                          "results": result_items(due, name_of)}))
                sent_final_upto += len(due)
            elif t - last_partial_at >= 0.4:
                partial = [w for w in words[sent_final_upto:] if w["start"] <= t]
                if partial:
                    await ws.send(json.dumps({"message": "AddPartialTranscript",
                                              "metadata": {"start_time": partial[0]["start"], "end_time": partial[-1]["end"], "transcript": " ".join(w["text"] for w in partial)},
                                              "results": result_items(partial, name_of)}))
                last_partial_at = t
            continue
        m = json.loads(msg)
        kind = m.get("message")
        if kind == "StartRecognition":
            sdc = (m.get("transcription_config") or {}).get("speaker_diarization_config") or {}
            for sp in sdc.get("speakers") or []:
                for ident in sp.get("speaker_identifiers", []):
                    known[ident] = sp["label"]
            await ws.send(json.dumps({"message": "RecognitionStarted", "id": "fake-session", "language_pack_info": {"language_description": "English"}}))
        elif kind == "GetSpeakers":
            if m.get("final"):
                speakers_at_end = True  # answered after the last transcript, like the real service
            else:
                await ws.send(speakers_result())
        elif kind == "EndOfStream":
            rest = words[sent_final_upto:]
            if rest:
                await ws.send(json.dumps({"message": "AddTranscript", "metadata": {"start_time": rest[0]["start"], "end_time": rest[-1]["end"], "transcript": ""},
                                          "results": result_items(rest, name_of)}))
                sent_final_upto = len(words)
            if speakers_at_end:
                await ws.send(speakers_result())
            await ws.send(json.dumps({"message": "EndOfTranscript"}))
            await ws.close()
            return


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--script", required=True)
    args = ap.parse_args()
    spans = json.load(open(args.script))
    async with websockets.serve(lambda ws: serve(ws, spans), "127.0.0.1", args.port):
        print(f"fake speechmatics on ws://127.0.0.1:{args.port}/v2", flush=True)
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
