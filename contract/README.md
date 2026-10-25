# Nametags contract

What the face, voice, backend and frontend parts hand each other. The Python models live in this
folder:
- `embedders.py`: what the face and voice owners implement;
- `setup_api.py`: the setup and person-context routes;
- `live.py`: the `/live` WebSocket messages.

The mock server serves all of it from memory, so you can build against it before the real backend
exists.

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
  1 − cosine similarity, so SpeechBrain's default similarity threshold of 0.25 becomes a cutoff of
  0.75.
- Run `check_face_embedder` or `check_voice_embedder` on your real code. They fail loudly on:
  - a wrong number of values, or a NaN or infinite value;
  - an all-zero embedding;
  - a box outside the image, or a box with no area;
  - a blank `model`.

## Setup and person-context routes

- **Boxes** are `{x, y, width, height}` in integer pixels of the submitted image, from the top
  left.
- **Audio** is WAV, 16 kHz, mono, 16-bit, and at least 1 second long.
- **Photos** are JPEG or PNG. Phone photos that carry a second image (Ultra HDR, portrait) count
  as JPEG.
- **Browsers:** a page served from any port on `localhost` or `127.0.0.1` may call both apps.
  Pages from other sites can't.

| Method and path | Body | Returns |
|---|---|---|
| `GET /people` | — | `list[Person]` |
| `POST /people` | `PersonIn` | `201 Person`; 409 if a person with the same name and relationship exists |
| `PATCH /people/{id}` | `PersonPatch` | `Person`; 404; 409 as for POST |
| `DELETE /people/{id}` | — | `204`, or 404 |
| `POST /photos` | multipart `file` (JPEG or PNG) | `201 PhotoOut` |
| `GET /photos` | — | `list[PhotoOut]`, with each face's current label |
| `GET /photos/{id}/image` | — | the stored image; 404 for an unknown photo |
| `POST /faces/{face_id}/assign` | `AssignIn` (`person_id`, or null to unlabel) | `204`; 404 for an unknown face or person; 409 if that person is already labelled on another face in this photo |
| `POST /people/{id}/voice` | multipart `file` (WAV) | `201 VoiceOut`; 422 for a wrong format or a recording under 1 second; 404 for an unknown person |
| `GET /people/{id}/voice` | — | `list[VoiceSample]`, oldest first; 404 for an unknown person |
| `DELETE /people/{id}/voice/{voice_sample_id}` | — | `204`; 404 if that person has no such recording |
| `POST /people/{id}/notes` | `NotesIn` | `Person` with the updated card; 404 for an unknown person |
| `POST /people/{id}/conversation` | `ConversationIn` | `Person` with the updated card; 404 for an unknown person |
| `GET /people/{id}/facts` | — | `list[Fact]`; 404 for an unknown person |
| `DELETE /people/{id}/facts/{fact_id}` | — | `204`; 404 if that person has no such fact |

"The same name and relationship" ignores case and surrounding spaces.

## `/live` messages

**The backend composes every spoken sentence.** The frontend speaks `text` exactly as it arrives.
To mute the mic while the app is speaking, the frontend simply stops sending audio.

From the browser:

```json
{"type":"frame","ts":1761350400000,"jpeg":"/9j/4AAQSkZJRg..."}
{"type":"audio","ts":1761350400500,"wav":"UklGRiQAAABXQVZF..."}
{"type":"who"}
```

From the server. `present` is sent after every frame, for the on-screen labels:

```json
{"type":"present","people":[{"person_id":1,"name":"David","relationship":"grandson","small_context":"David is your grandson. He just moved to Pittsburgh and works as a nurse."}],"faces":[{"box":{"x":212,"y":96,"width":148,"height":148},"state":"named","person_id":1},{"box":{"x":430,"y":120,"width":120,"height":120},"state":"unsure","person_id":null}]}
{"type":"arrived","person":{"person_id":1,"name":"David","relationship":"grandson","small_context":"David is your grandson. He just moved to Pittsburgh and works as a nurse."},"via":"face","text":"That's David, your grandson."}
{"type":"unknown","text":"I don't recognize this person."}
{"type":"who_answer","text":"That's David, your grandson, and Maria, your daughter."}
{"type":"error","message":"Unrecognised message; expected frame, audio or who."}
```

When nobody known is present, `who_answer` says "I don't see anyone I know right now."

These examples were generated with `model_dump_json()` from the models in `live.py`. After
changing the models, regenerate them.
