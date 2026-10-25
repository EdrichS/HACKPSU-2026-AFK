// What the caption bar shows. Two sources: transcript lines from the server (the PROPOSED
// "caption" message) and the app's own spoken sentences, which must also appear on screen.

import { useEffect, useMemo, useReducer } from "react";

import type { CaptionMessage } from "../api/contract";

export interface CaptionLine {
  speaker: string;
  text: string;
  /** False while the last word is still being transcribed. */
  final: boolean;
}

/** The speaker row while the app itself is talking. */
export const APP_SPEAKER = "Name Tags";
/** Undesigned: a voice the server didn't recognize. */
export const UNKNOWN_SPEAKER = "Someone";
/** Undesigned: the bar hides this long after its line last changed (or after speech ends). */
const HOLD_MS = 6000;

interface HeldLine extends CaptionLine {
  updatedAt: number;
  /** A spoken sentence still being said; it stays up and wins over transcripts until it ends. */
  active: boolean;
}

interface State {
  heard: HeldLine | null;
  spoken: HeldLine | null;
}

type Action =
  | { type: "heard"; message: CaptionMessage; now: number }
  | { type: "spokenStart"; text: string; now: number }
  | { type: "spokenEnd"; text: string; now: number }
  | { type: "expire"; now: number };

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "heard": {
      const { speaker, text, final } = action.message;
      const line = { speaker: speaker?.trim() || UNKNOWN_SPEAKER, text, final, updatedAt: action.now, active: false };
      return { ...state, heard: line };
    }
    case "spokenStart":
      return { ...state, spoken: { speaker: APP_SPEAKER, text: action.text, final: true, updatedAt: action.now, active: true } };
    case "spokenEnd":
      // Also used when there's no voice to speak with: the sentence is shown for the usual time.
      if (state.spoken?.active && state.spoken.text !== action.text) return state;
      return { ...state, spoken: { speaker: APP_SPEAKER, text: action.text, final: true, updatedAt: action.now, active: false } };
    case "expire": {
      // A little slack: a timer that fires a few ms early must still expire the line.
      const stale = (line: HeldLine | null) => line !== null && !line.active && line.updatedAt + HOLD_MS <= action.now + 50;
      if (!stale(state.heard) && !stale(state.spoken)) return state;
      return { heard: stale(state.heard) ? null : state.heard, spoken: stale(state.spoken) ? null : state.spoken };
    }
  }
}

function visible({ heard, spoken }: State): CaptionLine | null {
  if (spoken?.active) return spoken;
  if (heard && spoken) return heard.updatedAt >= spoken.updatedAt ? heard : spoken;
  return heard ?? spoken;
}

export function useCaptions() {
  const [state, dispatch] = useReducer(reducer, { heard: null, spoken: null });

  useEffect(() => {
    const deadlines = [state.heard, state.spoken]
      .filter((line): line is HeldLine => line !== null && !line.active)
      .map((line) => line.updatedAt + HOLD_MS);
    if (deadlines.length === 0) return;
    const wait = Math.max(0, Math.min(...deadlines) - performance.now());
    const timer = window.setTimeout(() => dispatch({ type: "expire", now: performance.now() }), wait);
    return () => window.clearTimeout(timer);
  }, [state]);

  const line = useMemo(() => visible(state), [state]);
  const actions = useMemo(
    () => ({
      heard: (message: CaptionMessage) => dispatch({ type: "heard", message, now: performance.now() }),
      spokenStart: (text: string) => dispatch({ type: "spokenStart", text, now: performance.now() }),
      spokenEnd: (text: string) => dispatch({ type: "spokenEnd", text, now: performance.now() }),
    }),
    [],
  );
  return { line, ...actions };
}
