# Nametags contract

What the face, voice, backend and frontend parts hand each other. The Python models live in this
folder:
- `embedders.py`: what the face and voice owners implement;
- `setup_api.py`: the setup and person-context routes;
- `live.py`: the `/live` WebSocket messages;
- `audio.py`: the one audio format, checked by every route that takes a recording;
- `fakes.py`: stand-in embedders for the mock and the tests.

The enrollment wizard's models live with its routes in `backend/enroll_api.py`, and Nova's in
`backend/nova_api.py`.

The mock server serves the setup routes and `/live` from memory, so you can build against them
without Postgres or the face and voice models.

## Run the mock

From the repo folder:

```
uv run uvicorn mock.app:app --port 8000
```

It makes no network calls.
- It "sees" one fake person on every `/live` frame.
- For notes and conversations, it stores the text as one fact and sets a placeholder card.

## Face and voice owners

- Implement `FaceEmbedder.detect_faces(image: bytes) -> list[FaceDetection]` or
  `VoiceEmbedder.embed_voice(wav: bytes) -> list[float]`, plus a `spec: EmbedderSpec`
  (`dimensions`, `metric`, `cutoff`, `model`).
- `cutoff` is a **distance**, and a match must be strictly under it. Cosine distance is
  1 − cosine similarity, so the voice package's similarity threshold of 0.45 becomes a cutoff of
  0.55 (`embedders/voice.py`).
- The live path (`python -m live` and `/live`) loosens that for voices only: a voice up to 0.10
  past the cutoff is still named when it leads the runner-up by at least 0.20 (`live/voices.py`).
