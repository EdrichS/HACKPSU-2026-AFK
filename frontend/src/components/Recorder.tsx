import { useLayoutEffect, useRef, useState, type RefObject } from "react";

import { formatDuration } from "../lib/recording";
import { WAVE_BARS, type RecorderControls, type RecorderStatus } from "../lib/useRecorder";
import { Icon, type IconName } from "./Icon";
import { Notice } from "./PageShell";
import styles from "./Recorder.module.css";

const BAR_MIN_WIDTH = 2;
const BAR_GAP = 3;
const FLAT_HEIGHT = 10; // % of 40px: the idle bars, and the floor while recording
const PEAK_FLOOR = 12; // % of 40px: silence in a recording still shows a bar

const LABELS: Record<RecorderStatus, string> = {
  idle: "Ready",
  requesting: "Starting…",
  recording: "Recording",
  recorded: "Recorded",
  too_short: "Too short",
  denied: "Mic blocked",
  insecure: "Mic unavailable",
  error: "Mic unavailable",
};

/**
 * The undesigned states' messages, under the bar. The Recorder keeps their live region mounted,
 * so each message is announced when it appears; a region inserted with its text often isn't.
 */
function Message({ status }: { status: RecorderStatus }) {
  switch (status) {
    case "too_short":
      return <Notice tone="info" live={false}>That was a bit short. Read the whole paragraph, then press stop.</Notice>;
    case "denied":
      return <Notice live={false}>Microphone access is blocked. Allow it in your browser's site settings, then press Retry.</Notice>;
    case "insecure":
      return <Notice live={false}>The microphone needs a secure connection. Open this page over HTTPS or on localhost.</Notice>;
    case "error":
      return <Notice live={false}>The microphone didn't start. Press Retry to try again.</Notice>;
    default:
      return null;
  }
}

/** The mockups draw 56 bars; a phone fits fewer at the 2px minimum, so draw as many as fit. */
function useBarCount(ref: RefObject<HTMLDivElement | null>): number {
  const [count, setCount] = useState(WAVE_BARS);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => {
      const fit = Math.floor((el.clientWidth + BAR_GAP) / (BAR_MIN_WIDTH + BAR_GAP));
      setCount(Math.max(8, Math.min(WAVE_BARS, fit)));
    };
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [ref]);
  return count;
}

/** Fewer bars than values: each bar keeps the loudest value in its slice. */
function fitTo(values: number[], count: number): number[] {
  if (values.length <= count) return values;
  return Array.from({ length: count }, (_, i) => {
    const from = Math.floor((i * values.length) / count);
    const to = Math.max(from + 1, Math.floor(((i + 1) * values.length) / count));
    return Math.max(...values.slice(from, to));
  });
}

export function Recorder({ recorder }: { recorder: RecorderControls }) {
  const { status, recording, elapsed, history, playing, progress } = recorder;
  const wave = useRef<HTMLDivElement>(null);
  const count = useBarCount(wave);

  const recorded = status === "recorded" && recording !== null;
  let heights: number[];
  if (status === "recording") heights = history.slice(-count).map((l) => Math.max(FLAT_HEIGHT, l * 100));
  else if (recorded) heights = fitTo(recording.peaks, count).map((p) => Math.max(PEAK_FLOOR, p * 100));
  else heights = Array(count).fill(FLAT_HEIGHT);
  const flat = status !== "recording" && !recorded;
  // Bars past the playhead dim while playing, and stay that way while paused part-way.
  const playhead = recorded && (playing || progress > 0) ? progress * heights.length : null;

  let icon: IconName = "mic";
  let label = "Start recording";
  let onClick: (() => void) | undefined = () => void recorder.start();
  if (status === "recording") {
    icon = "stop";
    label = "Stop recording";
    onClick = () => void recorder.stop();
  } else if (recorded) {
    icon = playing ? "pause" : "play";
    label = playing ? "Pause your recording" : "Play your recording";
    onClick = recorder.togglePlay;
  } else if (status === "requesting" || status === "insecure") {
    // aria-disabled rather than disabled, so a keyboard user's focus stays on the button.
    onClick = undefined;
  }

  const seconds = status === "recording" || status === "too_short" ? elapsed : recorded ? recording.seconds : 0;
  const stateLabel = recorded && playing ? "Playing" : LABELS[status];

  return (
    <div className={styles.recorder}>
      <div className={styles.panel}>
        <button
          ref={recorder.buttonRef}
          type="button"
          className={styles.control}
          aria-label={label}
          aria-disabled={onClick ? undefined : true}
          onClick={onClick}
        >
          <Icon name={icon} size={20} />
        </button>
        <div ref={wave} className={styles.wave} aria-hidden="true">
          {heights.map((h, i) => (
            <span
              key={i}
              className={flat ? `${styles.waveBar} ${styles.flat}` : playhead !== null && i >= playhead ? `${styles.waveBar} ${styles.ahead}` : styles.waveBar}
              style={{ height: `${h}%` }}
            />
          ))}
        </div>
        <div className={styles.meta}>
          <span className={styles.duration}>{formatDuration(seconds)}</span>
          <span className={styles.state} aria-live="polite">
            {stateLabel}
          </span>
        </div>
      </div>
      <div aria-live="polite" className={styles.messages}>
        <Message status={status} />
      </div>
    </div>
  );
}
