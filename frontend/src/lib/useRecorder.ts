// The Recorder's state machine: microphone -> raw samples -> a contract WAV (16 kHz mono 16-bit),
// plus playback of the result. Only "recorded" is designed; the other states are HANDOFF.md's
// undesigned Recorder row.

import { useEffect, useRef, useState, type RefObject } from "react";

import { MIC_CONSTRAINTS, levels, startPcmCapture, type PcmCapture } from "./pcmCapture";
import { MAX_RECORDING_SECONDS, MIN_RECORDING_SECONDS, type Recording } from "./recording";
import { TARGET_RATE, concat, encodeWav, peaks, resampleTo16k } from "./wav";

export type RecorderStatus = "idle" | "requesting" | "recording" | "recorded" | "too_short" | "denied" | "insecure" | "error";

/** Waveform bars at full width, as in the mockups. Recording.peaks has one value per bar. */
export const WAVE_BARS = 56;
const LEVEL_INTERVAL_MS = 80;
const SILENT_HISTORY: number[] = Array(WAVE_BARS).fill(0);

export interface RecorderControls {
  status: RecorderStatus;
  /** The finished recording, while status is "recorded". */
  recording: Recording | null;
  /** Seconds recorded so far, or the length of an attempt that was too short. */
  elapsed: number;
  /** Live levels, 0 to 1, oldest first, while recording. */
  history: number[];
  playing: boolean;
  /** Playback position, 0 to 1. */
  progress: number;
  /** A valid recording exists (Continue / Upload). */
  ready: boolean;
  /** Something was attempted, so "record again" makes sense. */
  canRetry: boolean;
  start: () => Promise<void>;
  stop: () => Promise<void>;
  togglePlay: () => void;
  /** Discard and record again, with focus on the Recorder's button so it isn't lost. */
  retry: () => void;
  /** The recording, now owned by the caller (the flow state revokes its URL from here on). */
  handOff: () => Recording | null;
  buttonRef: RefObject<HTMLButtonElement | null>;
}

interface Session {
  cancelled: boolean;
  stream: MediaStream | null;
  capture: PcmCapture | null;
  chunks: Float32Array[];
  timer: number | undefined;
  startedAt: number;
}

function micAvailable(): boolean {
  // mediaDevices only exists in a secure context (HTTPS or localhost).
  return typeof navigator !== "undefined" && typeof navigator.mediaDevices?.getUserMedia === "function";
}

function isDenied(error: unknown): boolean {
  return error instanceof DOMException && (error.name === "NotAllowedError" || error.name === "PermissionDeniedError");
}

/** Safe to call more than once: each resource is let go of exactly once. */
function release(s: Session) {
  s.cancelled = true;
  window.clearInterval(s.timer);
  s.timer = undefined;
  s.capture?.stop();
  s.capture = null;
  s.stream?.getTracks().forEach((track) => track.stop());
  s.stream = null;
}

