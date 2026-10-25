# Nametags

A memory aid that tells a person living with dementia who they're talking to.

[Evidence summary](docs/research/README.md) · [Study pipeline](docs/research/pipeline.md)

## About

Dementia can take away the ability to recognize loved ones: WHO notes that people with dementia "may not be able to
recognize family members or friends". Nametags helps in those moments. It recognizes the people a family has enrolled,
by voice and by face, and quietly says who they are: *That's David, your grandson.* When it isn't sure, it says nothing
rather than risk a wrong name. Nova, a voice assistant, answers questions such as "Nova, who's here?" from what the
family has recorded. Nametags is designed for glasses; today it runs as a web app and as a desktop program on a laptop.

It fits mild Alzheimer's best, where people still know their family but can't find the name. It isn't a treatment: it's
a non-drug support alongside medical care, not instead of it. It hasn't yet been tested with people living with
dementia.

The need is large. An estimated [7.4 million](docs/research/problem-size.md) Americans 65 and older live with
Alzheimer's dementia in 2026, [12.7 million](docs/research/problem-size.md) family and other unpaid caregivers gave 19.6
billion hours of care in 2025, and [between 39% and 49%](docs/research/problem-size.md) of US nursing-home residents
have a dementia diagnosis (our own count of CMS data for Q3 2026). The [evidence summary](docs/research/README.md)
explains why Nametags works the way it does.

### Built with

- **API:** Python 3.12, FastAPI and Uvicorn, managed with uv
- **Database:** PostgreSQL 17 with pgvector, through psycopg 3
- **Faces:** `facerec`, in this repo, on face_recognition 1.3 (dlib's ResNet encoder) and OpenCV
- **Voices:** `voice_rec`, in this repo: TitaNet-small speaker embeddings, Silero voice activity detection and Moonshine
  speech-to-text, all running locally through sherpa-onnx, plus the Supertonic voice for the desktop program
- **Captions:** Moonshine, on the machine, by default; in the web app's live view, Speechmatics real-time (through
  `speechmatics-rt`) when `SPEECHMATICS_API_KEY` is set
- **Nova:** Claude (`claude-opus-5-5`) through the Anthropic SDK, with three tools: two that read Postgres and one that
  reports who is in the room
- **Facts and cards:** Gemini (`gemini-3.8-flash` by default) through the Google Gen AI SDK
- **Web app:** React 19, React Router 7, TypeScript 5.9 and Vite 8; it speaks only with the browser's on-device voice
- **Deployment:** Docker Compose, with the API and Postgres in two containers

## Getting started

### Prerequisites

- Docker Engine with the compose plugin, for the API, the web app and Postgres
- Node.js and npm, only to work on the web app's pages
- A webcam and a microphone. Browsers allow them only on localhost or over HTTPS, so open the pages on the machine that
  serves them; [frontend/README.md](frontend/README.md) covers phones.
- For enrollment, the desktop program, or the API without Docker: uv and Python 3.12, plus a C++ compiler and CMake,
  because dlib builds from source. On macOS:

  ```sh
  xcode-select --install
  brew install cmake
  ```

- Optional: a Google Gemini API key, an Anthropic API key and a Speechmatics API key (see step 2)

### Installation

1. Clone this repository, and open a terminal in its folder.
2. Create the settings file:

   ```sh
   cp .env.example .env
   ```

   Then edit `.env`. All three keys are optional:

   - Paste a Google Gemini API key after `GEMINI_API_KEY=`. It turns typed notes and visit transcripts into facts and a
     short card for each person. Without it, `python -m enroll` and the wearer's setup save notes as typed, but notes
     from the visitor sign-up aren't saved, and visits aren't summarized.
   - Paste an Anthropic API key after `ANTHROPIC_API_KEY=`. It runs Nova. Without it, Nametags still recognizes,
     captions and summarizes.
   - Paste a Speechmatics API key after `SPEECHMATICS_API_KEY=` for live captions word by word. While it is set, the
     audio from the web app's live view is streamed to Speechmatics. Left empty, captions stay on this machine, one
     finished sentence at a time; `NAMETAGS_CAPTIONS=local` keeps them there even with a key.

   Leave the network settings as they are. They keep the API reachable from this machine only, because it has no login;
   [DEPLOY.md](DEPLOY.md) explains how to open it up.
3. Build and start the API and Postgres:

   ```sh
   docker compose up -d --build
   docker compose ps
   curl -s localhost:8000/health
   ```

   The first build compiles dlib, builds the web app and downloads the speech models, which takes 10 to 15 minutes.
   `docker compose ps` should list both services as healthy, and the health check returns JSON that starts with
   `{"status":"ok"`. Then open the web app at <http://localhost:8000/>: the API serves it, built into the image. The
   API's interactive docs are at <http://localhost:8000/docs>.
4. Optional, to work on the pages: start Vite's dev server, from a second terminal in the repo folder:

   ```sh
   cd frontend
   npm install
   npm run dev
   ```

   Open <http://localhost:5173>. Vite forwards `/api` to the API at <http://127.0.0.1:8000>. To change that address, the
   name the visitor screens use until a wearer is registered, or the contact email on the Consent screen, copy
   `frontend/.env.example` to `frontend/.env.local` and edit it. Set the contact email before real visitors sign up:
   left empty, the Consent screen shows a placeholder. The Docker image is built without `frontend/.env.local`, so
   these settings don't reach the app at port 8000, and its Consent screen shows the placeholder.
   [frontend/README.md](frontend/README.md) also covers a mock API, sample data and the live view's display settings.