- Run `check_face_embedder` or `check_voice_embedder` on your real code. They fail loudly on:
  - a wrong number of values, or a NaN or infinite value;
  - an all-zero embedding;
  - a box that starts left of or above the image, or a box with no area (a box running past the
    right or bottom edge isn't caught here);
  - a cutoff of 0 or less, or a blank `model`.

## Setup and person-context routes

- **Boxes** are `{x, y, width, height}` in integer pixels of the submitted image, from the top
  left.
- **Audio** is WAV, 16 kHz, mono, 16-bit, and at least 1 second long.
- **Photos** are JPEG or PNG. Phone photos that carry a second image (Ultra HDR, portrait) count
  as JPEG.
- **Browsers:** a page served from any port on `localhost` or `127.0.0.1` may call both apps, and
  the backend also allows the sites listed in `NAMETAGS_CORS_ORIGINS`. That is CORS, so it only
  stops other pages from reading replies and from sending JSON, PATCH and DELETE requests. It
  doesn't cover the `/live` WebSocket or form uploads: any page in a browser that can reach the app
  can open `/live` and read its messages, and can send uploads (photos, recordings, `/enroll`)
  without seeing the reply.

| Method and path | Body | Returns |
|---|---|---|
| `GET /people` | — | `list[Person]` |
| `GET /people/{id}` | — | `Person`, or 404 *(real backend only)* |
| `POST /people` | `PersonIn` | `201 Person`; 409 if a person with the same name and relationship exists |
| `PATCH /people/{id}` | `PersonPatch` | `Person`; 404; 409 as for POST |
| `DELETE /people/{id}` | — | `204`, or 404 |
| `POST /photos` | multipart `file` (JPEG or PNG) | `201 PhotoOut` |
| `GET /photos` | — | `list[PhotoOut]`, with each face's current label |
| `GET /photos/{id}/image` | — | the stored image; 404 for an unknown photo |
| `DELETE /photos/{id}` | — | `204`, the photo and every face in it are gone; 404 for an unknown photo *(real backend)* |
| `POST /faces/{face_id}/assign` | `AssignIn` (`person_id`, or null to unlabel) | `204`; 404 for an unknown face or person; 409 if that person is already labelled on another face in this photo |
| `POST /people/{id}/voice` | multipart `file` (WAV) | `201 VoiceOut`; 422 for a wrong format or a recording under 1 second; 404 for an unknown person |
| `GET /people/{id}/voice` | — | `list[VoiceSample]`, oldest first; 404 for an unknown person |
| `GET /people/{id}/voice/{voice_sample_id}/audio` | — | the recording (WAV); 404 if that person has no such recording *(real backend)* |
| `DELETE /people/{id}/voice/{voice_sample_id}` | — | `204`; 404 if that person has no such recording |
| `POST /people/{id}/notes` | `NotesIn` | `Person` with the updated card; 404 for an unknown person |
| `POST /people/{id}/conversation` | `ConversationIn` | `Person` with the updated card; 404 for an unknown person |
| `GET /people/{id}/facts` | — | `list[Fact]`; 404 for an unknown person |
| `POST /people/{id}/facts` | `FactIn` | `201 Fact` stored as typed (source `notes`, no Claude); 409 for a repeat; 422 if blank *(real backend)* |
| `PATCH /people/{id}/facts/{fact_id}` | `FactIn` | `Fact` reworded; 404; 409 if another fact already says that *(real backend)* |
| `DELETE /people/{id}/facts/{fact_id}` | — | `204`; 404 if that person has no such fact |
| `POST /people/{id}/card` | — | `Person` with the card written again by Claude from the stored facts; 422 with no facts, 503 without Claude, 502 when it gives no usable card (the old card stays) *(real backend)* |

"The same name and relationship" ignores case and surrounding spaces.

## The enrollment wizard and the rest (real backend only)

The self-enrollment wizard (consent, three photos, a recording, name and relationship) talks to
these. The checks are stateless, so the wizard can give feedback before it knows the name; the
upload at the end carries everything. Run the real backend with Docker or on a laptop
(`DEPLOY.md`); interactive docs at `/docs`.

| Method and path | Body | Returns |
|---|---|---|
| `GET /health` | — | `{status, face_model, voice_model, transcription, captions, claude, claude}`: `captions` is `speechmatics`, `local` or `off`; `claude` false means notes and visits are stored as typed or not at all |
| `GET /user` | — | `Person` for the app's user: the earliest person whose relationship is `user` or `patient`, in any case; 404 if none yet |
| `POST /enroll/check/photo` | multipart `file` (JPEG or PNG) | `{ok, faces, box, width, height, reason}`: `ok` when the photo has one face, or one face at least 1.5 times the area of the next; 422 for a non-image |
| `POST /enroll/check/voice` | multipart `file` (WAV, 16 kHz mono 16-bit) | `{ok, seconds, speech_seconds, reason}`: `ok` with 3+ seconds of speech |
| `POST /enroll` | multipart: `name`, `relationship` (or `user` for the wearer), optional `notes` (a sentence per fact), optional `merge=true`, `photos` (0..n files), `voice` (0..1 file) | `201 {person, photo_ids, face_ids, voice_sample_ids, facts, skipped_photos}`; 409 if that name and relationship exist (unless `merge`); 422 for no clear face in any photo, too little speech, or a bad name |
| `POST /nova/ask` | `{question, asker?}` | `{text}` to speak; 503 without an Anthropic key |

`photo_ids[0]` is the first photo stored, normally the front shot: `GET /photos/{id}/image` shows
it on the thank-you page. A photo without one clear face isn't stored, and `skipped_photos` says
why. Each stored photo keeps every face found: the chosen face labelled, any others unlabelled.
The recording stores the whole speech and each 4-second slice as separate voice samples; notes
become `facts` (source `notes`) and the card, through Claude when it is on and as typed otherwise.
Relationship is free text (son, daughter, grandson, granddaughter, friend, caregiver, or whatever
"Other" says), 1-40 characters.

The backend also serves the rough test UI at `/ui/` (`/` redirects there), FastAPI's docs at
`/docs` and `/redoc`, and the schema at `/openapi.json`.

## `/live` messages

**The backend composes every spoken sentence.** The frontend speaks `text` exactly as it arrives.
To mute the mic while the app is speaking, the frontend simply stops sending audio.

From the browser:

```json
{"type":"frame","ts":1761350400000,"jpeg":"/9j/4AAQSkZJRg..."}
{"type":"audio","ts":1761350400500,"wav":"UklGRiQAAABXQVZF..."}
{"type":"who"}
```

From the server. `present` is sent after every frame that decodes, for the on-screen labels; a
frame that doesn't decode gets only an `error`:

```json
{"type":"present","people":[{"person_id":1,"name":"David","relationship":"grandson","small_context":"Lives in Pittsburgh · Works as a nurse | Ask about: the new job","facts":["David works as a nurse.","David loves cars.","David moved to Pittsburgh in September 2026."]}],"faces":[{"box":{"x":212,"y":96,"width":148,"height":148},"state":"named","person_id":1},{"box":{"x":430,"y":120,"width":120,"height":120},"state":"unsure","person_id":null}]}
{"type":"arrived","person":{"person_id":1,"name":"David","relationship":"grandson","small_context":"Lives in Pittsburgh · Works as a nurse | Ask about: the new job","facts":["David works as a nurse.","David loves cars.","David moved to Pittsburgh in September 2026."]},"via":"face","text":"That's David, your grandson."}
{"type":"unknown","text":"I don't recognize this person."}
{"type":"who_answer","text":"That's David, your grandson, and Maria, your daughter."}
{"type":"error","message":"Unrecognised message; expected frame, audio or who."}
```

When nobody known is present, `who_answer` says "I don't see anyone I know right now." The
`error` text above is the mock's; the real backend's also lists `end_visit`.

The real backend (`backend/`) adds, in both directions:

```json
{"type":"end_visit"}
```

```json
{"type":"caption","person_id":1,"speaker":"David","text":"Hi Grandma, I brought","final":false,"start":12.4,"end":12.4}
{"type":"caption","person_id":1,"speaker":"David","text":"Hi Grandma, I brought the photos.","final":true,"start":12.4,"end":15.1}
{"type":"answer","question":"who is David?","text":"David's your grandson. He just moved to Pittsburgh."}
{"type":"visit_saved","person_id":1,"name":"David","new_facts":["David moved to Pittsburgh in September 2026."],"small_context":"Last spoke about: the move · Lives in Pittsburgh · Works as a nurse | Ask about: the new apartment"}
```

- `caption` is an utterance with who said it. Only a voice matched in `voice_samples` (the
  user's own included) gets a `speaker` and a `person_id`; any other voice, a not-sure match
  included, has both null. With cloud captions on (`SPEECHMATICS_API_KEY`) a sentence first
  arrives while it is being said, with `final: false`, each such caption replacing the previous
  one, and then once more finished with `final: true`; local captions send finished sentences only.
- `answer` is Nova's reply when a caption started with the wake word.
- `visit_saved` follows `end_visit`, once per visitor whose facts or card changed. Closing the
  socket also ends the visit and saves it, without these messages.
- `present.people[].facts` carries each person's three newest facts, oldest first, for the bullets
  beside a name. The mock sends it empty, and sends no `caption`, `answer` or `visit_saved`.

These examples were generated with `model_dump_json()` from the models in `live.py`. After
changing the models, regenerate them.
