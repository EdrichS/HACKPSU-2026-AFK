# Nametags: the project story

A memory aid for people living with dementia. It recognizes enrolled family and friends by face and voice and tells the wearer who they are. 

## How we built it

**The stack and how it connects**

- **Frontend (React, TypeScript, Vite):** four pages served by the API.
  - `/visitor`: consent, 5 face photos, a voice reading, notes.
  - `/setup`: the wearer's name, notes and voice.
  - `/live`: the glasses HUD with name tags, a card for each person, captions and Nova.
  - `/manage`: edit people, cards, facts, photos and recordings.
- **Browser → API:** the `/live` WebSocket streams camera frames and 16 kHz audio to the backend; sign up uploads go
  over HTTP.
- **Backend (Python, FastAPI, Pydantic):** receives frames and audio and runs recognition.
  - Faces: face_recognition and dlib turn each face into 128 numbers.
  - Voices: Silero VAD finds speech, then TitaNet-small (run through sherpa-onnx) turns it into 192 numbers.
- **Database (PostgreSQL with pgvector):** stores people and their face and voice embeddings.
  - One SQL query finds the nearest two people.
  - A name is given only when the match is under the cutoff and clearly ahead of the runner up.
- **Presence tracker:** a face needs two sightings within 3 seconds, a voice counts at once, and each arrival is
  announced once ("Here's David, your grandson.").
- **Captions:** Moonshine on the machine by default, or Speechmatics streaming if a key is set. Speaker labels are
  matched against voice samples in Postgres.
- **Context (Claude):** notes and visit transcripts go in; strangers' lines are left out.
  - One call writes neutral facts.
  - A second call writes a short card for the HUD, with no bad news.
  - Both are saved in Postgres.
- **Nova (Claude with tools):** a voice assistant.
  - Three tools (`list_people`, `person_context`, `who_is_here`) read only from Postgres.
  - She answers "who's here?" and never claims to be a person.
- **Deployment (Docker Compose):** a Postgres and pgvector container plus an API container that serves the built
  frontend
- **Privacy line:** photos and audio are recognized on the machine. Only text goes to Claude, and audio goes to
  Speechmatics only if you add its key.
- **Research (PySpark):**
  - 5,804 Europe PMC abstracts and 133,920 rows of CMS nursing home data.
  - 20 papers read in depth.
  - The result was a ranked list of changes; four are built.

## Challenges we faced

- **Voices in a real room:** synthetic voices matched at 0.92 to 0.98 similarity, but real people on a laptop mic
  matched far lower. We loosened the live cutoff, judged speakers on their recent attempts only, and lengthened sign up
  recordings to 15 seconds.
- **Overlapping speech:** Speechmatics gives one speaker per word, so two people talking at once merge.
- **Strangers' voices:** they were first captioned as the wearer. Now they're "Someone" and kept out of summaries.
- **Camera and mic:** browsers allow them only over HTTPS or on localhost. We also wrote our own resampling filter to
  keep hiss out of the voice band.
- **Testing limits:** no users living with dementia, no real glasses, no CI. The care home interview recording came
  back silent.

## Acknowledgements

- HackPSU 2026 organizers.
- **Recognition:** face_recognition, dlib, OpenCV, NumPy, Pillow, NVIDIA TitaNet-small, sherpa-onnx, Silero VAD,
  Moonshine, SpeechBrain, Supertonic.
- **AI and speech:** Anthropic Claude, Speechmatics, Google Gemini.
- **App:** PostgreSQL, pgvector, FastAPI, Pydantic, uvicorn, uv, pytest, Docker, React, Vite, TypeScript.
- **Research:**
  - Data and tools: Europe PMC, PubMed Central, Crossref, CMS Minimum Data Set, PySpark, matplotlib.
  - Guidance and figures: Alzheimer's Association, WHO, Dementia UK.
  - McCarron et al. 2019, the closest prior art.
- The care home worker who shared how staff introduce people.

## What we learned

- Agree on the interface and ship a mock first, parallel work depends on it.
- Tune recognition in the room you'll demo in, not on clean recordings.
- Log match distances and timings, so tuning uses numbers instead of guesses.
- Keep the factual record separate from what the wearer sees.

## What's next

- A pause mode for private rooms, and keeping everything on the machine in care homes.
- Cue first, then the name: "Your grandson is here", then the name a moment later.
- Settings for each person: announce on arrival, only when asked, or never.
- Faster naming, using the timing logs.
- Consent stored on the server; a login and HTTPS.
- Name two people talking at once; one voice cutoff everywhere.
- Test with people living with dementia, their carers, and real glasses.
