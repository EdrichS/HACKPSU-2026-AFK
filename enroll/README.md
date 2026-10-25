# Enrolling a person

`python -m enroll` registers one person for Nametags from the command line: their face from
the webcam (optional), their voice from the microphone, and a few typed facts. It writes to the
same Postgres tables the backend serves, through the same `db` functions, so what it stores is
exactly what `db/schema.sql` describes:

| Step | Table(s) | Via |
|---|---|---|
| name + relationship | `people` | `db.people.create_person` (or reuses the existing row) |
| each photo | `photos`, `face_samples` | `db.photos.save_photo`, then `assign_face` labels the one clear face |
| the recording | `voice_samples` | `db.voice.add_voice`, one row per clip |
| the facts | `facts` (source `notes`), `people.small_context` | `db.context.save_context` |

Photos and recordings land under `data/photos/` and `data/voice/` with random names, where the
backend keeps its own, so `GET /photos/{id}/image` serves them.

## Two kinds of person

The app has one **user**: the person wearing the glasses the camera and microphone are in.
Everyone else is registered **relative to them** (son, daughter, friend). Both are rows in
`people`; the user's row has the relationship `user`, which is how the live program knows whose
voice never to announce or summarize. Register the user first:

```
docker compose up -d --wait db
uv run python -m enroll --user "Rose"
```

That records their voice and asks for a few facts; it takes no photos, since the glasses never
see the wearer (add `--face` if you want some anyway). Then register the people in their life:

```
uv run python -m enroll "David" son
```

With no arguments at all it asks which of the two you are registering.

## Run it

It asks whether to take photos, then a camera window pops up and walks through five head poses
(front, left, right, up, down): hold still for a second once your face is boxed in green, or
click the shutter button (or press space) to take the photo now; `s` skips a pose, `q` stops.
Each shot flashes and joins a thumbnail strip. Then a recording window pops up: click the red
button, read the passage it shows, and keep talking until the bar fills with 10 seconds of
speech (silence doesn't count). Finally, back in the terminal, it asks for a few facts, one
sentence each, ending with an empty line. `--no-window` does it all in the terminal instead.

macOS asks for camera and microphone permission for your terminal the first time.

Without a camera or microphone, enroll from files:

```
uv run python -m enroll "David" grandson --photo d1.jpg d2.jpg --audio david.wav \
    --context "David is your grandson. He works as a nurse in Pittsburgh."
uv run python -m enroll --list
```

`--list` marks the user's row with `*`. `--help` lists everything: `--skip-face`, `--skip-voice`, `--seconds 15`, `--poses front,left,right`,
`--shots 2`, `--mic "MacBook"`, `--camera 1`, `--database-url`, `--data-dir`, `-y` to never ask.

## What it checks

- Before writing anything it runs `db.connect.check_embedders`: the tables must be `vector(128)`
  for faces and `vector(192)` for voices (they are), and must not already hold samples from a
  different model.
- A photo with no face is not stored. A photo with several faces of similar size is stored
  unlabelled, for the family to label in the setup UI; a clearly dominant face is labelled.
- Recordings are 16 kHz mono 16-bit WAV, at least a second long, with silences cut out. The
  whole recording is one sample; each 4-second slice of it is another (`--window 0` turns that
  off). Matching uses a person's best sample, so more samples help.
- Facts and the card stay within 300 characters each; a long text is split by sentence.

## The embedders

`embedders/face.py` and `embedders/voice.py` are the real `FaceEmbedder` and `VoiceEmbedder`
behind the contract, on `facerec` (face_recognition 1.3, 128 numbers, L2, cutoff 0.6) and
`voice_rec` (TitaNet small, 192 numbers, cosine, cutoff 0.55). The backend can swap them in for
the fakes in `backend/app.py`. Once this script has stored real samples, a backend still running
the fakes refuses to start, by design: switch it to these two classes.

Models: the speaker and VAD models go in `hackpsu_voice_rec/models/` (run
`hackpsu_voice_rec/scripts/download_models.sh`). dlib builds from source on `uv sync`; it needs a
C++ compiler and CMake (`xcode-select --install`, `brew install cmake`).
