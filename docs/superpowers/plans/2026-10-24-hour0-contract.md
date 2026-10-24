# Hour-0 Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pin down, as code all four teammates import, what passes between the face, voice, backend
and frontend parts. Ship it with a mock server, so each person can build against the contract
before the others are done.

**Architecture:**
- A small Python package, `contract/`, holds:
  - the interfaces the face and voice owners implement, plus checker functions they run on their
    real code;
  - Pydantic models for the setup HTTP routes and the `/live` WebSocket messages.
- A `mock/` FastAPI app implements those routes and messages with fake embedders and in-memory
  storage. The frontend builds against it until David's real backend replaces it.
- Nothing here covers the internals of face recognition, voice recognition, the database or the UI.

**Tech Stack:** Python 3.12, uv, Pydantic v2, FastAPI, pytest, httpx (for FastAPI's TestClient),
python-multipart.

**Spec:** `docs/superpowers/specs/2026-10-24-nametags-design.md`

## Global Constraints

- Everything stays local: no network calls in contract code or the mock. *(Spec: anti-goals.)*
  The real Gemini call lives in the context owner's code, outside the contract and the mock.
- The face and voice owners decide model internals. The contract fixes only: the embedding as a
  list of floats, its `dimensions`, its `metric` (`"l2"` or `"cosine"`), its `cutoff`, and the
  `model` that produced it. *(Spec: "What this design fixes about those two parts.")*
- A cutoff is a distance, and a match must be strictly under it. Cosine distance is 1 − cosine
  similarity, so a similarity threshold *s* becomes the cutoff 1 − *s*. SpeechBrain's default 0.25
  is a similarity, so its cutoff is 0.75.
- The backend composes every spoken sentence, and the frontend speaks the `text` field exactly as
  received, so the wording lives in one place.
- Spoken wording, copied from the spec:
  - Arrival: `That's {name}, your {relationship}.`
  - Unknown: `I don't recognize this person.`
- Box format everywhere: `{x, y, width, height}` in integer pixels of the submitted image, with the
  origin at the top left.
- Audio sent anywhere is WAV, 16 kHz, mono, 16-bit PCM.
- Commits carry no `Co-Authored-By` trailer and no "Generated with" line.

## Review Focus

1. A photo with no faces: `POST /photos` returns 201 with `faces: []`, not an error. *(Test: Task 2.)*
2. An embedder that returns the wrong number of floats: the checker fails loudly, so the mistake is
   caught before it ever reaches the database. *(Test: Task 1.)*
3. Clicking a face that is already labelled and choosing a different person: the label moves to the
   new person, and the face is never counted for both. *(Test: Task 2.)*
4. A voice upload that isn't 16 kHz mono WAV: 422 with a message that says what was expected.
   *(Test: Task 2.)*
5. A `/live` message the server doesn't understand: the server replies with an `error` message and
   keeps the socket open, so the patient's screen doesn't go dead. *(Test: Task 3.)*

---

### Task 1: Embedder interfaces, fakes and checkers

**Files:**
- Create: `pyproject.toml` (uv project `nametags`, packages `contract` and `mock`, dev dependency
  `pytest`)
- Create: `contract/__init__.py`, `contract/embedders.py`, `contract/fakes.py`
- Test: `tests/test_embedders.py`

**Interfaces:**
- Produces, in `contract/embedders.py`:
  - `Box(BaseModel)`: `x: int, y: int, width: int, height: int`
  - `EmbedderSpec(BaseModel)`: `dimensions: int, metric: Literal["l2", "cosine"], cutoff: float,
    model: str`. `model` names the embedder (for example `face_recognition-1.3-small`), so the
    backend can refuse to compare samples from different models.
  - `FaceDetection(BaseModel)`: `box: Box, embedding: list[float]`
  - `class FaceEmbedder(Protocol)`:
    - `spec: EmbedderSpec`
    - `def detect_faces(self, image: bytes) -> list[FaceDetection]`, where `image` is the bytes
      of a JPEG or PNG
  - `class VoiceEmbedder(Protocol)`:
    - `spec: EmbedderSpec`
    - `def embed_voice(self, wav: bytes) -> list[float]`
  - `def check_face_embedder(e: FaceEmbedder, image: bytes) -> None`: raises `AssertionError`
    with a clear message
  - `def check_voice_embedder(e: VoiceEmbedder, wav: bytes) -> None`: raises `AssertionError`
- Produces, in `contract/fakes.py`:
  - `FakeFaceEmbedder`: spec `(128, "l2", 0.6, "fake-face")`. Returns one face per image, with
    the box `Box(x=0, y=0, width=1, height=1)` (it fits any image) and an embedding derived
    deterministically from the image bytes.
  - `FakeVoiceEmbedder`: spec `(192, "cosine", 0.75, "fake-voice")`. It never returns all zeros,
    even for the silent audio `make_wav()` produces.
  - The fake spec values are placeholders. The real values come from the owners.
  - `make_wav(seconds: float = 1.0) -> bytes`: produces silent 16 kHz mono 16-bit audio, as a
    test helper.

- [ ] **Step 1: Write the failing tests**

```python
def test_fake_face_embedder_passes_checker():
    check_face_embedder(FakeFaceEmbedder(), PNG_1x1)

def test_fake_voice_embedder_passes_checker():
    check_voice_embedder(FakeVoiceEmbedder(), make_wav())

def test_checker_rejects_wrong_dimensions():          # Review Focus 2
    class Short(FakeFaceEmbedder):
        def detect_faces(self, image):
            return [FaceDetection(box=Box(x=0, y=0, width=1, height=1), embedding=[0.0] * 127)]
    with pytest.raises(AssertionError, match="128"):
        check_face_embedder(Short(), PNG_1x1)

def test_fake_face_embedding_is_deterministic():
    f = FakeFaceEmbedder()
    assert f.detect_faces(PNG_1x1) == f.detect_faces(PNG_1x1)
```

`PNG_1x1` is a module-level constant holding the bytes of a valid 1×1 PNG.

- [ ] **Step 2: Run `uv run pytest tests/test_embedders.py -v`.** Expected: FAIL with an import
  error.
- [ ] **Step 3: Implement the models, the protocols and the two checker functions in
  `contract/embedders.py`, and the fakes in `contract/fakes.py`.** Each checker asserts that:
  - every embedding has exactly `spec.dimensions` floats, every float is finite, and the
    embedding isn't all zeros;
  - every box has `x, y >= 0` and `width, height > 0`;
  - `0 < cutoff`, and `model` isn't blank.
- [ ] **Step 4: Run `uv run pytest tests/test_embedders.py -v`.** Expected: 4 passed.
- [ ] **Step 5: Commit:** `git add pyproject.toml uv.lock contract tests` then
  `git commit -m "contract: embedder interfaces, fakes and checkers"`

### Task 2: Setup HTTP routes, with a mock server

**Files:**
- Create: `contract/setup_api.py` (request and response models only)
- Create: `mock/__init__.py`, `mock/app.py` (FastAPI app with in-memory state, using the fakes from
  Task 1)
- Modify: `pyproject.toml` (add `fastapi`, `python-multipart`, `uvicorn`, and dev dependency
  `httpx`)
- Test: `tests/test_setup_api.py`

**Interfaces:**
- Consumes: `Box`, `FakeFaceEmbedder`, `FakeVoiceEmbedder` and `make_wav` from Task 1.
- Produces, in `contract/setup_api.py`:
  - `Person`: `id: int, name: str, relationship: str, face_count: int, has_voice: bool,
    small_context: str` (empty string until the first context update)
  - `PersonIn`: `name: str` (1–80 characters), `relationship: str` (1–40 characters)
  - `PersonPatch`: `name: str | None` (1–80 characters when given), `relationship: str | None`
    (1–40 characters when given), `small_context: str | None` (at most 300 characters when given)
  - `NotesIn`: `text: str`
  - `TranscriptLine`: `speaker: str, text: str`
  - `ConversationIn`: `lines: list[TranscriptLine]`
  - `Fact`: `id: int, text: str, source: Literal["conversation", "notes"], created_at: datetime`
  - `DetectedFace`: `face_id: int, box: Box, person_id: int | None`
  - `PhotoOut`: `photo_id: int, width: int, height: int, faces: list[DetectedFace]`
  - `AssignIn`: `person_id: int | None` (null unlabels the face)
  - `VoiceOut`: `voice_sample_id: int`
  - `VoiceSample`: `voice_sample_id: int, created_at: datetime`
- Routes (the mock and David's real backend both serve exactly these):

| Method and path | Body | Returns |
|---|---|---|
| `GET /people` | — | `list[Person]` |
| `POST /people` | `PersonIn` | `201 Person`; 409 if a person with the same name and relationship exists |
| `PATCH /people/{id}` | `PersonPatch` | `Person`; 404; 409 as for POST |
| `DELETE /people/{id}` | — | `204`, or 404 |
| `POST /photos` | multipart `file` (JPEG or PNG) | `201 PhotoOut` |
| `GET /photos` | — | `list[PhotoOut]`, with each face's current label |
| `GET /photos/{id}/image` | — | the stored image; 404 for an unknown photo |
| `POST /faces/{face_id}/assign` | `AssignIn` | `204`; 404 for an unknown face or person; 409 if that person is already labelled on another face in this photo |
| `POST /people/{id}/voice` | multipart `file` (WAV, 16 kHz, mono, 16-bit) | `201 VoiceOut`; 422 for a wrong format; 404 for an unknown person |
| `GET /people/{id}/voice` | — | `list[VoiceSample]`, oldest first; 404 for an unknown person |
| `DELETE /people/{id}/voice/{voice_sample_id}` | — | `204`; 404 if that person has no such recording |
| `POST /people/{id}/notes` | `NotesIn` | `Person` with the updated card; 404 for an unknown person |
| `POST /people/{id}/conversation` | `ConversationIn` | `Person` with the updated card; 404 for an unknown person |
| `GET /people/{id}/facts` | — | `list[Fact]`; 404 for an unknown person |
| `DELETE /people/{id}/facts/{fact_id}` | — | `204`; 404 if that person has no such fact |

  The mock makes no Gemini call. For `notes` and `conversation` it stores the text as one fact and
  sets `small_context` to a fixed placeholder card.

  "The same name and relationship" ignores case and surrounding spaces, so `" david"` and
  `"Grandson"` clash with `"David"` and `"grandson"`. Labels are matched per photo: a person can be
  on at most one face in each photo, and any number of faces can stay unlabelled.

- [ ] **Step 1: Write the failing tests** using `TestClient(mock.app.app)`:

```python
def test_create_and_list_person():
    r = client.post("/people", json={"name": "David", "relationship": "grandson"})
    assert r.status_code == 201
    assert client.get("/people").json() == [
        {"id": r.json()["id"], "name": "David", "relationship": "grandson",
         "face_count": 0, "has_voice": False, "small_context": ""}]

def test_photo_then_assign_counts_face():
    pid = client.post("/people", json={"name": "David", "relationship": "grandson"}).json()["id"]
    photo = client.post("/photos", files={"file": ("p.png", PNG_1x1, "image/png")}).json()
    assert client.post(f"/faces/{photo['faces'][0]['face_id']}/assign",
                       json={"person_id": pid}).status_code == 204
    assert client.get("/people").json()[0]["face_count"] == 1

def test_photo_with_no_faces_is_ok():                 # Review Focus 1
    monkeypatch.setattr(mock.app.face_embedder, "detect_faces", lambda image: [])
    r = client.post("/photos", files={"file": ("p.png", PNG_1x1, "image/png")})
    assert r.status_code == 201 and r.json()["faces"] == []

def test_reassign_moves_face():                       # Review Focus 3
    # Assign face to person A, then to person B.
    # Expect A.face_count == 0 and B.face_count == 1.

def test_voice_rejects_wrong_format():                # Review Focus 4
    r = client.post(f"/people/{pid}/voice", files={"file": ("v.wav", b"not a wav", "audio/wav")})
    assert r.status_code == 422 and "16 kHz" in r.text

def test_voice_accepts_wav_and_sets_has_voice():
    # Upload make_wav(10.0) and expect 201.
    # GET /people then shows has_voice is True.

def test_unknown_person_is_404():
    assert client.patch("/people/999", json={"name": "X"}).status_code == 404

def test_photos_survive_a_reload():
    up = client.post("/photos", files={"file": ("p.png", PNG_1x1, "image/png")}).json()
    assert client.get("/photos").json() == [up]

def test_photo_image_is_served():
    photo_id = client.post("/photos", files={"file": ("p.png", PNG_1x1, "image/png")}).json()["photo_id"]
    assert client.get(f"/photos/{photo_id}/image").content == PNG_1x1

def test_same_name_and_relationship_is_409():
    client.post("/people", json={"name": "David", "relationship": "grandson"})
    r = client.post("/people", json={"name": " david", "relationship": "Grandson"})
    assert r.status_code == 409

def test_unlabelling_a_face():
    # Assign a face to David, then assign the same face to null.
    # Expect 204 both times, and David's face_count back to 0.

def test_one_person_once_per_photo_is_409():
    # Patch the app's face_embedder.detect_faces to return the fake's one face twice:
    #   lambda image: FakeFaceEmbedder().detect_faces(image) * 2
    # Upload one photo, then assign both of its faces to David.
    # Expect 204, then 409.

def test_recordings_can_be_listed_and_one_deleted():
    # Upload make_wav(10.0) twice for David; GET /people/{id}/voice lists two recordings.
    # DELETE the first one: 204. The list then has one recording. Deleting it again: 404.

def test_patch_rejects_an_overlong_name():
    pid = client.post("/people", json={"name": "David", "relationship": "grandson"}).json()["id"]
    assert client.patch(f"/people/{pid}", json={"name": "x" * 81}).status_code == 422
```

  Write out the bodies of the tests that are given only as comments, exactly as the comments
  describe. Create a new `TestClient` for each test, using a fixture that resets the mock's
  in-memory state. The mock exposes its fake embedder as the module attribute
  `mock.app.face_embedder`.
- [ ] **Step 2: Run `uv run pytest tests/test_setup_api.py -v`.** Expected: FAIL with an import
  error.
- [ ] **Step 3: Write the models in `contract/setup_api.py`, then the routes in `mock/app.py`.**
  - Store state in dictionaries keyed by id, and give the app a `reset()` function for the test
    fixture.
  - Check the WAV format with the `wave` module from the standard library.
- [ ] **Step 4: Run `uv run pytest tests/test_setup_api.py -v`.** Expected: 14 passed.
- [ ] **Step 5: Commit:** `git add contract mock tests pyproject.toml uv.lock` then
  `git commit -m "contract: setup routes and mock server"`

### Task 3: `/live` WebSocket messages, added to the mock server

**Files:**
- Create: `contract/live.py`
- Modify: `mock/app.py` (add the `/live` WebSocket)
- Create: `contract/README.md`, a one-page reference for the teammates: the routes table, one JSON
  example of each message, and how to run the mock
- Test: `tests/test_live.py`

**Interfaces:**
- Consumes: `Box` from Task 1, and the mock app from Task 2.
- Produces, in `contract/live.py`, Pydantic models. Each one has a `type: Literal[...]` field, and
  the models are combined as a discriminated union on `type`.
  - **From the client:** `ClientMessage = Frame | Audio | Who`
    - `Frame`: `type="frame"`, `ts: int` (milliseconds since the epoch), `jpeg: str` (base64)
    - `Audio`: `type="audio"`, `ts: int`, `wav: str` (base64; 16 kHz mono WAV)
    - `Who`: `type="who"`
    - The frontend sends no audio while the app is speaking. That is how the mic gets muted, and
      it needs no message of its own.
  - **From the server:** `ServerMessage = Present | Arrived | Unknown | WhoAnswer | Error`
    - `PresentPerson`: `person_id: int, name: str, relationship: str, small_context: str`
    - `TrackedFace`: `box: Box, state: Literal["named", "unsure", "unknown"], person_id: int | None`
    - `Present`: `type="present"`, `people: list[PresentPerson]`, `faces: list[TrackedFace]`. Sent
      after every frame, for the on-screen labels.
    - `Arrived`: `type="arrived"`, `person: PresentPerson`, `via: Literal["face", "voice"]`,
      `text: str`. Example text: `"That's David, your grandson."`
    - `Unknown`: `type="unknown"`, `text: str`, which is always `"I don't recognize this person."`
    - `WhoAnswer`: `type="who_answer"`, `text: str`. The text names everyone present, for example
      `"That's David, your grandson, and Maria, your daughter."`. If nobody is present it says
      `"I don't see anyone I know right now."` *(My call; the spec doesn't give wording for an
      empty room.)*
    - `Error`: `type="error"`, `message: str`
  - `def parse_client(raw: str) -> ClientMessage` raises `pydantic.ValidationError` for invalid
    input.
  - `def who_text(people: list[PresentPerson]) -> str`:
    - each item is `"{name}, your {relationship}"`;
    - items are joined with `", "`, and the last item is preceded by `"and "`, so two people give
      `"A, your x, and B, your y"`;
    - the result starts with `"That's "` and ends with `"."`;
    - an empty list returns the empty-room sentence.
    - The backend should call this function, not rewrite it.
- **What the mock does on `/live`:**
  - For each `frame`, it replies with a `Present` message listing one fake person. On the first
    frame only, it also sends an `Arrived` message.
  - For `who`, it replies with a `WhoAnswer`.
  - For a message it can't understand, it replies with an `Error` message and keeps the socket open.

- [ ] **Step 1: Write the failing tests:**

```python
def test_who_text_two_people():
    assert who_text([P("David", "grandson"), P("Maria", "daughter")]) == \
        "That's David, your grandson, and Maria, your daughter."

def test_who_text_three_people():
    assert who_text([P("A", "son"), P("B", "niece"), P("C", "friend")]) == \
        "That's A, your son, B, your niece, and C, your friend."

def test_who_text_nobody():
    assert who_text([]) == "I don't see anyone I know right now."

def test_parse_client_roundtrip():
    assert parse_client('{"type":"who"}') == Who()

def test_mock_live_first_frame_announces_once():
    with client.websocket_connect("/live") as ws:
        ws.send_text(Frame(ts=1, jpeg=b64(PNG_1x1)).model_dump_json())
        msgs = [ws.receive_json(), ws.receive_json()]
        assert {m["type"] for m in msgs} == {"present", "arrived"}
        ws.send_text(Frame(ts=2, jpeg=b64(PNG_1x1)).model_dump_json())
        assert ws.receive_json()["type"] == "present"

def test_mock_live_bad_message_keeps_socket_open():   # Review Focus 5
    with client.websocket_connect("/live") as ws:
        ws.send_text('{"type":"dance"}')
        assert ws.receive_json()["type"] == "error"
        ws.send_text('{"type":"who"}')
        assert ws.receive_json()["type"] == "who_answer"
```

  In these tests, `P` builds a `PresentPerson` with `person_id=1`.
- [ ] **Step 2: Run `uv run pytest tests/test_live.py -v`.** Expected: FAIL with an import error.
- [ ] **Step 3: Implement `contract/live.py`, add `/live` to `mock/app.py`, and write
  `contract/README.md`.** Generate each JSON example in the README with `model_dump_json()` from
  the models, so the examples always match the code.
- [ ] **Step 4: Run the whole suite with `uv run pytest -v`.** Expected: 24 passed.
- [ ] **Step 5: Run `uv run uvicorn mock.app:app --port 8000`, then
  `curl -s localhost:8000/people`.** Expected: `[]`
- [ ] **Step 6: Commit:** `git add contract mock tests` then
  `git commit -m "contract: live websocket messages, mock and README"`
