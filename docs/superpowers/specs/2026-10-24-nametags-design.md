# Design: Nametags — face and voice recognition for people with dementia (HackPSU 2026)

## Context

People with dementia often can't recognize family members, and that is distressing for everyone in
the room. The app tells the patient, quietly and in the moment, who they are talking to: *"That's
David, your grandson."* A family member sets it up from a family photo, and the app then recognizes
each person by face and by voice. It also shows a short note about each person on screen, kept up
to date from their conversations with Gemini (see *Person context with Gemini*).

This is a 24-hour hackathon build by a team of four (Python plus web). The demo runs on a laptop
using its built-in camera and microphone.

Repo: `/Users/david/Documents/Development/hackathons/HACKPSU-2026-AFK`. It currently contains only
a LICENSE, so everything below is new.

## Scope and features at a glance

```
                            NAMETAGS  (HackPSU 2026, 24 h, laptop camera + mic)
 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │  IN SCOPE                                                                        │
 │                                                                                  │
 │  SETUP (family member)                      LIVE (patient)                       │
 │  ┌──────────────────────────────┐           ┌──────────────────────────────────┐ │
 │  │ F1 Photo enrollment          │           │ F3 Live face recognition         │ │
 │  │    upload family photo       │           │ F4 Live voice recognition        │ │
 │  │    → faces boxed             │           │ F5 Combine face + voice          │ │
 │  │    → click face, type        │           │    named / not sure yet / unknown│ │
 │  │      name + relationship     │           │    several people at once        │ │
 │  │    → add more photos         │           │ F6 Announcer (spoken + on screen)│ │
 │  │ F2 Voice enrollment          │           │    "That's David, your grandson."│ │
 │  │    ~10 s recording per person│           │    once per arrival              │ │
 │  │ Edit / remove a person       │           │    "Who is this?" names everyone │ │
 │  └──────────────────────────────┘           │    unknown only after a few sec  │ │
 │                                             │ F7 Live screen: big text, button │ │
 │                                             └──────────────────────────────────┘ │
 │                                                                                  │
 │  CONTEXT (Gemini, text only)                                                     │
 │  F8 After a visit: speaker-labeled transcript → new facts + a short card         │
 │     Family member types notes → same path · card shows when they're recognized   │
 └──────────────────────────────────────────────────────────────────────────────────┘
 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │  OUT OF SCOPE (future)                                                           │
 │  learn voices during conversations · visit log ·                                 │
 │  ask "who is this?" out loud · phone / wearable · cloud · accounts               │
 └──────────────────────────────────────────────────────────────────────────────────┘
 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │  NEVER: say a wrong name · repeat or alarm · send photos or audio off the laptop │
 │         · show deaths, illness or bad news on the context card                   │
 └──────────────────────────────────────────────────────────────────────────────────┘
```

How the parts connect, and who owns each one:

```
   BROWSER  (4 — Frontend)                    BACKEND  (3 — David)
 ┌──────────────────────────┐   HTTP     ┌────────────────────────────────────┐
 │ Setup page               │──────────▶│ setup routes: people, photos,      │
 │  photo, click to label,  │           │ label a face, voice upload         │
 │  record voice            │           │                                    │
 │                          │ WebSocket │ /live: tracks everyone present,    │
 │ Live page                │◀────────▶│ not-sure-yet wait, once per arrival│
 │  camera + mic → frames,  │  frames,  │ writes every spoken sentence       │
 │  audio chunks            │  audio ▶  │                                    │
 │  speaks `text` verbatim  │ ◀ events  │      │ image            │ audio      │
 │  "Who is this?" button   │           │      ▼                  ▼            │
 └──────────────────────────┘           │ ┌──────────────┐ ┌──────────────┐  │
                                        │ │ 1 — Face     │ │ 2 — Voice    │  │
                                        │ │ (face_rec.)  │ │ (SpeechBrain)│  │
                                        │ │ → box +      │ │ → embedding  │  │
                                        │ │   embedding  │ │              │  │
                                        │ └──────┬───────┘ └──────┬───────┘  │
                                        │        ▼ embeddings     ▼          │
                                        │ ┌────────────────────────────────┐ │
                                        │ │ Postgres + pgvector            │ │
                                        │ │ people · photos ·              │ │
                                        │ │ face_samples · voice_samples   │ │
                                        │ │ facts · small_context          │ │
                                        │ │ closest match under the cutoff │ │
                                        │ └────────────────────────────────┘ │
                                        └────────────────────────────────────┘
   Everything runs on the one demo laptop. The face and voice owners design their own parts;
   the shared contract fixes only what they hand the backend.
   The one exception is Gemini: after a visit the backend sends it text (never images or audio)
   and stores what comes back. Nothing on the live recognition path calls it.
```

