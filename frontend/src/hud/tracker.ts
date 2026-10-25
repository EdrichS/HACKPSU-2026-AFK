// Face tracks across /live "present" messages. Boxes arrive about 3 times a second; tags follow
// them every animation frame, easing toward the latest box so they don't jitter.

import { useEffect, useRef, useState } from "react";

import type { Box, TrackedFace } from "../api/contract";

/** A detected face in stage px. */
export interface StageFace {
  box: Box;
  state: TrackedFace["state"];
  personId: number | null;
}

export interface FaceSnapshot {
  faces: StageFace[];
  /** performance.now() when the boxes arrived. */
  at: number;
}

interface Track {
  key: number;
  personId: number | null;
  state: TrackedFace["state"];
  target: Box;
  current: Box;
  lastSeen: number;
  /** Snapshots in a row this track was missing from. */
  missed: number;
}

/** What gets drawn: a track's smoothed box. */
export interface TrackView {
  key: number;
  personId: number | null;
  state: TrackedFace["state"];
  box: Box;
}

/** An unnamed face continues a track whose center is within this many face widths. */
const MATCH_DISTANCE = 0.6;
/** A face missing from this many snapshots in a row is gone (about 0.7 s at 3 a second). */
const MAX_MISSED = 2;
/** If snapshots stop coming at all, tracks go after this long. Above useLiveSession's frame timeout. */
const TRACK_TTL_MS = 2500;
const SMOOTHING_MS = 120;
const SIDES = ["x", "y", "width", "height"] as const;

let nextKey = 1;

function center(box: Box): [number, number] {
  return [box.x + box.width / 2, box.y + box.height / 2];
}

/** Match the new faces to tracks: the same person first, then the nearest center. */
function updateTracks(tracks: Track[], faces: StageFace[], now: number): Track[] {
  const free = new Set(tracks);
  const pairs: [StageFace, Track | undefined][] = [];
  const rest: StageFace[] = [];
  for (const face of faces) {
    const same = face.personId === null ? undefined : [...free].find((t) => t.personId === face.personId);
    if (same) {
      free.delete(same);
      pairs.push([face, same]);
    } else {
      rest.push(face);
    }
  }
  for (const face of rest) {
    const [fx, fy] = center(face.box);
    let nearest: Track | undefined;
    let nearestDistance = MATCH_DISTANCE * face.box.width;
    for (const track of free) {
      const [tx, ty] = center(track.target);
      const distance = Math.hypot(tx - fx, ty - fy);
      if (distance < nearestDistance) {
        nearest = track;
        nearestDistance = distance;
      }
    }
    if (nearest) free.delete(nearest);
    pairs.push([face, nearest]);
  }
  const seen = pairs.map(([face, track]): Track => {
    if (!track) {
      const { personId, state, box } = face;
      return { key: nextKey++, personId, state, target: { ...box }, current: { ...box }, lastSeen: now, missed: 0 };
    }
    track.personId = face.personId;
    track.state = face.state;
    track.target = { ...face.box };
    track.lastSeen = now;
    track.missed = 0;
    return track;
  });
  // Counted per snapshot, not per second: a slow server must not make every tag blink out.
  const kept = [...free].filter((track) => ++track.missed < MAX_MISSED);
  return [...seen, ...kept];
}

/** Ease every track toward its target; true if anything moved. */
function stepTracks(tracks: Track[], dt: number): boolean {
  const k = 1 - Math.exp(-dt / SMOOTHING_MS);
  let moved = false;
  for (const track of tracks) {
    for (const side of SIDES) {
      const gap = track.target[side] - track.current[side];
      if (gap === 0) continue;
      moved = true;
      track.current[side] = Math.abs(gap) < 0.05 ? track.target[side] : track.current[side] + gap * k;
    }
  }
  return moved;
}

function viewsOf(tracks: Track[]): TrackView[] {
  return tracks.map((t) => ({ key: t.key, personId: t.personId, state: t.state, box: { ...t.current } }));
}

/** The smoothed face boxes for the latest snapshot; re-renders only while something moves. */
export function useFaceTracks(snapshot: FaceSnapshot | null): TrackView[] {
  // Seeded from the first snapshot so a fixed scene (demo mode) is right on the first paint.
  const [initial] = useState(() => (snapshot ? updateTracks([], snapshot.faces, snapshot.at) : []));
  const tracks = useRef<Track[]>(initial);
  const [views, setViews] = useState<TrackView[]>(() => viewsOf(initial));

  useEffect(() => {
    if (!snapshot) return;
    tracks.current = updateTracks(tracks.current, snapshot.faces, snapshot.at);
    setViews(viewsOf(tracks.current));
  }, [snapshot]);

  useEffect(() => {
    let frame = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const count = tracks.current.length;
      tracks.current = tracks.current.filter((t) => now - t.lastSeen <= TRACK_TTL_MS);
      const moved = stepTracks(tracks.current, Math.max(0, now - last));
      last = now;
      if (moved || tracks.current.length !== count) setViews(viewsOf(tracks.current));
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, []);

  return views;
}
