// The mockup's sample data, fed through the real components by /live?demo=1, so the result can be
// laid over Design/screens/glasses/live-view.html at 1600 × 900 for visual QA.

import type { PresentPerson } from "../api/contract";
import type { CaptionLine } from "./captionLines";
import type { FaceSnapshot } from "./tracker";

export const DEMO_PERSON: PresentPerson = {
  person_id: 1,
  name: "Maya",
  relationship: "granddaughter",
  small_context: "Anita's daughter, your oldest grandchild\nStudying nursing, in her final year\nVisits most Sundays after lunch",
};

export const DEMO_PEOPLE: PresentPerson[] = [DEMO_PERSON];
export const DEMO_DIRECTORY: ReadonlyMap<number, PresentPerson> = new Map([[DEMO_PERSON.person_id, DEMO_PERSON]]);

/** A detected face whose bracket box lands where the mockup draws it: 626, 204, 188 × 232. */
export const DEMO_FACES: FaceSnapshot = {
  faces: [{ box: { x: 642, y: 222, width: 156, height: 192 }, state: "named", personId: DEMO_PERSON.person_id }],
  at: Number.POSITIVE_INFINITY, // never goes stale
};

export const DEMO_CAPTION: CaptionLine = {
  speaker: "Maya",
  text: "Hi Grandma! I brought the photos from our beach trip. Want to see them?",
  final: false,
};
