# Name Tags frontend

The screens from `Design/HANDOFF.md`, in React + Vite + TypeScript:

| Path | Screens |
|---|---|
| `/visitor` | Visitor sign up: Intro, Consent, Face photos, Voice, About you, Thank you |
| `/setup` | Glasses user setup: Name, Context, Voice, All set |
| `/live` | Glasses live view (HUD) |
| `/manage` | Manage (not designed, real backend only): every person with their card, facts, photos and voice recordings, plus faces still to label |
| `/` | A launcher linking to the three |

## Run

Start the API first, from the repo folder: the real backend (`docker compose up -d --build`, or
`uv run uvicorn backend.app:app --port 8000` against `docker compose up -d --wait db`), or the mock
(no database, no recognition):

```
uv run uvicorn mock.app:app --port 8000
```

In Docker the API also serves this app itself: `http://localhost:8000/` is the built frontend,
calling `/api/...` on the same origin. `npm run dev` is for working on the pages.

Then, from this folder:

```
npm install
npm run dev
```

Open http://localhost:5173. Vite forwards `/api/*` (and the `/api/live` WebSocket) to
`NAMETAGS_API`, default `http://127.0.0.1:8000`, so the pages and the API share one origin.
Copy `.env.example` to `.env.local` to change it, the glasses user's name or the contact email.

`npm run build` type-checks and writes `dist/`; `npm run preview` serves it with the same proxy.

## Without a camera or microphone

In `npm run dev`, add `?preview` to a flow URL (`/visitor/about?preview`, `/setup/voice?preview`)
to start it with sample photos and a sample recording. `/live?demo=1` draws the HUD over the
mockup's illustration with its sample data, for comparing against
`Design/screens/glasses/live-view.html` at 1600 × 900.

HUD settings from the handoff go in the URL: `?tag=0.45` (0.2 to 0.85), `?glass=0.5` (0.1 to
0.85), `?accent=yellow|cyan|green|white`, `?boxes=0`, `?mirror=1`.

## Phones

Browsers only allow the camera and microphone on `localhost` or over HTTPS. To sign up from a
phone on the same network, serve the dev server over HTTPS (for example with a mkcert certificate
in `server.https` in `vite.config.ts`) or through an HTTPS tunnel.

## Where things are

- `src/styles/tokens.css`: every design token from the handoff.
- `src/components/`: the handoff's components (LogoTag, StepIndicator, Button, TextField,
  TextArea, ChipGroup, ConsentList, ConsentCheckbox, CameraViewfinder, PhotoStrip, VoicePrompt,
  Recorder, NameTag) and the page shell.
- `src/api/contract.ts`: the TypeScript copy of `contract/*.py`. Change both together.
- `src/api/visitor.ts`: what Upload on About you sends, in order.
- `src/api/glassesUser.ts`: the glasses user is the Person with relationship `user` on the API
  (`GET /user`); setup creates or updates them, uploads their voice and sends their notes. A copy
  of the name stays in this browser so the visitor copy can greet with it at once.
- `src/hud/`: the live view.
