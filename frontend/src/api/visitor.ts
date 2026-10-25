// Upload on About you "submits everything". The contract has no single sign-up route, so this
// composes the existing setup routes, in an order that refuses a duplicate name before any
// photo leaves the browser, and removes the new person again if a later step fails.
//
// If that removal fails too (the connection dropped), the half-made person's id is kept in
// sessionStorage and removed at the start of the next Upload, so the retry isn't refused as a
// duplicate of the visitor's own leftover. sessionStorage also covers a reload mid-upload.

import { ApiError, addNotes, assignFace, createPerson, deletePerson, uploadPhoto, uploadVoice } from "./client";
import type { DetectedFace, Person } from "./contract";

export interface VisitorSubmission {
  name: string;
  relationship: string;
  context: string;
  photos: { blob: Blob; pose: string }[];
  voice: Blob;
}

export interface SubmitResult {
  person: Person;
  /** Photos where a face was found and labelled with this person (of 5). */
  facesLabelled: number;
  /** False when the notes route answered 404/405: the real backend doesn't mount it yet. */
  contextSaved: boolean;
}

export type SubmitErrorKind = "duplicate" | "no_face" | "voice" | "offline" | "other";

export class SubmitError extends Error {
  readonly kind: SubmitErrorKind;

  constructor(kind: SubmitErrorKind, message: string) {
    super(message);
    this.name = "SubmitError";
    this.kind = kind;
  }
}

const LEFTOVER_KEY = "nametags.unfinishedPersonId";

function leftover(): number | null {
  try {
    const id = Number(sessionStorage.getItem(LEFTOVER_KEY));
    return Number.isInteger(id) && id > 0 ? id : null;
  } catch {
    return null;
  }
}

function setLeftover(id: number | null) {
  try {
    if (id === null) sessionStorage.removeItem(LEFTOVER_KEY);
    else sessionStorage.setItem(LEFTOVER_KEY, String(id));
  } catch {
    // storage blocked: a failed rollback just can't be retried after a reload
  }
}

/** Delete a person, treating "already gone" as done. Tries twice: a dropped request is common here. */
async function removePerson(id: number): Promise<void> {
  for (let attempt = 0; ; attempt++) {
    try {
      await deletePerson(id);
      return;
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) return;
      if (attempt >= 1) throw e;
    }
  }
}

/** A selfie can catch someone in the background; the visitor is the biggest face. */
function largest(faces: DetectedFace[]): DetectedFace | null {
  return faces.reduce<DetectedFace | null>(
    (best, f) => (!best || f.box.width * f.box.height > best.box.width * best.box.height ? f : best),
    null,
  );
}

let inFlight: Promise<SubmitResult> | null = null;

/** The Upload still running, if the visitor left About you and came back during it. */
export function submissionInProgress(): Promise<SubmitResult> | null {
  return inFlight;
}

/** One Upload at a time: a second call while one runs gets the same result. */
export function submitVisitor(s: VisitorSubmission): Promise<SubmitResult> {
  inFlight ??= submit(s).finally(() => {
    inFlight = null;
  });
  return inFlight;
}

async function submit(s: VisitorSubmission): Promise<SubmitResult> {
  let person: Person;
  try {
    const unfinished = leftover();
    if (unfinished !== null) {
      await removePerson(unfinished);
      setLeftover(null);
    }
    person = await createPerson({ name: s.name.trim(), relationship: s.relationship.trim() });
    setLeftover(person.id); // until the whole sign-up has gone through
  } catch (e) {
    throw asSubmitError(e);
  }

  try {
    let facesLabelled = 0;
    for (const photo of s.photos) {
      const out = await uploadPhoto(photo.blob, `${photo.pose}.jpg`);
      const face = largest(out.faces);
      if (face) {
        await assignFace(face.face_id, person.id);
        facesLabelled++;
      }
    }
    if (facesLabelled === 0) {
      throw new SubmitError("no_face", "We couldn't find your face in any of the photos. Please take them again in better light.");
    }

    try {
      await uploadVoice(person.id, s.voice);
    } catch (e) {
      if (e instanceof ApiError && e.status === 422) throw new SubmitError("voice", e.message);
      throw e;
    }

    let contextSaved = true;
    if (s.context.trim()) {
      try {
        person = await addNotes(person.id, s.context.trim());
      } catch (e) {
        // The real backend doesn't mount the context owner's routes yet. The visitor's photos and
        // voice are in, so don't fail the whole sign-up over the optional notes.
        if (e instanceof ApiError && (e.status === 404 || e.status === 405)) contextSaved = false;
        else throw e;
      }
    }
    setLeftover(null);
    return { person, facesLabelled, contextSaved };
  } catch (e) {
    // Undo the half-made person: their faces go back to unlabelled and their voice is deleted.
    // The photos themselves stay, because the contract has no route to delete a photo.
    try {
      await removePerson(person.id);
      setLeftover(null);
    } catch {
      // still offline: the next Upload removes it first (see the top of this file)
    }
    throw asSubmitError(e);
  }
}

function asSubmitError(e: unknown): SubmitError {
  if (e instanceof SubmitError) return e;
  if (e instanceof ApiError) {
    if (e.status === 409) return new SubmitError("duplicate", e.message);
    if (e.status === 0) return new SubmitError("offline", e.message);
    return new SubmitError("other", e.message);
  }
  return new SubmitError("other", "Something went wrong. Please try again.");
}
