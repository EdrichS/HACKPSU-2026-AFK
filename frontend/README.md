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
- `src/api/glassesUser.ts`: the glasses user is kept in this browser until the API has a route
  for them (see `report.txt` in the repo folder).
- `src/hud/`: the live view.
