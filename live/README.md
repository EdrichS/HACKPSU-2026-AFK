# Live: the patient's laptop during a visit

`python -m live` is the demo-day program. It opens the webcam and the microphone and names the
people it sees and hears from the database, announces them, keeps the visit's transcript, has
Gemini summarize it into each visitor's facts and card, and answers questions as Nova.

```
docker compose up -d --wait db
uv run python -m live
```

Add `--no-camera` for microphone only, `--no-tts` to print instead of speaking, `--no-nova` to
turn off Nova (Claude), `--no-summary` to skip the Gemini visit summary, and `--help` for the
rest.

## One id for a face and a voice

Both recognizers resolve to `people.id`, nothing else:

- a face's 128 numbers are matched against `face_samples` with `db.match.nearest_people` and
  `decide` (L2, cutoff 0.6, and the runner-up must trail by `--face-margin`);
- a voice's 192 numbers are matched against `voice_samples` the same way (cosine, cutoff 0.55,
  `--voice-margin`), except that a voice up to 0.10 past the cutoff is still named when it leads
  the runner-up by 0.20 (`live/voices.py`).

Nothing is loaded into memory at start: every face and every utterance is matched against the
tables as they are now. Enroll someone with `python -m enroll` and the live program knows them
on their next sentence. The one exception is the user, who is read once at start (see The user).
Only people in the database can ever be named; anyone else is "unknown" on camera, and on the
microphone any voice the database can't name, including a not-sure match, is attributed to the
user.

`live/presence.py` merges the two: a voice match counts at once, a face needs two sightings
within three seconds. Each arrival is announced once, with the sentence the contract fixes
(`That's David, your grandson.`); someone who leaves and comes back is announced again only if
at least five minutes have passed since their last announcement.

## The user

The user is the person wearing the glasses, registered with `python -m enroll --user NAME`
(their `people` row has the relationship `user`). Their voice is recognized and labelled like
anyone's, but they are never announced, never counted as a visitor, and never summarized. A voice
the database doesn't know is attributed to them too, since they are the one person always there.
`--user NAME` sets the name on the user's lines, overriding the registered user's name if there
is one.

## Without the camera

The microphone path never depends on the camera: every utterance is matched against
`voice_samples` and transcribed whether or not a face is in view, so a visitor who is off to the
side or behind the wearer is still named and logged. Who is present only breaks a tie between
two voices that are too close to call, and present means seen or heard in the last 20 seconds,
so that works without the camera too. Face detection runs on its own thread at most `--face-rate`
times a second (3 by default, with `--face-upsample 0`), so it can't starve the microphone.

To prove the voice-only path, or to demo without talking, play a recording through the pipeline:

```
uv run python -m live --no-camera --audio-file data/voice/<some-enrollment>.wav --audio-speed 4
```

## The visit and Gemini

Every utterance is transcribed locally (Moonshine via sherpa-onnx) and logged as a speaker-labelled
line. The visit ends on `e` in the window, after `--visit-timeout` seconds of silence (120 by
default), or when the program exits. Then the transcript goes, once per known visitor, to the
context owner's `backend.gemini.update_context`: a facts call adds new facts (source
`conversation`) and a card call rewrites `people.small_context`, with no database connection held
meanwhile. A failed facts call changes nothing; a failed card call still keeps the facts. It needs
`GEMINI_API_KEY` in the repo's `.env`. The same call serves `POST /people/{id}/conversation` and
the wizard's notes, so there is one path for context.

## Nova

Nova is the one thing on Anthropic; `ANTHROPIC_API_KEY` is for her alone.

Say "Nova, who is David?" (or "Hey Nova, who's here?"). The wake word, question window, barge-in
and echo suppression come from `voice_rec.assistant`. The brain is `live/nova.py`: Claude with
three tools. `list_people` and `person_context(name)` read Postgres, and `who_is_here` reads who
the program sees and hears right now. The system prompt tells it the database is the only source
of truth, so it looks a person up before answering and says so when someone isn't registered.
The answer is spoken with the local Supertonic voice (macOS `say` if the model folder is missing).

## Echo, and what leaves the laptop

The microphone keeps listening while the program speaks. Only Nova's echo suppression drops the
program's own voice, so without Nova its announcements can land in the transcript as the user's
lines. Visit transcripts go to Gemini, and Nova sends names, cards, facts and the recent
conversation to Anthropic; photos and audio stay on the laptop.

## Keys and setup

In the camera window, `q` quits, `e` ends the visit now and `w` asks who is here. Ctrl-C quits
from the terminal. With `--no-camera` there is no window, so Ctrl-C is the only key, and the
visit ends on the silence timeout or when you quit.

- `ANTHROPIC_API_KEY` (Nova) and `GEMINI_API_KEY` (visit summaries) go in the repo's gitignored
  `.env`.
- Models in `hackpsu_voice_rec/models/`: TitaNet and Silero (enrollment too), Moonshine for
  transcription, Supertonic for the voice. `hackpsu_voice_rec/scripts/download_models.sh` fetches
  them all.
- macOS asks for camera and microphone permission for the terminal the first time.
