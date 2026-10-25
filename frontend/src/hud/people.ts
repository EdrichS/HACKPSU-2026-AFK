import type { PresentPerson } from "../api/contract";
import type { TrackView } from "./tracker";

function stripMarker(line: string): string {
  return line.replace(/^\s*[-•*]+\s*/, "").trim();
}

function tidy(text: string): string {
  return stripMarker(text).replace(/(?<!\.)\.$/, "");
}

/** The card as the panel shows it: the latest conversation, the standing context, what to ask about. */
export interface CardSections {
  /** "Last spoke about: ..." */
  recent: string | null;
  /** The card's other fragments, in order. */
  about: string[];
  /** "Ask about: ..." */
  ask: string | null;
}

const RECENT = /^last spoke about:\s*/i;
const ASK = /^ask about:\s*/i;

/**
 * Reads the card Claude writes ("Last spoke about: x · Works as a nurse | Ask about: y, z") into
 * its sections, so the panel can set each one in its own type. A hand-written card without those
 * markers is all "about": one fragment per line, or per " · ". Nothing here comes from the facts.
 */
export function parseCard(smallContext: string): CardSections {
  const sections: CardSections = { recent: null, about: [], ask: null };
  for (const part of smallContext.split(/\r?\n|\s*\|\s*/)) {
    const text = stripMarker(part);
    if (!text) continue;
    if (ASK.test(text)) {
      sections.ask = tidy(text.replace(ASK, ""));
      continue;
    }
    const pieces = text.split(/\s*[·•]\s*/).map(tidy).filter(Boolean);
    if (pieces.length > 0 && RECENT.test(pieces[0])) sections.recent = tidy(pieces.shift()!.replace(RECENT, ""));
    sections.about.push(...pieces);
  }
  return sections;
}

/** "granddaughter" (as the visitor flow stores it) to "Granddaughter" (as the HUD shows it). */
export function capitalize(text: string): string {
  const trimmed = text.trim();
  return trimmed.charAt(0).toUpperCase() + trimmed.slice(1);
}

/**
 * Whose card the info panel shows: the named face with the largest box; with no named face, the
 * last person recognized by voice, while the server still lists them as present.
 */
export function choosePanelPerson(
  tracks: TrackView[],
  directory: ReadonlyMap<number, PresentPerson>,
  present: PresentPerson[],
  voicePersonId: number | null,
): PresentPerson | null {
  let best: PresentPerson | null = null;
  let bestArea = -1;
  for (const track of tracks) {
    if (track.state !== "named" || track.personId === null) continue;
    const person = directory.get(track.personId);
    const area = track.box.width * track.box.height;
    if (person && area > bestArea) {
      best = person;
      bestArea = area;
    }
  }
  if (best) return best;
  if (voicePersonId === null) return null;
  return present.find((p) => p.person_id === voicePersonId) ?? null;
}
