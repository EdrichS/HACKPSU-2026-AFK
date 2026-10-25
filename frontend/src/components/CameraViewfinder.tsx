import { useEffect, type RefObject } from "react";

import type { CameraStatus } from "../lib/useCamera";
import styles from "./CameraViewfinder.module.css";
import { Icon } from "./Icon";

/** What the leading badge holds: the design's check, a countdown number, or an undesigned state. */
export type ChipBadge = "check" | "loading" | "alert" | number;

interface CameraViewfinderProps {
  status: CameraStatus;
  stream: MediaStream | null;
  /** The screen reads frames from this element to take the photos. */
  videoRef: RefObject<HTMLVideoElement | null>;
  /** Fires once frames are actually showing, which is later than the stream arriving. */
  onPlaying?: () => void;
  chip: { badge: ChipBadge; text: string };
}

// Not designed: what the viewfinder shows when there is no camera feed.
const PROBLEMS: Partial<Record<CameraStatus, { title: string; body: string }>> = {
  denied: { title: "Camera access is blocked", body: "Allow camera access in your browser's site settings, then press Retry." },
  unavailable: { title: "We couldn't find a camera", body: "Connect a camera, then press Retry." },
  insecure: { title: "The camera needs a secure connection", body: "Open this page over HTTPS or on localhost." },
  error: { title: "The camera didn't start", body: "Press Retry to try again." },
};

/** The camera feed, mirrored like a selfie preview, with the face oval and a status chip. */
export function CameraViewfinder({ status, stream, videoRef, onPlaying, chip }: CameraViewfinderProps) {
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.srcObject = stream;
    // autoPlay covers most browsers; the explicit play() is for those that wait for one.
    if (stream) video.play().catch(() => undefined);
  }, [stream, videoRef]);

  const problem = PROBLEMS[status];

  return (
    <div className={styles.viewfinder}>
      <video ref={videoRef} className={styles.video} autoPlay muted playsInline aria-label="Camera preview" onPlaying={onPlaying} />
      {problem ? (
        <div className={styles.problem} role="alert">
          <Icon name="alert-circle" size={28} className={styles.problemIcon} />
          <p className={styles.problemTitle}>{problem.title}</p>
          <p className={styles.problemBody}>{problem.body}</p>
        </div>
      ) : (
        <>
          <div className={styles.oval} aria-hidden="true" />
          <div className={styles.chip} role="status">
            {/* aria-hidden so the countdown digits aren't read out every second; the text carries the meaning. */}
            <span className={styles.badge} aria-hidden="true">
              <Badge badge={chip.badge} />
            </span>
            <span className={styles.chipText}>{chip.text}</span>
          </div>
        </>
      )}
    </div>
  );
}

function Badge({ badge }: { badge: ChipBadge }) {
  if (typeof badge === "number") return <span className={styles.count}>{badge}</span>;
  if (badge === "loading") return <Icon name="loader" size={13} strokeWidth={3} className={styles.spinner} />;
  if (badge === "alert") return <Icon name="alert-circle" size={14} strokeWidth={2.5} />;
  return <Icon name="check" size={13} strokeWidth={3} />;
}
