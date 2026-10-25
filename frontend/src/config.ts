import { loadGlassesUser } from "./api/glassesUser";

/** Suggested character limits (HANDOFF.md, Content). Not designed; the API allows more. */
export const LIMITS = {
  firstName: 24,
  otherRelationship: 40, // PersonIn.relationship's own limit
  visitorContext: 500,
  glassesUserContext: 1000,
} as const;

const PLACEHOLDER_NAME = "Rose"; // the design's sample glasses user
const LINK_NAME_KEY = "nametags.forName";

/**
 * The glasses user's first name for the visitor copy. A shared link can carry it (?for=Rose);
 * otherwise the setup done in this browser, then VITE_GLASSES_USER_NAME, then the placeholder.
 */
export function resolveGlassesUserName(search: string = location.search): string {
  const fromLink = new URLSearchParams(search).get("for")?.trim().slice(0, LIMITS.firstName);
  // The flow's own links drop the query, so keep the link's name for this tab: a reload mid-flow
  // (common on phones) would otherwise greet the visitor with the wrong name.
  try {
    if (fromLink) sessionStorage.setItem(LINK_NAME_KEY, fromLink);
    const remembered = sessionStorage.getItem(LINK_NAME_KEY)?.trim();
    if (remembered) return remembered;
  } catch {
    if (fromLink) return fromLink; // storage blocked
  }
  const fromSetup = loadGlassesUser()?.name.trim();
  if (fromSetup) return fromSetup;
  const fromEnv = (import.meta.env.VITE_GLASSES_USER_NAME as string | undefined)?.trim();
  return fromEnv || PLACEHOLDER_NAME;
}

/** The Consent screen's contact address, or null to show the design's placeholder. */
export const CONTACT_EMAIL: string | null = (import.meta.env.VITE_CONTACT_EMAIL as string | undefined)?.trim() || null;

/** "Rose's", "James's". */
export function possessive(name: string): string {
  return `${name}'s`;
}