## Goals

- A family member can enroll people from one family photo: the app finds every face, and they click
  each one to enter a **name** and **relationship**.
- They record about 10 seconds of each enrolled person's voice.
- During a visit, the app recognizes a known person by **face and voice** and announces them
  **out loud**, with the same text shown on screen.
- **It announces each person once when they arrive**, and the patient can ask "who is this?" at any
  time and hear the answer again.
- When a known person is recognized, the screen also shows a **short context card** about them,
  for example *"David is your grandson. He just moved to Pittsburgh and works as a nurse."*
- Gemini keeps that card up to date from each conversation and from notes a family member types.

## Non-goals (for this build)

- Learning voices from conversations (named as a future use case).
- A visit log or a full history view. *(Amended: short per-person context is now in scope. See
  Person context with Gemini.)*
- Phones, wearables, cloud hosting, user accounts, and multiple patients.

## Anti-goals (it would count as a failure even if it technically works)

- **Saying the wrong name.** Telling grandma that a stranger is her grandson is worse than saying
  nothing. When the app isn't confident, it treats the person as unknown. *(My call.)*
- Repeating announcements, or using an alarming tone. It speaks once per arrival, calmly.
- Sending family photos or audio off the laptop. Images and audio stay local. *(My call.)*
  *(Amended: text may leave the laptop. Speaker-labeled transcripts and typed notes go to Gemini,
  and nothing else does.)*
- **Showing upsetting facts on the context card.** Deaths, illness, diagnoses and bad news never
  appear on it, even if they came up in conversation.

## Use cases

| # | Actor | Use case | Outcome |
|---|-------|----------|---------|
| UC1 | Family member | Upload a family photo and label the faces | Each face gets a name and relationship; their face data is saved |
| UC2 | Family member | Record a person's voice | 10 s of audio becomes that person's voice profile |
| UC3 | Family member | Edit or remove a person | The list of people stays correct |
| UC4 | Patient | A known person walks in and talks | It speaks once: "That's David, your grandson." |
| UC5 | Patient | A known person talks while off camera | Their voice alone identifies them, then the same announcement plays |
| UC6 | Patient | Asks "who is this?" (button or spacebar) | It repeats who is currently in front of them |
| UC7 | Patient | An unknown person appears | The app stays silent while unsure. Once the face has been clearly visible and unmatched for several seconds, it says gently: "I don't recognize this person." |
| UC8 | Family member | Add more photos of an enrolled person | The extra face samples make recognition more reliable |
| UC9 | Patient | Several known people are present | Each is announced on arrival. "Who is this?" names everyone present: "That's David, your grandson, and Maria, your daughter." |
| UC10 | Patient | A known person is recognized | Their short context card shows on screen next to their name |
| UC11 | Patient | A visit ends | Gemini reads the speaker-labeled transcript, adds any new facts about that person, and updates their card |
| UC12 | Family member | Types notes about a person | Gemini turns the notes into facts and updates the card |
| UC13 | Family member | Opens a person's page | They can read every stored fact, and fix the card by hand if it is wrong |

