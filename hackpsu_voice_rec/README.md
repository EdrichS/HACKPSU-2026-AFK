# hackpsu_voice_rec

Talk into the microphone and the system tells you who is speaking.

Enroll each person once (about 20 seconds of talking), then run `voicerec listen`.
Every utterance is matched against the enrolled voiceprints and printed with a
confidence score; voices nobody enrolled come back as **Unknown**. Add
`--transcribe` and each line also says *what* they said, so you get a live
"who said what" transcript, even for two people talking at once.

Everything runs locally: no cloud, no API keys. Speaker embeddings come from
NVIDIA's TitaNet-small via [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx),
with Silero VAD chopping the mic stream into utterances. For **people talking at
the same time**, an optional speech-separation front end (SpeechBrain SepFormer,
PyTorch, runs on the Apple GPU) splits the mixture first so every voice is named.

## Quick start

```bash
python3.13 -m venv .venv && source .venv/bin/activate
pip install -e .
scripts/download_models.sh          # TitaNet-small + Silero VAD (~41 MB), Moonshine speech-to-text (~250 MB), Supertonic voice (~130 MB)

voicerec devices                    # pick a mic if the default is wrong
voicerec enroll "Nikita"            # read the passage, then keep talking until the bar fills (~20 s)
voicerec enroll "Teammate"
voicerec listen                     # talk; Ctrl-C to stop
```

For simultaneous talkers, install the separation extra and enroll with `--multi`
(this also builds a second, separation-domain voiceprint per person):

```bash
pip install -e '.[separation]'          # PyTorch + SpeechBrain, ~1 GB; model downloads on first use (~113 MB)
voicerec enroll "Nikita" --multi
voicerec enroll "Teammate" --multi
voicerec listen --multi
```

`listen` prints one line per utterance:

```
16:42:07 Nikita       ████████████████░░░░ 0.81  next: Teammate 0.21  3.4s
16:42:12 Unknown      ██████████░░░░░░░░░░ 0.48  closest: Teammate  next: Nikita 0.19  2.1s
```

While someone is still talking a provisional guess is shown on the status line
and replaced by the final call when they pause. With `--multi`, two people
talking over each other come out as:

```
16:43:01 2 talkers  Nikita 0.81 + Teammate 0.74  4.2s
```

With `--transcribe` (or `-t`) every final line is followed by the words:

```
16:42:07 Nikita       ████████████████░░░░ 0.81  3.4s
         “so the whole pipeline runs on the laptop, no cloud”
16:43:01 2 talkers  Nikita 0.81 + Teammate 0.74  4.2s
         Nikita: wait, let me show the demo first
         Teammate: the judges are coming over now
```

`--log notes.txt` appends the same as timestamped `Name: text` lines, a running
transcript of the session.

## Commands

| command | what it does |
| --- | --- |
| `voicerec enroll NAME [--seconds 20] [--text FILE] [--replace] [--from a.wav b.wav] [--multi]` | record (or load files) and save a voiceprint; re-running adds samples; `--multi` also builds the separation-domain voiceprint |
| `voicerec listen [--threshold 0.45] [--device 0] [--jsonl] [--multi] [--transcribe] [--log FILE]` | live identification from the mic; `--multi` names simultaneous talkers; `--transcribe` adds what they said |
| `voicerec identify FILE... [--segments] [--jsonl] [--multi] [--transcribe]` | identify (and transcribe) the speaker(s) in audio files |
| `voicerec list` | enrolled speakers, sample counts, self-consistency |
| `voicerec matrix` | pairwise similarity between enrolled speakers (spots confusable pairs) |
| `voicerec remove NAME` / `voicerec reset --yes` | forget one speaker / everyone |
| `voicerec devices` | list microphones |
| `voicerec live [--log FILE] [--jsonl] [--max-speakers 4] [--from FILE]` | **cloud streaming**: live transcript with a name on every turn (Speechmatics) |
| `voicerec cloud-enroll NAME [--seconds 25] [--from FILE]` / `--list` / `--remove NAME` | teach the cloud service a voice |
| `voicerec assistant --name Nova [--interject] [--brain MODEL] [--voice-engine ...]` | the voice assistant in the conversation (Claude brain, local Supertonic voice) |

