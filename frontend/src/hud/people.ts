import type { PresentPerson } from "../api/contract";
import type { TrackView } from "./tracker";

const MAX_BULLETS = 3;

function stripMarker(line: string): string {
  return line.replace(/^\s*[-•*]+\s*/, "").trim();
}

/** A sentence can't end on "Dr.", "St.", "e.g." or an initial like "J.". */
const ABBREVIATION = /(?:\b(?:Dr|Mr|Mrs|Ms|Mx|Prof|St|Mt|Jr|Sr|Ave|Rd|vs|etc|approx|e\.g|i\.e)|(?:^|\s)[A-Z])\.$/;

function sentences(text: string): string[] {
  const out: string[] = [];
  for (const part of text.split(/(?<=[.!?])\s+/)) {
    if (out.length > 0 && ABBREVIATION.test(out[out.length - 1])) out[out.length - 1] += ` ${part}`;
    else out.push(part);
  }
  return out;
}

/**
 * The info panel's bullets from a person's small_context: one per line, or one per sentence when
 * the summary is a single paragraph; at most 3. The design's bullets have no closing period.
 */
export function toBullets(smallContext: string): string[] {
  let lines = smallContext.split(/\r?\n/).map(stripMarker).filter(Boolean);
  if (lines.length === 1) lines = sentences(lines[0]).map(stripMarker).filter(Boolean);
  return lines.slice(0, MAX_BULLETS).map((line) => line.replace(/(?<!\.)\.$/, ""));
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