**Future use cases (not built now):**
- Learning voices on the fly during conversations.
- A visit log ("David visited last Sunday").
- Asking "who is this?" out loud instead of pressing a button.
- Running on a phone or wearable.

## Core features

1. **Photo enrollment.** Upload a photo, the app detects the faces and draws a box around each one,
   and the family member clicks a box to enter a name and relationship. That face's
   "fingerprint" (embedding) is saved for the person. The family member can also upload more photos
   of the same person. Each person keeps several face samples, and matching uses the best one.
2. **Voice enrollment.** A "Record voice" button captures about 10 s from the mic and saves a voice
   fingerprint for the person.
3. **Live face recognition.** The camera sends a few frames per second, and each one is matched
   against the enrolled faces using a confidence threshold.
4. **Live speaker recognition.** The mic sends audio in chunks of a few seconds, and each chunk is
   matched against the enrolled voices using a confidence threshold.
5. **Combining face and voice.** The backend keeps track of everyone currently present, not just
   one person.
   - A confident face match adds that person.
   - A confident voice match also adds that person, even if a different person is on camera.
     That counts as two people, not as face and voice disagreeing.
   - Each face is in one of three states: *named*, *not sure yet* (silent), or *unknown*. It
     becomes unknown only after it has been clearly visible and unmatched for several seconds.
   - Voice can only name people; it never triggers "unknown". So the patient's voice, and the
     operator's, are ignored. *(My call.)*
   - The builder tunes the exact rules.
6. **Announcer.** Announces each person once when they arrive, and waits a few minutes before
   announcing the same person again. "Who is this?" names everyone present. It uses an on-device
   browser voice, so names never go to a cloud service, and it mutes the mic while speaking so the
   app doesn't hear itself.
7. **Live screen.** Large, high-contrast text: the camera feed with a name label, plus a big
   "Who is this?" button. A recognized person's short context card shows beside their name.
8. **Person context.** Each person has a large context (every fact stored about them) and a small
   context (the short card). Gemini adds facts after each visit and from typed notes, then
   rewrites the card. Details are in *Person context with Gemini*.

## How it gets made (my calls, all changeable)

- **Backend:** Python with FastAPI, running locally.
- **Face recognition:** built on `face_recognition` (github.com/ageitgey/face_recognition). Its
  design and structure belong to the face owner.
- **Voice recognition:** built on SpeechBrain. Its design and structure belong to the voice owner.
- **What this design fixes about those two parts:** each one hands the backend a list of numbers
  (an embedding) for each face or voice clip, and tells it how many numbers there are, which
  distance measure to use, and what cutoff counts as a match. Everything else is up to the owner.
- **Frontend:** a plain web page or a small React app.
  - The browser captures the camera and mic (`getUserMedia`) and streams frames and audio chunks
    to the backend over a WebSocket.
  - The browser speaks using `speechSynthesis`.
