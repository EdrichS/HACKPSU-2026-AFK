// What the visitor flow collects, held in memory until Upload on About you sends it all.
// Nothing is stored in the browser: closing the tab discards the photos and the recording.

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { resolveGlassesUserName } from "../../config";
import { previewEnabled, samplePhotos, sampleRecording } from "../../dev/preview";
import type { Recording } from "../../lib/recording";

export type Pose = "front" | "left" | "right" | "up" | "down";

/** PhotoStrip order: Front, Left, Right, Up, Down. */
export const POSES: readonly { pose: Pose; label: string; instruction: string }[] = [
  { pose: "front", label: "Front", instruction: "Look straight at the camera" },
  { pose: "left", label: "Left", instruction: "Turn your head a little to the left" },
  { pose: "right", label: "Right", instruction: "Now a little to the right" },
  { pose: "up", label: "Up", instruction: "Tilt your head up a little" },
  { pose: "down", label: "Down", instruction: "Tilt your head down a little" },
];

export interface CapturedPhoto {
  pose: Pose;
  /** JPEG, unmirrored, at the camera's resolution. */
  blob: Blob;
  /** Object URL of `blob`, for thumbnails and the Thank you photo. */
  url: string;
  width: number;
  height: number;
}

export const RELATIONSHIPS = ["Son", "Daughter", "Grandson", "Granddaughter", "Friend", "Caregiver", "Other"] as const;

export interface AboutYou {
  name: string;
  /** One of RELATIONSHIPS, or null before a chip is picked. */
  relationship: string | null;
  /** The short text field "Other" reveals. */
  otherRelationship: string;
  context: string;
}

export interface Submitted {
  name: string;
  photoUrl: string | null;
}

interface VisitorFlow {
  glassesUserName: string;
  consent: boolean;
  setConsent: (value: boolean) => void;
  photos: CapturedPhoto[];
  setPhotos: (photos: CapturedPhoto[]) => void;
  voice: Recording | null;
  setVoice: (voice: Recording | null) => void;
  about: AboutYou;
  setAbout: (about: AboutYou) => void;
  submitted: Submitted | null;
  setSubmitted: (submitted: Submitted) => void;
  /** Forget everything (Decline goes back to Intro with a clean slate). */
  reset: () => void;
}

const EMPTY_ABOUT: AboutYou = { name: "", relationship: null, otherRelationship: "", context: "" };

const Context = createContext<VisitorFlow | null>(null);

export function VisitorFlowProvider({ children }: { children: ReactNode }) {
  // Resolved once, so a ?for= link keeps working after the flow's own navigation drops the query.
  const [glassesUserName] = useState(() => resolveGlassesUserName());
  const [preview] = useState(previewEnabled);
  const [consent, setConsent] = useState(preview);
  const [photos, setPhotosState] = useState<CapturedPhoto[]>(() => (preview ? samplePhotos() : []));
  const [voice, setVoiceState] = useState<Recording | null>(() => (preview ? sampleRecording() : null));
  const [about, setAbout] = useState<AboutYou>(EMPTY_ABOUT);
  const [submitted, setSubmitted] = useState<Submitted | null>(null);

  const setPhotos = useCallback((next: CapturedPhoto[]) => {
    setPhotosState((previous) => {
      for (const p of previous) if (!next.includes(p)) URL.revokeObjectURL(p.url);
      return next;
    });
  }, []);

  const setVoice = useCallback((next: Recording | null) => {
    setVoiceState((previous) => {
      if (previous && previous !== next) URL.revokeObjectURL(previous.url);
      return next;
    });
  }, []);

  // Leaving the flow frees the photos and the recording. Deferred, because StrictMode's test
  // unmount is followed by a remount that keeps the same state (and so the same URLs).
  const latest = useRef({ photos, voice, submitted });
  latest.current = { photos, voice, submitted };
  const pendingRelease = useRef(0);
  useEffect(() => {
    window.clearTimeout(pendingRelease.current); // remounted: keep everything
    return () => {
      pendingRelease.current = window.setTimeout(() => {
        const { photos, voice, submitted } = latest.current;
        for (const p of photos) URL.revokeObjectURL(p.url);
        if (voice) URL.revokeObjectURL(voice.url);
        if (submitted?.photoUrl) URL.revokeObjectURL(submitted.photoUrl);
      });
    };
  }, []);

  const reset = useCallback(() => {
    setConsent(false);
    setPhotos([]);
    setVoice(null);
    setAbout(EMPTY_ABOUT);
  }, [setPhotos, setVoice]);

  const value = useMemo(
    () => ({ glassesUserName, consent, setConsent, photos, setPhotos, voice, setVoice, about, setAbout, submitted, setSubmitted, reset }),
    [glassesUserName, consent, photos, setPhotos, voice, setVoice, about, submitted, reset],
  );
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useVisitorFlow(): VisitorFlow {
  const flow = useContext(Context);
  if (!flow) throw new Error("useVisitorFlow must be used inside VisitorFlowProvider");
  return flow;
}

/** The relationship the API gets: the chip in lower case ("granddaughter"), or the typed "Other". */
export function relationshipFor(about: AboutYou): string {
  if (about.relationship === "Other") return about.otherRelationship.trim();
  return (about.relationship ?? "").toLowerCase();
}
