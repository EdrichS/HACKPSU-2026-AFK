import type { PresentPerson } from "../api/contract";
import type { TrackView } from "./tracker";

const MAX_LINES = 3;

function stripMarker(line: string): string {
  return line.replace(/^\s*[-•*]+\s*/, "").trim();
}

/**
 * What the info panel shows: the person's card, the short context Claude writes from their facts
 * ("Last spoke about: x · Works as a nurse | Ask about: y"), and nothing else. The card's two halves
 * become two lines, the summary and the conversation starters, so recent conversations and new
 * context show up as the card changes; a hand-written card shows one line per line typed. The
 * facts themselves never appear here: they are the record the card is written from.
 */
export function toBullets(smallContext: string): string[] {
  const lines = smallContext.split(/\r?\n|\s*\|\s*/).map(stripMarker).filter(Boolean);
  return lines.slice(0, MAX_LINES).map((line) => line.replace(/(?<!\.)\.$/, ""));
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
