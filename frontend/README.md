# Name Tags frontend

The screens from `Design/HANDOFF.md`, in React + Vite + TypeScript:

| Path | Screens |
|---|---|
| `/visitor` | Visitor sign up: Intro, Consent, Face photos, Voice, About you, Thank you |
| `/setup` | Glasses user setup: Name, Context, Voice, All set |
| `/live` | Glasses live view (HUD) |
| `/` | A launcher linking to the three |

## Run

Start the API first, from the repo folder: the mock (no database) or the real backend.

```
uv run uvicorn mock.app:app --port 8000
```

Then, from this folder:

```
npm install
npm run dev
```

Open http://localhost:5173. Vite forwards `/api/*` (and the `/api/live` WebSocket) to
`NAMETAGS_API`, default `http://127.0.0.1:8000`, so the pages and the API share one origin.
Copy `.env.example` to `.env.local` to change it, the glasses user's name or the contact email.
For pages served apart from the API, `VITE_API_BASE` (default `/api`) sets where the HTTP calls
go, and `VITE_LIVE_URL` sets the `/live` socket's full address (without it, the socket follows
`VITE_API_BASE`).

`npm run build` type-checks and writes `dist/`; `npm run preview` serves it on port 4173 with the
same proxy. `npm run typecheck` only type-checks.

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
- `src/api/contract.ts`: the TypeScript copy of `contract/*.py`; change both together. It is
  behind today: it has no `end_visit`, `answer` or `visit_saved` messages and no `facts` on
  people, and its `caption` has a `final` field the backend never sends.
- `src/api/visitor.ts`: what Upload on About you sends, in order.
- `src/api/glassesUser.ts`: the glasses user's name and context are kept in this browser, and the
  voice sample isn't sent. The backend can now register the wearer (`POST /enroll` with
  relationship `user`) and serves `GET /user`; this page doesn't use them yet.
- `src/hud/`: the live view.