5. For enrollment and the desktop program, install the Python packages and download the voice models once:

   ```sh
   uv sync
   ```

   `uv sync` compiles dlib. Then run the `download_models.sh` script in the voice package's `scripts/` folder once; it
   works from any folder, and [live/README.md](live/README.md#keys-and-setup) shows the full command. The script
   downloads the speaker, voice-activity, speech-to-text and speaking-voice models.

For a public server with HTTPS, backups, and running the API without Docker, see [DEPLOY.md](DEPLOY.md).

## Usage

### The web app

Open <http://localhost:8000/>, or <http://localhost:5173> with the dev server. The home page links to four screens:

- **Visitor sign-up, `/visitor`.** A visitor steps through Intro, Consent, Face photos, Voice, About you and Thank you.
  Upload, on About you, registers their name and relationship, their photos, a voice sample and a few notes.
- **The wearer's setup, `/setup`.** Name, Context, Voice and All set. Upload, on Voice, registers the wearer on the
  API: their name, a voice sample, and the context as notes that become their facts and card. A copy of the name and
  context stays in that browser. The command line is another way to register the wearer (below).
- **The live view, `/live`.** The display for the glasses. Click **Start live view** and allow the camera and
  microphone. Enrolled people get a name tag and an info panel, and captions show who said what. It speaks only when
  asked: press **Who is this?**, or the Space key, to hear who is in view, or ask Nova (below). Names are spoken only
  with an on-device voice; without one, they show in the caption bar.
- **Manage, `/manage`.** Every person with their card, facts, photos and voice recordings, plus faces still to label.

### Enrollment and the desktop program

Both run on the laptop and use its camera and microphone; macOS asks for permission for the terminal the first time.
Start Postgres, register the wearer (unless `/setup` already did), then the people in their life:

```sh
docker compose up -d --wait db
uv run python -m enroll --user "Rose"
uv run python -m enroll "David" son
```

Each run walks through five head poses in a camera window (none for the wearer, since the glasses never see them),
records 10 seconds of speech in a second window, then asks for a few facts in the terminal. `--no-window` does it all in
the terminal, and `uv run python -m enroll --list` shows who is registered.

Then start the desktop program:

```sh
uv run python -m live
```

It names the people it sees and hears, announces each arrival once, and keeps the visit's transcript. When the visit
ends, Gemini turns the lines of recognized voices (never a stranger's) into each visitor's facts and card. In its
window, `q` quits, `e` ends the visit, and `w` asks who is here. `--no-camera` uses the microphone only, `--no-tts`
prints instead of speaking, `--no-nova` and `--no-summary` turn off Nova and the visit summary, and `--help` lists the
rest. More in [enroll/README.md](enroll/README.md) and [live/README.md](live/README.md).

### Nova

Nova answers questions about the people in the wearer's life, using only what's in the database. Her wake word is her
name: say "Nova, who is David?" or "Hey Nova, who's here?". She needs `ANTHROPIC_API_KEY`. The desktop program and the
web app's live view speak her answers.

## Research

Nametags rests on a small data study; start with the [evidence summary](docs/research/README.md). The study combines
published figures, care workers' accounts from published studies and care organizations, a Spark analysis of 5,804
Europe PMC abstracts and 133,920 rows of CMS nursing-home data, 20 papers read in depth, and points a care-home worker
made, recalled by a team member.

- [Pipeline](docs/research/pipeline.md): how the data was collected, stored, processed, analyzed and delivered. The
  eight Spark jobs are written as map, shuffle and reduce; no Hadoop MapReduce job ran.
- [How big the problem is](docs/research/problem-size.md)
- [Care-worker accounts](docs/research/care-worker-accounts.md)
- [Research at scale](docs/research/research-at-scale.md)
- [Interview themes](docs/research/interview-themes.md): points a care-home worker made, recalled by a team member
- [Suggested changes](docs/research/suggested-changes.md), ranked by the evidence
- [References](docs/research/references.md)

The code that reproduces the analysis is in [research/](research/).

## Roadmap

From the [suggested changes](docs/research/suggested-changes.md), most urgent first:

- [ ] Introduce rather than correct: *Here's David, your grandson.* instead of *That's David, your grandson.*
- [ ] Make Nova graceful: when a name isn't registered, she says so and says who is here. She introduces herself once
  per visit and never claims to be a person.
- [ ] Privacy by design: send Gemini only the lines of consented, enrolled voices; add a pause mode for bedrooms and
  bathrooms; make local-only the default in care homes.
- [ ] Cue first, then the name: give the wearer a moment to recall who it is before the glasses show or say it. Opt-in,
  in the live view first.
- [ ] Smaller follow-ups: per-person announcement settings, enrolling care staff through `/visitor`, a nudge to refresh
  photos and voice, and measuring how long it takes to name someone.

## License

MIT; see [LICENSE](LICENSE). The quotes in `docs/research/` belong to their sources; they're short and attributed.

## Acknowledgments

The research uses data from:

- Europe PMC, for the literature
- the CMS Minimum Data Set, for nursing-home residents by state
- the Alzheimer's Association's *2026 Alzheimer's Disease Facts and Figures*, for the US figures
- the World Health Organization's dementia fact sheet, for the global figures

Full citations are in the [references](docs/research/references.md).