Common flags: `--model`, `--db`, `--threads`, `--threshold`, `--debug`. Multi-talker
flags: `--multi`, `--sep-model`, `--sep-device mps|cpu`, `--stream-threshold`.
Transcription: `--transcribe`, `--asr-model`. Environment equivalents:
`VOICEREC_MODEL`, `VOICEREC_DB`, `VOICEREC_THRESHOLD`, `VOICEREC_SEP_MODEL`,
`VOICEREC_ASR_MODEL`.

### Integrating with something else (web UI, game, bot)

`voicerec listen --jsonl` writes one JSON object per line to stdout:

```json
{"type": "final", "start": 12.3, "duration": 3.4, "ts": 1761338527.1,
 "speaker": "Nikita", "known": true, "score": 0.81, "margin": 0.60,
 "ranked": [["Nikita", 0.81], ["Teammate", 0.21]]}
```

`type` is `partial` (provisional, while they are still talking) or `final`.
`speaker` is `null` when nobody clears the threshold. `wall_start` is the
utterance's start as a Unix timestamp. With `--multi` each event also carries
`n_talkers`, `speakers` (names, loudest first) and `talkers`, one object per
voice with `speaker`, `score` and `share` (its fraction of the energy); the
single-speaker fields then describe the whole mixture. With `--transcribe`,
`text` holds the transcript (for two talkers, `Name: text | Name: text`, and each
`talkers` entry carries its own `text`). Pipe it into whatever you are building,
or import the package directly:

```python
from voice_rec.embedder import SpeakerEmbedder
from voice_rec.store import SpeakerStore
from voice_rec.recognizer import Recognizer
from voice_rec.audio import load_audio
from voice_rec.config import DB_PATH

emb = SpeakerEmbedder()
store = SpeakerStore(DB_PATH, emb.model_name, emb.dim)
rec = Recognizer(emb, store, threshold=0.45)
match = rec.identify(load_audio("clip.wav"))   # 16 kHz mono float32 in, Match out
print(match.speaker, match.score, match.ranked)
```

## How it works

```
mic (16 kHz mono) ──► Silero VAD ──► utterance ──► TitaNet-small ──► 192-d embedding
                                                                         │
            enrolled centroids (data/speakers.json) ──► cosine similarity ◄┘
                                                              │
                                   best ≥ threshold ? name : Unknown
```

* **Enrollment** collects VAD-trimmed speech, embeds each utterance plus 3 s
  windows plus the whole take, and stores all of them. The reading text (the
  Rainbow Passage by default, `--text` for your own) matters far less than the
  amount of speech and recording in the conditions you will demo in. The speaker's voiceprint
  is the L2-normalised mean of their samples. Enrolling again adds samples, so
  people can enroll from several distances/rooms.
* **Recognition** scores an utterance against every centroid and takes the best.
  With three or more people enrolled, the *ranking* is done after subtracting the
  mean of all stored embeddings from profiles and probe alike. That removes what
  every voice has in common and pulls look-alike speakers apart (two teammates
  went from 0.45 apart to clearly separated). The raw score of the winner is what
  is compared against the threshold, so thresholds keep their meaning. `margin`
  is the winner's lead in that centered space.
  Utterances end at 0.4 s of silence or after `--max-speech` (8 s) of continuous
  talking, whichever comes first, so a monologue still produces regular calls.
* `data/speakers.json` records which model produced its embeddings; mixing
  models is refused with a clear error.

## Cloud streaming mode (`voicerec live`)

