# Design: "Who's This?" — face and voice recognition for people with dementia (HackPSU 2026)

## Context

People with dementia often can't recognize family members, and that is distressing for everyone in
the room. The app tells the patient, quietly and in the moment, who they are talking to: *"That's
David, your grandson."* A family member sets it up from a family photo, and the app then recognizes
each person by face and by voice.

This is a 24-hour hackathon build by a team of four (Python plus web). The demo runs on a laptop
using its built-in camera and microphone.

Repo: `/Users/david/Documents/Development/hackathons/HACKPSU-2026-AFK`. It currently contains only
a LICENSE, so everything below is new.

## Scope and features at a glance

```
                         WHO'S THIS?  (HackPSU 2026, 24 h, laptop camera + mic)
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
 └──────────────────────────────────────────────────────────────────────────────────┘
 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │  OUT OF SCOPE (future)                                                           │
 │  learn voices during conversations · personal notes · visit log ·                │
 │  ask "who is this?" out loud · phone / wearable · cloud · accounts               │
 └──────────────────────────────────────────────────────────────────────────────────┘
 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │  NEVER: say a wrong name · repeat or alarm · send photos or voices off the laptop│
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
                                        │ │ closest match under the cutoff │ │
                                        │ └────────────────────────────────┘ │
                                        └────────────────────────────────────┘
   Everything runs on the one demo laptop. The face and voice owners design their own parts;
   the shared contract fixes only what they hand the backend.
```

## Goals

- A family member can enroll people from one family photo: the app finds every face, and they click
  each one to enter a **name** and **relationship**.
- They record about 10 seconds of each enrolled person's voice.
- During a visit, the app recognizes a known person by **face and voice** and announces them
  **out loud**, with the same text shown on screen.
- **It announces each person once when they arrive**, and the patient can ask "who is this?" at any
  time and hear the answer again.

## Non-goals (for this build)

- Learning voices from conversations (named as a future use case).
- Anything beyond name and relationship: no personal notes, no visit log.
- Phones, wearables, cloud hosting, user accounts, and multiple patients.

## Anti-goals (it would count as a failure even if it technically works)

- **Saying the wrong name.** Telling grandma that a stranger is her grandson is worse than saying
  nothing. When the app isn't confident, it treats the person as unknown. *(My call.)*
- Repeating announcements, or using an alarming tone. It speaks once per arrival, calmly.
- Sending family photos or voices off the laptop. Everything stays local. *(My call.)*

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

**Future use cases (not built now):**
- Learning voices on the fly during conversations.
- A short personal note per person.
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
   "Who is this?" button.

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
    - `people`: id, name, relationship, created_at
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
- **Pages:** Setup (people, photo upload, voice recording) and Live (the patient's view).

## Team split (4 people)

The API contract gets agreed in the first hour, then each person works on their own part. The face
and voice owners hand David lists of numbers, and David's database does the matching:

| Person | Owns | Deliverable |
|--------|------|-------------|
| 1 — Face | Face recognition, designed and structured by its owner | For any image: each face's box plus its embedding |
| 2 — Voice | Voice recognition, designed and structured by its owner | For any audio clip: its embedding |
| 3 — David: backend, database, context | The database of people, their face and voice samples, and their context (name and relationship); FastAPI routes and WebSocket; tracking everyone present, the not-sure-yet wait, the once-per-arrival logic | A `/live` socket that sends `arrived` and `unknown` events (name, relationship), plus the current list of people present |
| 4 — Frontend | Setup page (photo, click to label, record voice) and Live page (video, label, speech, button) | The clickable demo |

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

## After approval

Save this design to `docs/superpowers/specs/2026-10-24-whos-this-design.md` in the hackathon repo.
Commit it only once you say so. Then write the implementation plan.
