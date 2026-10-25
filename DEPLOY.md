# Deploying Nametags

One Docker host runs everything: the API container (faces, voices, the enrollment wizard, the
`/live` socket, Nova) and Postgres with pgvector. The UI is a separate static site that calls the
API; it is not in this repo.

## First time

On a server with Docker Engine and the compose plugin:

```
git clone https://github.com/EdrichS/HACKPSU-2026-AFK.git && cd HACKPSU-2026-AFK
cp .env.example .env            # put the Anthropic key in, set the UI's origin
docker compose up -d --build    # the first build compiles dlib and downloads models: 10-15 minutes
docker compose ps               # both services "healthy"
curl -s localhost:8000/health   # {"status":"ok",...}
```

The API listens on port 8000 (`NAMETAGS_PORT` in `.env`), with interactive docs at `/docs` and a
rough test UI at `/ui/` (the enrollment wizard) and `/ui/live.html` (the glasses view) that
exercises every route from a browser. Open it on `http://localhost:8000/ui/` on the machine
itself, since browsers allow the camera and microphone only on localhost or https.
Postgres is reachable only from the host itself, on 5433, for the CLIs and `psql`.

Put a reverse proxy with TLS in front (Caddy, nginx) for a public URL; the `/live` route is a
WebSocket, so proxy that too. Browsers only allow the camera and microphone on https or localhost.

## Updating

```
git pull && docker compose up -d --build
```

The schema is applied at every API start and is idempotent.

## What is state, and moving it

| Volume | Holds |
|---|---|
| `pgdata` | every person, face and voice embedding, fact and card |
| `nametags_data` | the photo and recording files (`/data/photos`, `/data/voice`) |

Nothing else matters; the image is rebuilt from the repo. To move to another server:

```
docker compose stop api
docker run --rm -v hackpsu-2026-afk_pgdata:/v -v "$PWD":/b alpine tar czf /b/pgdata.tgz -C /v .
docker run --rm -v hackpsu-2026-afk_nametags_data:/v -v "$PWD":/b alpine tar czf /b/data.tgz -C /v .
```

Copy the two archives and the repo to the new host, create the volumes by starting the stack
once (`docker compose up -d` then `docker compose stop`), and restore:

```
docker run --rm -v hackpsu-2026-afk_pgdata:/v -v "$PWD":/b alpine sh -c "cd /v && tar xzf /b/pgdata.tgz"
docker run --rm -v hackpsu-2026-afk_nametags_data:/v -v "$PWD":/b alpine sh -c "cd /v && tar xzf /b/data.tgz"
docker compose up -d
```

(The volume prefix is the folder name; `docker volume ls` shows it.)

## Resetting

```
docker compose down -v && docker compose up -d
```

deletes every person, photo and recording.

## Environment

| Variable | Default | Meaning |
|---|---|---|
| `ANTHROPIC_API_KEY` | empty | visit summaries and Nova; without it the API still recognizes and captions |
| `NAMETAGS_CORS_ORIGINS` | `*` | origins the UI is served from; `*` for any |
| `NAMETAGS_PORT` | `8000` | host port |
| `NAMETAGS_EMBEDDERS` | `real` | `fake` uses the contract's stand-ins (tests only) |
| `NAMETAGS_TRANSCRIBE` | `1` | `0` turns captions off |

## Running without Docker

The same API runs on a laptop with `uv run uvicorn backend.app:app --port 8000` against
`docker compose up -d --wait db`. The laptop-only programs, `python -m enroll` (webcam and mic
windows) and `python -m live` (speaks through the laptop), stay as they are.
