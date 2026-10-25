// HTTP calls to the setup routes. Every path is relative to API_BASE, which Vite proxies to the
// backend or the mock (see vite.config.ts).

import type { EnrollOut, Fact, PersonIn, PersonPatch, Person, PhotoOut, VoiceOut, VoiceSample } from "./contract";

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

export async function listPeople(): Promise<Person[]> {
  return (await request("/people")).json();
}

export async function getPerson(personId: number): Promise<Person> {
  return (await request(`/people/${personId}`)).json();
}

export async function createPerson(body: PersonIn): Promise<Person> {
  return (await request("/people", { method: "POST", ...json(body) })).json();
}

export async function deletePerson(personId: number): Promise<void> {
  await request(`/people/${personId}`, { method: "DELETE" });
}

export async function updatePerson(personId: number, patch: PersonPatch): Promise<Person> {
  return (await request(`/people/${personId}`, { method: "PATCH", ...json(patch) })).json();
}

/** The glasses user (the Person whose relationship is "user"), or null when nobody is registered yet. */
export async function getUser(): Promise<Person | null> {
  try {
    return (await request("/user")).json();
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

export async function uploadPhoto(photo: Blob, filename: string): Promise<PhotoOut> {
  return (await request("/photos", { method: "POST", ...file(photo, filename) })).json();
}

/** Every photo with its faces and their labels. */
export async function listPhotos(): Promise<PhotoOut[]> {
  return (await request("/photos")).json();
}

/** The photo itself, for an <img>. */
export function photoImageUrl(photoId: number): string {
  return `${API_BASE}/photos/${photoId}/image`;
}

/** Remove a photo and every face in it: a shot with no face, or a sign-up that failed halfway. */
export async function deletePhoto(photoId: number): Promise<void> {
  await request(`/photos/${photoId}`, { method: "DELETE" });
}

export interface VoiceCheck {
  ok: boolean;
  seconds: number;
  speech_seconds: number;
  reason: string;
}

/**
 * Does this recording hold enough actual speech? Null when the server has no such check (the
 * mock): the upload then decides.
 */
export async function checkVoice(wav: Blob): Promise<VoiceCheck | null> {
  try {
    return (await request("/enroll/check/voice", { method: "POST", ...file(wav, "voice.wav") })).json();
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 405)) return null;
    throw e;
  }
}

/**
 * The real backend's one-shot sign-up (multipart name, relationship, notes, merge, photos, voice).
 * Null when the server has no such route (the mock).
 */
export async function enroll(form: FormData): Promise<EnrollOut | null> {
  try {
    return (await request("/enroll", { method: "POST", body: form })).json();
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 405)) return null;
    throw e;
  }
}

/** Label a face with a person; null unlabels it. */
export async function assignFace(faceId: number, personId: number | null): Promise<void> {
  await request(`/faces/${faceId}/assign`, { method: "POST", ...json({ person_id: personId }) });
}

export async function uploadVoice(personId: number, wav: Blob): Promise<VoiceOut> {
  return (await request(`/people/${personId}/voice`, { method: "POST", ...file(wav, "voice.wav") })).json();
}

export async function listVoice(personId: number): Promise<VoiceSample[]> {
  return (await request(`/people/${personId}/voice`)).json();
}

/** The recording itself (16 kHz WAV), for an <audio>. */
export function voiceAudioUrl(personId: number, sampleId: number): string {
  return `${API_BASE}/people/${personId}/voice/${sampleId}/audio`;
}

export async function deleteVoice(personId: number, sampleId: number): Promise<void> {
  await request(`/people/${personId}/voice/${sampleId}`, { method: "DELETE" });
}

/** The context owner's route: turns typed notes into facts and rewrites the card. */
export async function addNotes(personId: number, text: string): Promise<Person> {
  return (await request(`/people/${personId}/notes`, { method: "POST", ...json({ text }) })).json();
}

// The record behind the card, as the family manages it (no Claude): facts as typed.

export async function listFacts(personId: number): Promise<Fact[]> {
  return (await request(`/people/${personId}/facts`)).json();
}

/** 409 when the record already says that. */
export async function addFact(personId: number, text: string): Promise<Fact> {
  return (await request(`/people/${personId}/facts`, { method: "POST", ...json({ text }) })).json();
}

export async function updateFact(personId: number, factId: number, text: string): Promise<Fact> {
  return (await request(`/people/${personId}/facts/${factId}`, { method: "PATCH", ...json({ text }) })).json();
}

export async function deleteFact(personId: number, factId: number): Promise<void> {
  await request(`/people/${personId}/facts/${factId}`, { method: "DELETE" });
}

/** Claude writes the card again from the stored facts. 422 with no facts, 503 without Claude, 502 when it fails. */
export async function rewriteCard(personId: number): Promise<Person> {
  return (await request(`/people/${personId}/card`, { method: "POST" })).json();
}

/** ws(s)://<this host>/api/live, or VITE_LIVE_URL when the socket lives somewhere else. */
export function liveUrl(): string {
  const configured = import.meta.env.VITE_LIVE_URL;
  if (configured) return configured;
  const scheme = location.protocol === "https:" ? "wss:" : "ws:";
  const base = API_BASE.startsWith("http") ? API_BASE.replace(/^http/, "ws") : `${scheme}//${location.host}${API_BASE}`;
  return `${base}/live`;
}