- **Database (team's choice): Postgres with pgvector**, owned by David.
  - It runs from the `pgvector/pgvector` Docker image through a `docker-compose.yml` in the repo,
    so all four laptops get the same database with one command. *(My call; the alternative is
    installing Postgres and pgvector with brew.)*
  - Python talks to it with `psycopg` 3 and the `pgvector` package.
  - Tables:
    - `people`: id, name, relationship, created_at, `small_context` (the short card; empty until
      the first update)
    - `facts`: id, person_id, text, source (`conversation` or `notes`), created_at. This is the
      large context. Rows are only ever added, never rewritten.
    - `photos`: id, file path, uploaded_at
    - `face_samples`: id, person_id, photo_id, the face's box in the photo, and an `embedding`
      vector sized to whatever the face owner's model produces
    - `voice_samples`: id, person_id, audio file path, and an `embedding` vector sized to whatever
      the voice owner's model produces
  - The image and audio files live in a local `data/` folder; the database stores their paths.
  - **Matching is a query:** find the closest stored sample using the distance measure the owner
    names.
  - A result counts only if its distance is under the owner's cutoff. Anything else is treated as
    *not sure yet*.
  - No index: an exact scan over a few hundred rows is instant.
- **Pages:** Setup (people, photo upload, voice recording, notes and facts per person) and Live
  (the patient's view).

## Person context with Gemini

*Amendment, 2026-10-24, agreed by the team.* Each person gets a short card on screen that stays
up to date from their conversations.

### Two contexts per person

- **Large context:** every fact we know about the person, stored as rows in the `facts` table.
  Gemini only ever adds rows. It never rewrites old ones, so nothing is lost by summarizing a
  summary, and one bad fact can be deleted without touching the rest.
- **Small context:** the short card, stored in `people.small_context`. It is at most two short
  sentences in plain words, sized to be read at a glance. It is rewritten from the facts each time
  they change.

### Two inputs, one path

1. **After a visit.** The visit ends when someone presses "End visit" (or after a timeout the
   builder picks). The backend sends the **speaker-labeled transcript of the whole conversation**,
   for example `Patient: Did you move?` / `David: Yeah, last month.` Keeping both sides means
   answers stay attached to their questions. If several known people were in the visit, the same
   transcript is sent once for each of them.
2. **Typed notes.** A family member types notes about a person on the Setup page.

Both make the same Gemini call.

### The Gemini call

One request per visit (per person present), or per note. Not one per sentence.

- **Input:** the person's name and relationship, their existing facts, and the new transcript or
  notes.
- **Output:** JSON, enforced with Gemini's structured output (`response_mime_type:
  "application/json"` plus `response_json_schema`):

  ```json
  {
    "new_facts": ["Moved to Pittsburgh last month", "Works as a nurse"],
    "small_context": "David is your grandson. He just moved to Pittsburgh and works as a nurse."
  }
  ```

- The backend adds `new_facts` to the `facts` table and overwrites `small_context`.
- **Model:** a Gemini Flash model. This is extraction and short summarizing, so a fast, cheap
  model is enough. Check the current model list when wiring it up.

**Rules the prompt must state:**
- Only add facts about this person and their life, not about the patient.
- Skip facts already in the existing list. Conversations with someone with dementia repeat a lot,
  and without this rule the same fact gets added again every visit.
- When a new fact replaces an old one (moved, changed jobs), the card uses the newer one.
- Never put deaths, illness, diagnoses or bad news on the card.
- Keep the card to two short sentences.

### Rules for the rest of the system

- **Gemini is never called at recognition time.** The Live page shows `small_context` straight
  from the database, so the card appears instantly and still works if the wifi drops.
- **Gemini never writes the spoken announcement.** That stays `That's {name}, your
  {relationship}.`, composed by the backend.
- **If the call fails or returns bad JSON,** keep the old card, add no facts, and log it.
- **Only text leaves the laptop.** Photos and audio never do.
- **The API key lives in a gitignored `.env`** as `GEMINI_API_KEY`. The repo is public.
- **A wrong card gets fixed by a person.** A family member can edit `small_context` directly, or
  add a note that corrects it.

### Contract additions

- `Person` gains `small_context: str` (empty string until the first update).
- `PresentPerson` (in `/live` messages) gains `small_context: str`, so the Live page can show the
  card without another request.
- `PersonPatch` gains `small_context: str | None`, for fixing the card by hand. A card fixed by
  hand is also stored as a `notes` fact, so the next Gemini rewrite starts from the family's
  correction. *(Amended 2026-10-24 by David.)*
- New routes:

| Method and path | Body | Returns |
|---|---|---|
| `POST /people/{id}/notes` | `{text}` | `Person` with the updated card; 404 for an unknown person |
| `POST /people/{id}/conversation` | `{lines: [{speaker, text}]}` | `Person` with the updated card; 404 for an unknown person |
| `GET /people/{id}/facts` | — | `list[Fact]` (`id, text, source, created_at`); 404 for an unknown person |
| `DELETE /people/{id}/facts/{fact_id}` | — | `204`; 404 if that person has no such fact. The card isn't rewritten automatically. *(Amended 2026-10-24 by David.)* |

The mock server makes no network calls. For `notes` and `conversation` it stores the text as one
fact and sets a fixed placeholder card.

*Amended 2026-10-24 by David, from the database plan
(`docs/superpowers/plans/2026-10-24-database.md`).* The contract plan also gains:
- `GET /photos` and `GET /photos/{id}/image`, so the setup page can show saved photos after a
  reload;
- `GET /people/{id}/voice` and `DELETE /people/{id}/voice/{voice_sample_id}`, to remove one bad
  recording;
- `AssignIn.person_id: int | None`, so a wrong face label can be undone;
- 409 for a second person with the same name and relationship, and for labelling one person on
  two faces of the same photo;
- `EmbedderSpec.model`, so samples from different models are never compared;
- length limits on `PersonPatch`.

## Team split

The API contract gets agreed in the first hour, then each person works on their own part. The face
and voice owners hand David lists of numbers, and David's database does the matching:

| Person | Owns | Deliverable |
|--------|------|-------------|
| 1 — Face | Face recognition, designed and structured by its owner | For any image: each face's box plus its embedding |
| 2 — Voice | Voice recognition, designed and structured by its owner | For any audio clip: its embedding |
| 3 — David: backend, database, context | The database of people, their face and voice samples, and their context (name and relationship); FastAPI routes and WebSocket; tracking everyone present, the not-sure-yet wait, the once-per-arrival logic | A `/live` socket that sends `arrived` and `unknown` events (name, relationship), plus the current list of people present |
| 4 — Frontend | Setup page (photo, click to label, record voice) and Live page (video, label, speech, button) | The clickable demo |
| Context (Gemini) | The Gemini call, its prompt and JSON schema, and the `notes`, `conversation` and `facts` routes. The `facts` table and `small_context` column are added to David's database. | Facts and an updated card for any transcript or note |

**Rough timeline:**
- **Hours 0–1:** contract and repo skeleton.
- **By hour 8:** each part works on its own.
- **By hour 14:** everything integrated, end to end.
- **Hours 14–20:** tune thresholds and polish the UI.
- **Hours 20–24:** rehearse the demo.

## Left to the builder

- Exact thresholds, frame rate, audio chunk length, and how long to wait before announcing someone
  again.
- Visual design, as long as the text is large and high contrast.
- Folder layout and test approach.

## Verification (demo script)

1. Enroll from one family photo containing 3–4 teammates, and record each teammate's voice.
2. A teammate walks into the camera frame and it announces "That's X, your Y" exactly once.
3. They keep talking and it stays quiet. Press "Who is this?" and it repeats the line.
4. A teammate talks while off camera, and they are identified by voice.
5. A person who was never enrolled stays in view. After a few seconds it says "I don't recognize
   this person." It never gives a wrong name, and it never says "unknown" about an enrolled person
   who is walking in.
6. Two enrolled teammates are in frame, and each is announced once. "Who is this?" names both.
7. Grandma (the operator) talks, and the app says nothing about her voice.
8. Run the face and voice matching on their own against saved sample images and audio clips, so
   the thresholds can be tuned before the event.
9. Type a note for a teammate. Their card updates, and the next time they walk in, it shows beside
   their name.
10. A teammate chats with "grandma" and mentions something new, then someone presses "End visit."
    The new fact appears in their facts list and the card reflects it.
11. Repeat the same fact in a second visit. It is not added a second time.
12. Mention something sad in a conversation (staged). It never appears on the card.
13. Turn off the wifi. Recognition still shows each person's existing card.

## After approval

Save this design to `docs/superpowers/specs/2026-10-24-nametags-design.md` in the hackathon repo.
Commit it only once you say so. Then write the implementation plan.
