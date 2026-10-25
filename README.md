# Nametags

A memory aid that tells a person living with dementia who they're talking to.

Read the [evidence summary](docs/research/README.md) and [how the study was done](docs/research/pipeline.md).

## About

Dementia can take away the ability to recognize loved ones: WHO notes that people with dementia "may not be able to
recognize family members or friends". Nametags recognizes the people a family has enrolled, by voice and by face, and
tells the wearer who they are. When it isn't sure, it says nothing rather than risk a wrong name. It is designed for
glasses; today it runs as a web app and as a desktop program on a laptop.

It fits mild Alzheimer's best, where people still know their family but can't find the name. It helps alongside
medical care and isn't a treatment, and it hasn't yet been tested with people living with dementia. The need is large:
an estimated [7.4 million](docs/research/problem-size.md) Americans 65 and older live with Alzheimer's dementia in
2026, and [between 39% and 49%](docs/research/problem-size.md) of residents in US nursing homes have a dementia
diagnosis.

## What it does

- **Names people for the wearer.** The live view for the glasses puts a name tag on each face it knows, shows a short
  card on what to talk about, and captions who said what. It speaks only when asked: Space says who is in view.
- **Nova, a voice assistant.** Ask "Nova, who's here?" or about anyone in the wearer's life. She answers only from what
  the family recorded, and never claims to be a person.
- **Remembers each visit.** Notes and visit conversations become facts and a short card for each person. A stranger's
  words are left out.
- **Visitors sign themselves up**, with consent: a few photos, a voice reading and some notes.
- **Recognition stays on the machine.** Faces and voices are recognized locally. Only text leaves it, for Nova and the
  cards, and the live view's audio goes to Speechmatics only if you add its key. The API answers this machine only; it
  has no login.

| Page | What it's for |
|---|---|
| `/visitor` | A visitor signs up: consent, face photos, a voice reading, notes. Share `/visitor?for=Rose`. |
| `/setup` | The wearer's name, notes and voice |
| `/live` | The glasses view: name tags, cards, captions and Nova |
| `/manage` | Each person's details, card, facts, photos and voice recordings, and faces still to label |

**Built with** Python 3.12 (FastAPI, uv), PostgreSQL 17 with pgvector, React 19 with Vite, and Docker Compose. Faces:
face_recognition (dlib). Voices: TitaNet-small, Silero and Moonshine through sherpa-onnx, all local. Claude
(`claude-opus-5-5`) runs Nova and writes the cards; Speechmatics is optional, for captions that appear word by word.

## Getting started

You need Docker with the compose plugin, a webcam and a microphone. Browsers allow the camera and microphone only on
localhost or over HTTPS; [frontend/README.md](frontend/README.md) covers phones.

```sh
cp .env.example .env
docker compose up -d --build
```

The first build compiles dlib, builds the web app and downloads the speech models, in 10 to 15 minutes. Then open
<http://localhost:8000/>; the API's docs are at <http://localhost:8000/docs>. Both keys in `.env` are optional:

- `ANTHROPIC_API_KEY` runs Nova and writes the facts and cards. Without it, notes are stored as typed and visits
  aren't summarized.
- `SPEECHMATICS_API_KEY` makes captions appear word by word, by streaming the live view's audio to Speechmatics.
  Without it, captions stay on the machine.

Before real visitors sign up, give the Consent screen a contact email: copy `frontend/.env.example` to
`frontend/.env.local` and use the dev server (below). The Docker image doesn't read that file, so its Consent screen
shows a placeholder.

## The laptop programs

`python -m enroll` registers people from the terminal, and `python -m live` runs recognition with a camera window. They
need uv, Python 3.12, a C++ compiler and CMake, since dlib builds from source (on macOS, `xcode-select --install` and
`brew install cmake`).

```sh
uv sync
hackpsu_voice_rec/scripts/download_models.sh
docker compose up -d --wait db
uv run python -m enroll --user "Rose"   # the wearer: voice and notes
uv run python -m enroll "David" son     # five head poses, 10 s of speech, notes
uv run python -m live                   # q quits, e ends the visit, w asks who is here
```

`python -m live` announces each arrival once (*Here's David, your grandson.*) and summarizes the visit when it ends.
More in [enroll/README.md](enroll/README.md) and [live/README.md](live/README.md).

## Development

To work on the pages, run Vite's dev server; it forwards `/api` to the API on port 8000:

```sh
cd frontend && npm install && npm run dev
```

Open <http://localhost:5173>. [frontend/README.md](frontend/README.md) covers a mock API, sample data and the live
view's display settings, and [DEPLOY.md](DEPLOY.md) covers a public server with HTTPS, backups and running without
Docker. The tests run with `uv run pytest` while the database container is up.

## Research

Nametags is based on a study of the evidence: published figures, care workers' accounts, a Spark analysis of 5,804
Europe PMC abstracts and 133,920 rows of CMS data on nursing homes, 20 papers read in depth, and points made by a care
home worker, as a team member recalls them. Start with the [evidence summary](docs/research/README.md); the
[suggested changes](docs/research/suggested-changes.md) rank what to build next, and [research/](research/) reproduces
the analysis.

## Roadmap

- [x] Arrivals introduced, not corrected: *Here's David, your grandson.*
- [x] Nova says who is here when she can't find a name, and introduces herself once per visit
- [x] Visit summaries leave out bystanders' words, and each arrival logs how long naming took
- [ ] A pause mode for bedrooms and bathrooms, and keeping everything on the machine by default in care homes
- [ ] Cue first, then the name: a moment to recall who it is before the glasses say it
- [ ] Settings for how each person is announced, care staff enrolling through `/visitor`, and a nudge to refresh
  photos and voice

## License and data

MIT; see [LICENSE](LICENSE). The research uses Europe PMC, the CMS Minimum Data Set, the Alzheimer's Association's
*2026 Alzheimer's Disease Facts and Figures* and the WHO dementia fact sheet; full citations are in the
[references](docs/research/references.md). Quotes in `docs/research/` belong to their sources.