/** `initial` is the flow's recording when the person comes back to the step; the flow owns it. */
export function useRecorder(initial: Recording | null = null): RecorderControls {
  const [status, setStatus] = useState<RecorderStatus>(() => (initial ? "recorded" : micAvailable() ? "idle" : "insecure"));
  const [recording, setRecordingState] = useState<Recording | null>(initial);
  const [elapsed, setElapsed] = useState(0);
  const [history, setHistory] = useState<number[]>(SILENT_HISTORY);
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(0);

  const session = useRef<Session | null>(null);
  const current = useRef<Recording | null>(initial);
  // A recording this hook made and hasn't handed off yet: its URL is ours to revoke.
  const owned = useRef<Recording | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);
  const frame = useRef<number | undefined>(undefined);
  const mounted = useRef(false);
  const buttonRef = useRef<HTMLButtonElement | null>(null);

  const setRecording = (next: Recording | null) => {
    current.current = next;
    setRecordingState(next);
  };

  const stopFrames = () => {
    if (frame.current !== undefined) cancelAnimationFrame(frame.current);
    frame.current = undefined;
  };

  const dropAudio = () => {
    stopFrames();
    const a = audio.current;
    audio.current = null;
    if (a) {
      a.onplay = a.onpause = a.onended = a.onerror = null;
      a.pause();
      a.removeAttribute("src");
      a.load(); // lets go of the blob; the URL itself stays valid for whoever owns it
    }
  };

  const discardCurrent = () => {
    const rec = current.current;
    if (rec && rec === owned.current) {
      URL.revokeObjectURL(rec.url);
      owned.current = null;
    }
    setRecording(null);
  };

  const stop = async () => {
    const s = session.current;
    if (!s || !s.capture) return; // nothing to stop yet (still asking for the mic)
    session.current = null;
    const rate = s.capture.sampleRate;
    const wall = (performance.now() - s.startedAt) / 1000;
    release(s);
    const samples = concat(s.chunks);
    const seconds = samples.length / rate;
    setElapsed(seconds);
    setHistory(SILENT_HISTORY);
    if (seconds < MIN_RECORDING_SECONDS) {
      // Samples trail the clock by a buffer or so; far fewer than the clock says means the mic
      // wasn't delivering audio at all, not that the attempt was short.
      setStatus(wall >= MIN_RECORDING_SECONDS && seconds < Math.min(1, wall / 2) ? "error" : "too_short");
      return;
    }
    try {
      const samples16k = await resampleTo16k(samples, rate);
      if (!mounted.current) return;
      const wav = new Blob([encodeWav(samples16k, TARGET_RATE)], { type: "audio/wav" });
      const rec: Recording = {
        wav,
        seconds: samples16k.length / TARGET_RATE,
        peaks: peaks(samples16k, WAVE_BARS),
        url: URL.createObjectURL(wav),
      };
      owned.current = rec;
      setRecording(rec);
      setElapsed(rec.seconds);
      setStatus("recorded");
    } catch {
      if (mounted.current) setStatus("error");
    }
  };

  const tick = (s: Session) => {
    if (session.current !== s || !s.capture) return;
    const seconds = (performance.now() - s.startedAt) / 1000;
    setElapsed(seconds);
    const level = levels(s.capture.analyser, 1)[0] ?? 0;
    setHistory((h) => [...h.slice(1 - WAVE_BARS), level]);
    if (seconds >= MAX_RECORDING_SECONDS) void stop();
  };

  const start = async () => {
    if (session.current) return; // already asking or recording
    if (!micAvailable()) {
      setStatus("insecure");
      return;
    }
    dropAudio();
    setPlaying(false);
    setProgress(0);
    discardCurrent();
    const s: Session = { cancelled: false, stream: null, capture: null, chunks: [], timer: undefined, startedAt: 0 };
    session.current = s;
    setElapsed(0);
    setHistory(SILENT_HISTORY);
    setStatus("requesting");
    try {
      s.stream = await navigator.mediaDevices.getUserMedia({ audio: MIC_CONSTRAINTS });
      if (s.cancelled) return void release(s);
      const capture = await startPcmCapture(s.stream, (chunk) => s.chunks.push(chunk));
      if (s.cancelled) {
        capture.stop();
        return void release(s);
      }
      s.capture = capture;
    } catch (e) {
      const cancelled = s.cancelled;
      release(s);
      if (session.current === s) session.current = null;
      if (!cancelled) setStatus(isDenied(e) ? "denied" : "error");
      return;
    }
    s.startedAt = performance.now();
    s.timer = window.setInterval(() => tick(s), LEVEL_INTERVAL_MS);
    setStatus("recording");
  };

  const togglePlay = () => {
    const rec = current.current;
    if (!rec) return;
    let a = audio.current;
    if (!a) {
      a = new Audio(rec.url);
      audio.current = a;
      const el = a;
      const total = () => (Number.isFinite(el.duration) && el.duration > 0 ? el.duration : rec.seconds);
      const follow = () => {
        setProgress(Math.min(1, el.currentTime / total()));
        frame.current = requestAnimationFrame(follow);
      };
      el.onplay = () => {
        setPlaying(true);
        stopFrames();
        follow();
      };
      el.onpause = () => {
        stopFrames();
        setPlaying(false);
        setProgress(Math.min(1, el.currentTime / total()));
      };
      el.onended = () => {
        stopFrames();
        setPlaying(false);
        setProgress(0);
      };
      el.onerror = () => {
        stopFrames();
        setPlaying(false);
      };
    }
    if (a.paused) a.play().catch(() => setPlaying(false));
    else a.pause();
  };

  const retry = () => {
    void start();
    buttonRef.current?.focus();
  };

  const handOff = () => {
    const rec = current.current;
    if (rec && rec === owned.current) owned.current = null;
    return rec;
  };

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      if (session.current) release(session.current);
      session.current = null;
      dropAudio();
      if (owned.current) URL.revokeObjectURL(owned.current.url);
      owned.current = null;
    };
    // dropAudio only touches refs, so this is safe to mount twice (StrictMode).
  }, []);

  const ready = status === "recorded" && recording !== null;
  const canRetry = status === "recorded" || status === "too_short" || status === "denied" || status === "error";

  return { status, recording, elapsed, history, playing, progress, ready, canRetry, start, stop, togglePlay, retry, handOff, buttonRef };
}
