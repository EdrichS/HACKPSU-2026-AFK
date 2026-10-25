# Live: the patient's laptop during a visit

`python -m live` is the demo-day program. It opens the webcam and the microphone and names the
people it sees and hears from the database, announces them, keeps the visit's transcript, has
Claude summarize it into each visitor's facts and card, and answers questions as Nova.

```
docker compose up -d --wait db
uv run python -m live
```

Add `--no-camera` for microphone only, `--no-tts` to print instead of speaking, `--no-nova` or
`--no-summary` to leave Claude out, and `--help` for the rest.

## One id for a face and a voice

Both recognizers resolve to `people.id`, nothing else:

- a face's 128 numbers are matched against `face_samples` with `db.match.nearest_people` and
  `decide` (L2, cutoff 0.6, and the runner-up must trail by `--face-margin`);
- a voice's 192 numbers are matched against `voice_samples` the same way (cosine, cutoff 0.55,
  `--voice-margin`).

Nothing is loaded into memory at start: every face and every utterance is matched against the
tables as they are now. Enroll someone with `python -m enroll` and the live program knows them
on their next sentence. Only people in the database can ever be named; anyone else is "unknown"
on camera and attributed to the patient on the microphone.

`live/presence.py` merges the two: a voice match counts at once, a face needs two sightings
within three seconds. Each arrival is announced once, with the sentence the contract fixes
(`That's David, your grandson.`); someone who leaves and returns is announced again after five
minutes at most.

## The user

The user is the person wearing the glasses, registered with `python -m enroll --user NAME`
(their `people` row has the relationship `user`). Their voice is recognized and labelled like
anyone's, but they are never announced, never counted as a visitor, and never summarized. A voice
the database doesn't know is attributed to them too, since they are the one person always there.
`--user NAME` overrides the name when nobody is registered as the user yet.

## Without the camera

The microphone path never depends on the camera: every utterance is matched against
`voice_samples` and transcribed whether or not a face is in view, so a visitor who is off to the
side or behind the wearer is still named and logged. The camera only breaks a tie between two
voices that are too close to call. Face detection runs on its own thread at most `--face-rate`
times a second (3 by default, with `--face-upsample 0`), so it can't starve the microphone.

To prove the voice-only path, or to demo without talking, play a recording through the pipeline:

```
uv run python -m live --no-camera --audio-file data/voice/<some-enrollment>.wav --audio-speed 4
```

## The visit and Claude

Every utterance is transcribed locally (Moonshine via sherpa-onnx) and logged as a speaker-labelled
line. The visit ends on `e` in the window, after `--visit-timeout` seconds of silence (120 by
default), or when the program exits. Then, for each known visitor who was there, one Claude call
(`claude-opus-5-5`, structured JSON output, server-side refusal fallback enabled) reads the
visitor's existing facts and the transcript and returns:

```json
{"new_facts": ["Moved to Pittsburgh last month"], "small_context": "David is your grandson. He just moved to Pittsburgh and works as a nurse."}
```

`db.context.save_context` adds the facts with source `conversation` and overwrites
`people.small_context`. A failed call, a refusal or bad JSON changes nothing. The prompt follows
the design's rules: only facts about the visitor, skip repeats, newer facts win, nothing about
illness or bad news on the card, two short sentences.

## Nova

Say "Nova, who is David?" (or "Hey Nova, who's here?"). The wake word, question window, barge-in
and echo suppression come from `voice_rec.assistant`. The brain is `live/nova.py`: Claude with
three tools that read Postgres, `list_people`, `person_context(name)` and `who_is_here`. The
system prompt tells it the database is the only source of truth, so it looks a person up before
answering and says so when someone isn't registered. The answer is spoken with the local
Supertonic voice (macOS `say` if the model folder is missing).

## Keys and setup

`q` quits, `e` ends the visit now, `w` asks who is here. Ctrl-C quits from the terminal.

- `ANTHROPIC_API_KEY` goes in the repo's gitignored `.env`.
- Models in `hackpsu_voice_rec/models/`: TitaNet and Silero (enrollment too), Moonshine for
  transcription, Supertonic for the voice. `hackpsu_voice_rec/scripts/download_models.sh` fetches
  them all.
- macOS asks for camera and microphone permission for the terminal the first time.
