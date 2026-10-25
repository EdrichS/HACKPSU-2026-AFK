// What the manage screens share: loading a record set from the API, wording for its failures,
// and the small layout pieces (a section card, a row of fields with a button) the mockups don't
// have. Not designed: the whole area is a family-facing admin view in the style of the flows.

import { useCallback, useEffect, useState, type ReactNode } from "react";

import { ApiError } from "../../api/client";
import { USER_RELATIONSHIP, type Person } from "../../api/contract";
import styles from "./manage.module.css";

/** A sentence for a failed call, in the voice of the flows' notices. */
export function describe(e: unknown, doing: string): string {
  if (e instanceof ApiError && e.status === 0) return `You seem to be offline. Check your connection, then try ${doing} again.`;
  if (e instanceof ApiError && (e.status === 502 || e.status === 504)) return e.message; // the client's proxy sentence, or the route's own detail
  if (e instanceof ApiError && e.status === 404) return "That record is gone. It may have been removed on another device.";
  if (e instanceof ApiError) return e.message;
  return `Something went wrong while ${doing}. Please try again.`;
}

export interface Loaded<T> {
  data: T | null;
  /** Null while loading and after a successful load. */
  error: string | null;
  loading: boolean;
  reload: () => void;
  /** Change the loaded value in place after a successful write, so the screen doesn't flash. */
  set: (update: (previous: T) => T) => void;
}

/**
 * Fetch on mount (and on `reload`), with a cancelled flag so StrictMode's double mount and a
 * fast navigation away never set state on an unmounted screen. `key` identifies what's loaded:
 * change it (the person id) and it loads again.
 */
export function useLoad<T>(load: () => Promise<T>, key: string | number): Loaded<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    load().then(
      (value) => {
        if (cancelled) return;
        setData(value);
        setLoading(false);
      },
      (e: unknown) => {
        if (cancelled) return;
        setError(describe(e, "loading"));
        setLoading(false);
      },
    );
    return () => {
      cancelled = true;
    };
    // `load` is a fresh closure each render; `key` and `attempt` say when to run it again.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, attempt]);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);
  const set = useCallback((update: (previous: T) => T) => setData((previous) => (previous === null ? previous : update(previous))), []);
  return { data, error, loading, reload, set };
}

/** The wearer's row is special: "Glasses user" rather than a relationship to themselves. */
export function isGlassesUser(person: Person): boolean {
  return isUserRelationship(person.relationship);
}

/** The words the backend reserves for the wearer (enroll/store.py USER_RELATIONSHIPS). */
export function isUserRelationship(relationship: string): boolean {
  const word = relationship.trim().toLowerCase();
  return word === USER_RELATIONSHIP || word === "patient";
}

export function relationshipLabel(person: Person): string {
  if (isGlassesUser(person)) return "Glasses user";
  const text = person.relationship.trim();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** The flows' "Step 2 of 4" style heading over a block of the page. */
export function Section({ title, aside, children }: { title: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <section className={styles.section} aria-label={title}>
      <div className={styles.sectionHead}>
        <h2 className={styles.sectionTitle}>{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  );
}

/** A short date for a record: "25 Oct 2026". */
export function shortDate(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}
