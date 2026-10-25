# Deploying Nametags

One Docker host runs everything: the API container (faces, voices, the enrollment wizard, the
`/live` socket, Nova) and Postgres with pgvector. The UI is a separate static site that calls the
API; it is not in this repo.

## First time

On a server with Docker Engine and the compose plugin:

```
git clone https://github.com/EdrichS/HACKPSU-2026-AFK.git && cd HACKPSU-2026-AFK
cp .env.example .env            # put the Anthropic and Gemini keys in, set the UI's origin
docker compose up -d --build    # the first build compiles dlib and downloads models: 10-15 minutes
docker compose ps               # both services "healthy"
curl -s localhost:8000/health   # {"status":"ok",...}
```

The API listens on port 8000 (`NAMETAGS_PORT` in `.env`), with interactive docs at `/docs` and a
rough test UI at `/ui/` (the enrollment wizard) and `/ui/live.html` (the glasses view) that
exercises every route from a browser. Open it on `http://localhost:8000/ui/` on the machine
itself, since browsers allow the camera and microphone only on localhost or https.
The API has no login, so it listens on 127.0.0.1 only and answers pages from localhost only;
`NAMETAGS_BIND` and `NAMETAGS_CORS_ORIGINS` open it up (see Environment).
Postgres is reachable only from the host itself, on 5433, for the CLIs and `psql`.

Put a reverse proxy with TLS in front (Caddy, nginx) for a public URL; it reaches the API on
127.0.0.1:8000. The `/live` route is a WebSocket, so proxy that too. Browsers only allow the camera
and microphone on https or localhost. If the UI is served from another site, put its origin in
`NAMETAGS_CORS_ORIGINS`. A phone or glasses on the same Wi-Fi need that proxy, or
`NAMETAGS_BIND=0.0.0.0`, which lets anyone on the network in.

## Updating

```
git pull && docker compose up -d --build
```

The schema is applied at every API start and is idempotent.

## What is state, and moving it

| Where | Holds |
|---|---|
| the `pgdata` volume | every person, face and voice embedding, fact and card |
| the repo's `data/` folder | the photo and recording files (`data/photos`, `data/voice`), shared with the laptop programs |

Nothing else matters; the image is rebuilt from the repo. To move to another server:

```
docker compose stop api
docker run --rm -v hackpsu-2026-afk_pgdata:/v -v "$PWD":/b alpine tar czf /b/pgdata.tgz -C /v .
tar czf data.tgz data
```

Copy the two archives and the repo to the new host, create the volume by starting the stack
once (`docker compose up -d` then `docker compose stop`), and restore:

```
docker run --rm -v hackpsu-2026-afk_pgdata:/v -v "$PWD":/b alpine sh -c "cd /v && tar xzf /b/pgdata.tgz"
tar xzf data.tgz
docker compose up -d
```

(The volume prefix is the folder name; `docker volume ls` shows it.)

## If you ran it before `data/` was shared

The container used to keep its files in a `nametags_data` volume and store their paths as
`/data/...`. After `git pull`, move them into `data/`:

```
docker compose stop api
docker run --rm -v hackpsu-2026-afk_nametags_data:/v -v "$PWD/data":/d alpine cp -a /v/. /d/
docker compose exec db psql -U nametags -d nametags -c "UPDATE photos SET file_path = 'data/' || substr(file_path, 7) WHERE file_path LIKE '/data/%'" -c "UPDATE voice_samples SET audio_path = 'data/' || substr(audio_path, 7) WHERE audio_path LIKE '/data/%'"
docker compose up -d --build
```

Once the photos open, `docker volume rm hackpsu-2026-afk_nametags_data` removes the old volume.

## Resetting

```
docker compose down -v && find data -type f -delete && docker compose up -d
```

deletes every person, photo and recording.

## Environment

| Variable | Default | Meaning |
|---|---|---|
| `GEMINI_API_KEY` | empty | notes and visit summaries into facts and cards; without it the wizard and `python -m enroll` store notes as typed, `POST /people/{id}/notes` and `/conversation` store nothing, and visits aren't summarized |
| `ANTHROPIC_API_KEY` | empty | Nova; without it the API still recognizes, captions and summarizes |
| `NAMETAGS_BIND` | `127.0.0.1` | address the API listens on; `0.0.0.0` opens it to the network, and it has no login |
| `NAMETAGS_CORS_ORIGINS` | empty | origins of a UI on another site, comma-separated; empty allows pages on localhost only, `*` lets any site read everything |
| `NAMETAGS_PORT` | `8000` | host port |
| `NAMETAGS_EMBEDDERS` | `real` | `fake` uses the contract's stand-ins (tests only) |
| `NAMETAGS_TRANSCRIBE` | `1` | `0` turns captions off |

## Running without Docker

The same API runs on a laptop with `uv run uvicorn backend.app:app --port 8000` against
`docker compose up -d --wait db`. It loads the real face and voice models at startup, so download
the voice models once first: `hackpsu_voice_rec/scripts/download_models.sh --no-tts`. It keeps its
files in the same `data/` folder as the container. The laptop-only programs, `python -m enroll`
(webcam and mic windows) and `python -m live` (speaks through the laptop), stay as they are.
