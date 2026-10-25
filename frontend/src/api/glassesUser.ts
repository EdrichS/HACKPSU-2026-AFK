// The glasses user (the wearer, "Rose"). The contract has no route for them yet: no table, no
// name, no context, no voice sample. Until one exists, setup is kept in this browser so the
// visitor flow on the same device can greet visitors with the right name. See report.txt for
// the routes this needs; when they exist, replace the body of saveGlassesUser and keep its shape.

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

export interface SaveResult {
  /** False until the backend has a route for the glasses user's voice sample. */
  voiceUploaded: boolean;
}

export async function saveGlassesUser(user: GlassesUser, voice: Blob): Promise<SaveResult> {
  void voice; // validated by the Recorder (16 kHz mono WAV, long enough), but there's nowhere to send it yet
  try {
    localStorage.setItem(KEY, JSON.stringify({ name: user.name.trim(), context: user.context.trim() }));
  } catch {
    // storage blocked: the name still shows on the All set screen, it just won't carry over
  }
  return { voiceUploaded: false };
}
