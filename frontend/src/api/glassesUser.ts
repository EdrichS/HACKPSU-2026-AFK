// The glasses user (the wearer, "Rose") is a Person with the relationship "user" on the API:
// GET /user finds them, and the setup flow creates or updates them with the contract routes
// (name, a voice sample, notes that become their facts and card). A copy of the name and the
// typed context is kept in this browser too, so the visitor copy greets with the right name before
// the API has answered, and the setup screens start from what was typed last time.

import { ApiError, addNotes, checkVoice, createPerson, enroll, getUser, updatePerson, uploadVoice } from "./client";
import { USER_RELATIONSHIP } from "./contract";

const KEY = "nametags.glassesUser";

export interface GlassesUser {
  name: string;
  context: string;
}

export function loadGlassesUser(): GlassesUser | null {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const value = JSON.parse(raw);
    return typeof value?.name === "string" && value.name.trim()
      ? { name: value.name, context: typeof value.context === "string" ? value.context : "" }
      : null;
  } catch {
    return null; // storage blocked (private window) or a corrupt value
  }
}

function remember(user: GlassesUser) {
  try {
    localStorage.setItem(KEY, JSON.stringify({ name: user.name.trim(), context: user.context.trim() }));
  } catch {
    // storage blocked: the name still shows on the All set screen, it just won't carry over
  }
}

export interface SaveResult {
  personId: number;
  /** The name as stored. */
  name: string;
  voiceUploaded: boolean;
  /** False when context text was sent but the server stored none of it. */
  contextSaved: boolean;
}

/**
 * The app has one user. Reuse their row if it exists (renamed when the name changed), else let
 * the sign-up route create it; then store this recording and the notes.
 *
 * The notes go through POST /enroll rather than POST /people/{id}/notes: both run the Gemini
 * context flow (which knows the wearer's record is the patient's own), but /enroll also keeps
 * the notes as typed when Gemini is off or adds nothing, so nothing typed is lost.
 */
export async function saveGlassesUser(user: GlassesUser, voice: Blob): Promise<SaveResult> {
  const name = user.name.trim();
  const context = user.context.trim();
  const check = await checkVoice(voice); // actual speech, not a quiet room, before anything is stored
  if (check && !check.ok) throw new ApiError(422, check.reason);
  let person = await getUser();
  if (person && person.name !== name) person = await updatePerson(person.id, { name });

  const form = new FormData();
  form.append("name", name);
  form.append("relationship", USER_RELATIONSHIP);
  form.append("notes", context);
  form.append("merge", person ? "true" : "false");
  form.append("voice", voice, "voice.wav");
  const out = await enroll(form);
  if (out) {
    person = out.person;
  } else {
    // A server without /enroll (the mock): the contract routes, one by one.
    if (person === null) person = await createPerson({ name, relationship: USER_RELATIONSHIP });
    await uploadVoice(person.id, voice);
    if (context) person = await addNotes(person.id, context);
  }
  remember({ name, context });
  return { personId: person.id, name: person.name, voiceUploaded: true, contextSaved: !context || person.small_context !== "" };
}

/**
 * The user as the API knows them, remembered in this browser. Null when nobody is registered,
 * or the API can't be reached (the browser copy then stands in).
 */
export async function syncGlassesUser(): Promise<GlassesUser | null> {
  try {
    const person = await getUser();
    if (!person) return null;
    const user = { name: person.name, context: loadGlassesUser()?.context ?? "" };
    remember(user);
    return user;
  } catch {
    return null;
  }
}
