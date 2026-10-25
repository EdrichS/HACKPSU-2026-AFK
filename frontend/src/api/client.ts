// HTTP calls to the setup routes. Every path is relative to API_BASE, which Vite proxies to the
// backend or the mock (see vite.config.ts).

import type { PersonIn, Person, PhotoOut, VoiceOut } from "./contract";

export const API_BASE: string = import.meta.env.VITE_API_BASE ?? "/api";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** FastAPI sends {"detail": "..."} for our errors and {"detail": [{msg, ...}]} for validation. */
async function errorFrom(response: Response): Promise<ApiError> {
  // 502 from the dev proxy means the API itself isn't running.
  let message =
    response.status === 502 || response.status === 504
      ? "The Name Tags server isn't answering."
      : `The server had a problem (${response.status}).`;
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") message = body.detail;
    else if (Array.isArray(body?.detail) && body.detail[0]?.msg) message = body.detail[0].msg;
  } catch {
    // not JSON; keep the sentence above
  }
  // Messages are shown inside a sentence of our own, so each ends like one.
  if (!/[.!?]$/.test(message)) message += ".";
  return new ApiError(response.status, message);
}

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, init);
  } catch {
    // fetch only rejects when the request never got an answer: offline, or the server is down
    throw new ApiError(0, "Can't reach Name Tags. Check your connection and try again.");
  }
  if (!response.ok) throw await errorFrom(response);
  return response;
}

function json(body: unknown): RequestInit {
  return { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

function file(blob: Blob, filename: string): RequestInit {
  const form = new FormData();
  form.append("file", blob, filename);
  return { body: form };
}

export async function createPerson(body: PersonIn): Promise<Person> {
  return (await request("/people", { method: "POST", ...json(body) })).json();
}

export async function deletePerson(personId: number): Promise<void> {
  await request(`/people/${personId}`, { method: "DELETE" });
}

export async function uploadPhoto(photo: Blob, filename: string): Promise<PhotoOut> {
  return (await request("/photos", { method: "POST", ...file(photo, filename) })).json();
}

/** Label a face with a person; null unlabels it. */
export async function assignFace(faceId: number, personId: number | null): Promise<void> {
  await request(`/faces/${faceId}/assign`, { method: "POST", ...json({ person_id: personId }) });
}

export async function uploadVoice(personId: number, wav: Blob): Promise<VoiceOut> {
  return (await request(`/people/${personId}/voice`, { method: "POST", ...file(wav, "voice.wav") })).json();
}

/** The context owner's route: turns typed notes into facts and rewrites the card. */
export async function addNotes(personId: number, text: string): Promise<Person> {
  return (await request(`/people/${personId}/notes`, { method: "POST", ...json({ text }) })).json();
}

/** ws(s)://<this host>/api/live, or VITE_LIVE_URL when the socket lives somewhere else. */
export function liveUrl(): string {
  const configured = import.meta.env.VITE_LIVE_URL;
  if (configured) return configured;
  const scheme = location.protocol === "https:" ? "wss:" : "ws:";
  const base = API_BASE.startsWith("http") ? API_BASE.replace(/^http/, "ws") : `${scheme}//${location.host}${API_BASE}`;
  return `${base}/live`;
}