The local pipeline waits for a pause before it answers. `voicerec live` streams
the microphone to [Speechmatics' real-time API](https://docs.speechmatics.com/api-ref/realtime-transcription-websocket)
and prints words as they are recognised, with a speaker on every word. It is the
mode to use when accuracy and latency matter more than running offline.

```bash
pip install speechmatics-rt                # already in .venv
echo 'SPEECHMATICS=your-key' > .env         # or export SPEECHMATICS_API_KEY=...; free tier at portal.speechmatics.com
voicerec cloud-enroll "Nikita"             # 25 s alone at the mic: the service learns the voice
voicerec cloud-enroll "Teammate"
voicerec live --log notes.txt              # streaming transcript, names on every turn
```

The key is read from `.env` in the project folder (`SPEECHMATICS`, `SPEECHMATICS_API_KEY`
or `SPEECHMATICS_KEY`) or from the environment. `.env` is gitignored. Free accounts
allow only one or two sessions at once: "Concurrent Quota Exceeded" means another
`voicerec live` is still open, or the last one closed seconds ago. Wait ten seconds.

Output is a running conversation, one line per sentence or speaker change, with
the provisional words of the current sentence shown on the status line as they
arrive:

```
18:52:01 Nikita: So the pipeline runs on the laptop, no cloud needed for the demo.
18:52:04 Teammate: Right, but the judges will want to see the latency.
18:52:06 Speaker 3: Can I interrupt for a second?
         (S3 sounds like David)
18:52:09 David: Sorry, which model is this again?
```

**Who is who.** Two mechanisms, used together:

* **Cloud identifiers.** `cloud-enroll` runs a short diarized session and asks the
  service for *speaker identifiers* (opaque, encrypted voiceprints that only work
  in your Speechmatics project). `live` sends them with every session and the
  service tags matching words with the name directly. Up to 50 identifiers in
  total; enrol each person once per acoustic setting you care about.
* **Local profiles.** Anyone the service only knows as `S1`, `S2`, ... is named
  with the local TitaNet profiles from `voicerec enroll`: the audio behind each
  label is identified locally and the label is renamed once two looks agree
  ("S3 sounds like David"). This works without cloud enrollment at all, and
  covers people who were enrolled locally but not in the cloud.

`--max-speakers` (default 4) is how many *un-enrolled* voices the service tells
apart. `--max-delay` (default 1.0 s) trades latency for accuracy; 0.7 is the
minimum. `--cloud-model enhanced` is the default; `standard` is cheaper and
faster. `--from FILE` streams a recording instead of the mic. `--jsonl` emits
`partial`, `turn` (with word timings) and `mapping` events for whatever you are
building; `--log FILE` keeps a plain `Name: text` transcript you can feed to an
LLM as context.

**Measured** (synthetic voices, `enhanced` model, `max_delay` 1.0): a five-turn
two-person conversation came back word for word with every turn attributed
correctly, both by the local profiles and by the cloud identifiers; from the
microphone, the first provisional words appeared about one second after speech
started, with 20 to 30 partial updates per sentence; cloud-enrolled voices were
named directly and a voice enrolled only locally was named after its first turn.

**What it does and does not do.** Diarization assigns one speaker per word, so
turn-taking and interruptions among several people work well; two people saying
different things at the same instant still come out as one stream of words
(the local `listen --multi` is the mode for that). Everything leaves the laptop:
the audio is sent to Speechmatics. Without a network or a key, `voicerec listen`
is the fallback. `scripts/fake_speechmatics.py` is a protocol stand-in used to
test the client without a key.

## The assistant (`voicerec assistant`)

A voice assistant that sits in the conversation. It has a code name, answers when
addressed, can speak up on its own when it has something specific to add, and
talks back in a natural voice.

```bash
echo 'ANTHROPIC_API_KEY=...' >> .env         # the brain is Claude; key from console.anthropic.com
voicerec assistant --name Nova --unmute 60 --ack   # add --interject to let it speak up unprompted
```

It says "Nova here." on start, which doubles as the audio check: if you do not hear
it, the laptop is muted or the wrong output device is selected. `--unmute 60`
unmutes and sets the macOS output volume on start; a muted output prints a warning
otherwise. `--output-device` picks another output (see `voicerec devices`).

* **Asking.** Say "hey Nova, what's the latency number again?" and it answers
  out loud, using everything said so far (with names) as context. A bare "Nova?"
  arms it for that person's next sentence. The code name is added to the
  recognizer's custom vocabulary so it is heard reliably; `--alias` adds other
  spellings the recognizer might produce.
* **Interjecting** (`--interject`). After each committed sentence it asks the
  model, under a strict policy, whether it has something worth adding: a factual
  correction, an answer to a question nobody answered, a number someone is
  reaching for, a real problem with a plan. Small talk never triggers it. At most
  one remark every `--interject-cooldown` seconds (default 45), two sentences max.
* **Interrupting it.** Say the code name, or "stop", while it is talking and it
  stops mid-sentence. Its own voice coming back through the microphone is
  recognised and dropped from the transcript.
* **Speaking.** Answers stream from the model and are spoken sentence by
  sentence, so the first words play while the rest is still being written.
  Voice engines: Supertonic 3 locally through sherpa-onnx (default; about ten
  times faster than real time on this laptop), Speechmatics TTS in the cloud
  (`--voice-engine speechmatics --voice sarah|theo|megan`, same key as `live`),
  or macOS `say` as a last resort. Unmute the laptop.
* **Brain.** `claude-opus-5-5` by default with low effort for snappy replies,
  streamed, with the server-side refusal fallback enabled; `--brain` picks another
  model, `--brain mock` is an offline stand-in used by the tests. The system prompt
  is cached across calls. Its lines appear in the transcript, the log and the
  JSONL stream (`type: "assistant"`), so later questions can refer to them.

Everything `live` does applies: cloud identifiers, local naming of S-labels,
`--log`, `--jsonl`, `--from FILE`.

### Response time

Measured from the end of the question to the first spoken word (real recognizer,
real model, Supertonic voice), the chain is:

| stage | time | lever |
| --- | --- | --- |
| recognizer finalizes the sentence | 0.8 s | this is the service's minimum commit delay (`--max-delay 0.7`) plus network; `--eou` (0.5 s of silence by default) only matters when someone trails off without finishing a sentence |
| model's first token | 0.7 s quiet, up to 1.5 s under load | the same on Opus 5.5, Sonnet 5.5 and Haiku 5.5, so `--brain` is about answer quality and length, not speed; the HTTPS connection is warmed at start |
| tokens until the first clause | ~0.2 s | the first chunk goes out at the first comma or sentence end |
| synthesis of that chunk | ~0.3 s | Supertonic runs ten times faster than real time; the voice is warmed up at start |

Total: the first answer word plays **2 to 2.5 s** after you stop talking. With
`--ack` the assistant says a pre-synthesized "Sure." or "Okay." at **1.3 s**
whenever the model has not started within half a second, so there is never dead
air; the answer itself is not delayed by it beyond the half second the filler
takes to say. Every
complete sentence is spoken as soon as it ends, and the last sentence is flushed
150 ms after tokens stop instead of waiting for the stream to close. Each answer
prints a timing note like `(first answer word after 0.8 s to hear it, 0.7 s
thinking, 0.3 s voice)` so you can see where time goes.

Known limit: without headphones the laptop hears itself, so echo is filtered by
timing and by matching the words it just said. Someone talking *over* the
assistant gets through only if their words differ from its own, and a loud room
full of side conversations shows up as `Speaker N` lines that the assistant also
reads as context.

## Simultaneous talkers (`--multi`)

```
mixture ──► SepFormer (2 sources) ──► stream A ──► TitaNet ──► vs separation-domain voiceprints ──┐
                                  └─► stream B ──► TitaNet ──┘                                     ├─► who is talking
whole mixture ──► TitaNet ──► vs clean voiceprints ────────────────────────────────────────────────┘
```

* **Why a second voiceprint.** A separated stream carries artifacts, so it scores
  only 0.4 to 0.5 against a clean-speech profile. Enrolling with `--multi` also
  runs the person's enrollment audio through the separator and stores those
  embeddings; separated streams are compared against that, which brings genuine
  scores back to 0.7 to 0.9. The price is that look-alike voices score higher too
  (two teammates sat at 0.74 in this domain), which is why ranking is done in the
  centered space described above, and streams use their own bar,
  `--stream-threshold` (default `threshold + 0.07`).
* **Deciding who is real.** Streams with under 10% of the energy are dead
  outputs. Two streams naming the same person collapse into one. A stream that
  misses the bar but whose closest match was already found is residue of that
  person. A near miss whose top candidate leads the runner-up by 0.15 is accepted.
  A stream nobody matches counts as **Unknown** only if it carries at least 30% of
  the energy and shows up in at least half the chunks of the utterance. Never more
  talkers than the separator has outputs. When only one voice is left, the plain
  whole-mix answer is used, because for a single voice it is the better evidence;
  if that whole-mix answer ranks a second enrolled person at 0.45 or above (one
  voice never scores a runner-up that high), the separator missed a talker and
  both are reported. Finally the streams' story must agree with the whole mix:
  if nobody the streams named reaches the threshold on the un-separated audio,
  the claims are artifacts (typically a stranger split in two) and the whole-mix
  answer, usually Unknown, is reported instead.
* **Latency.** Separation runs on the Apple GPU at roughly four times real time,
  so a 5 s utterance is labelled about 1.3 s after it ends. Identification runs on
  a worker thread; the mic loop never falls behind, and provisional guesses are
  skipped while the worker is busy.
* **Limits.** The separator handles at most two simultaneous voices. It assumes
  the people talking are enrolled: a stranger talking over an enrolled person
  tends to be attributed to the most similar enrolled voice, whereas a stranger
  talking alone is still reported as Unknown. Very robotic voices (macOS legacy
  voices such as Albert) are not treated as speech by the separator at all.

Measured results:

| test | result |
| --- | --- |
| `eval_mixtures.py`, clean synthetic mixtures, robotic Albert excluded | both named 19 of 20 at equal loudness, 10 of 10 with one voice 6 dB quieter; lone talker reported as one talker 12 of 12 |
| `loopback_test.py --multi`, quiet room, both voices through one loudspeaker into the laptop mic | 10 of 10: six enrolled pairs, two lone talkers, a lone stranger as Unknown, an enrolled talker plus a stranger |
| same, with people talking in the background | about three pairs in four |

The remaining known failure is a stranger talking *over* an enrolled person: the
stranger's stream may be labelled as the most similar enrolled voice.

## Transcription (`--transcribe`)

Speech-to-text runs through sherpa-onnx too, with
[Moonshine base](https://github.com/usefulsensors/moonshine) (English, int8,
288 MB on disk). It is built for short utterances and costs about 2% of the
audio's duration on CPU, so it adds nothing noticeable to latency. Each final
utterance is transcribed after it is identified; with `--multi` and two talkers,
each person's *separated stream* is transcribed, which is how overlapping speech
gets two separate lines. Measured on the synthetic voices: 13% word error rate,
mostly on the robotic legacy voices and clipped first words; a quarter-second of
pre-roll is now kept in front of every segment for that reason. Another
sherpa-onnx offline model (for example a Whisper export) can be used by pointing
`--asr-model` at its folder.

## Tuning the threshold

The default is `0.45`. Two measurements with TitaNet-small on synthetic voices
set the scale; real people score lower (see below):

| test | genuine scores | impostor scores |
| --- | --- | --- |
| `eval_synthetic.py`: 8 TTS voices, clean files | 0.92 to 0.98 | up to 0.56 (two robotic voices) |
| `loopback_test.py`: enroll **and** test through speakers and the laptop mic | 0.84 to 0.90 | 0.32 to 0.45 |

Enrolling from clean files but testing through the mic dropped a genuine
score to 0.46, so enroll in the same room and mic you will demo with. Synthetic
voices are unusually self-consistent; with four real people on a laptop mic in a
hackathon room the right person scored well under 0.55, which is why the default
bar is 0.45.

Real human voices on a laptop mic in a busy room score lower than those tests.
Two things keep names showing up anyway:

* **Clear-winner rule.** A best match up to 0.10 under the threshold is still
  accepted when it leads the runner-up by at least 0.20 in the centered space.
  With a handful of enrolled people that is almost always right; the cost is that
  a stranger who resembles one enrolled person gets that person's name more
  often. Turn it off with `--no-rescue` when strangers matter more than misses.
* **Lower the bar.** If people still come back `Unknown` with the right name after
  `closest:`, run `listen --threshold 0.35` (the stream threshold for `--multi`
  follows it). `--debug` prints every utterance's full ranking, and each
  separated stream's with `--multi`, which is the fastest way to pick a value. Scores under about 0.35 for the right person mean the enrollment
  does not match the test conditions: re-enroll in that room.

* Enrolled people showing up as Unknown: lower `--threshold`, or enroll more
  audio in the conditions you demo in (`voicerec enroll NAME` again).
* Strangers matched to someone: raise it, and check `voicerec matrix` for two
  enrolled people who sound alike.

The WeSpeaker CAM++ model (`scripts/download_models.sh --all`) is also
supported but scored only 9/16 on the same synthetic test, so it is not the default.

## Testing without a human

```bash
scripts/make_synthetic_speakers.sh /tmp/tts        # macOS `say` voices, 4 clips each
python scripts/eval_synthetic.py /tmp/tts          # accuracy + threshold sweep
voicerec enroll Karen --db /tmp/t.json --from /tmp/tts/Karen/s1.wav /tmp/tts/Karen/s2.wav
python scripts/loopback_test.py --db /tmp/t.json Karen "?Moira"   # plays through speakers, listens on the mic

# simultaneous talkers: enroll through the speakers with --multi, then play two voices at once
python scripts/eval_mixtures.py /tmp/tts                           # clean synthetic mixtures
python scripts/loopback_test.py --db /tmp/m.json --multi --enroll-first "Karen+Daniel" "Rishi+Karen" "Karen" "?Moira"

# the assistant without an Anthropic key: mock brain, real recognition, real voice
voicerec assistant --name Nova --brain mock --interject --jsonl &
say -v Karen "Hey Nova, what time is it right now?"              # answered out loud ~2.5 s after the question ends
```

## Troubleshooting

* **Nothing is detected**: run `voicerec devices` and pass `--device`; on macOS
  make sure your terminal has Microphone permission (System Settings →
  Privacy & Security → Microphone).
* **"model not found"**: run `scripts/download_models.sh`.
* **"holds embeddings from model X"**: the database was built with a different
  model. Pass `--model` for that one or `voicerec reset --yes` and re-enroll.
* Scores feel low on a far-field mic: enroll in the same setup you demo in.

## Layout

```
voice_rec/
  audio.py        mic capture (sounddevice), file loading, resampling
  vad.py          Silero VAD wrapper -> speech segments
  embedder.py     sherpa-onnx speaker embedding extractor
  store.py        JSON persistence of enrolled embeddings
  recognizer.py   cosine matching + threshold -> Match; MultiRecognizer for simultaneous talkers
  separator.py    SepFormer speech separation (optional, PyTorch)
  transcriber.py  Moonshine speech-to-text via sherpa-onnx
  cloud.py        Speechmatics streaming session, turn builder, local naming of S-labels
  assistant.py    the assistant: context, wake word, Claude brain, voices, barge-in
  cli.py          the voicerec command
scripts/
  download_models.sh, make_synthetic_speakers.sh, eval_synthetic.py, eval_mixtures.py, loopback_test.py,
  fake_speechmatics.py (protocol stand-in for testing `live` without a key)
models/           ONNX models (gitignored)
data/             speakers.json (gitignored)
```
