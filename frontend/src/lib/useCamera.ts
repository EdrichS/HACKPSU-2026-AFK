// The front camera for the Face photos step. Stops every track on unmount and on retry().

import { useCallback, useEffect, useState } from "react";

export type CameraStatus = "starting" | "ready" | "denied" | "unavailable" | "insecure" | "error";

export interface Camera {
  status: CameraStatus;
  /** Set while status is "ready"; attach it to a <video> with srcObject. */
  stream: MediaStream | null;
  /** Ask for the camera again (after it was blocked, missing or stopped). */
  retry: () => void;
}

const CONSTRAINTS: MediaStreamConstraints = {
  video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 960 } },
  audio: false,
};

function statusFor(error: unknown): CameraStatus {
  const name = (error as { name?: string } | null)?.name;
  if (name === "NotAllowedError" || name === "SecurityError") return "denied";
  if (name === "NotFoundError" || name === "OverconstrainedError") return "unavailable";
  return "error";
}

function stopTracks(stream: MediaStream) {
  for (const track of stream.getTracks()) track.stop();
}

interface CameraState {
  status: CameraStatus;
  stream: MediaStream | null;
}

const STARTING: CameraState = { status: "starting", stream: null };

export function useCamera(): Camera {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<CameraState>(STARTING);

  useEffect(() => {
    // getUserMedia only exists in a secure context: HTTPS or localhost, not http://192.168.x.x.
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      setState({ status: "insecure", stream: null });
      return;
    }
    let cancelled = false;
    let stream: MediaStream | null = null;
    setState(STARTING);
    navigator.mediaDevices.getUserMedia(CONSTRAINTS).then(
      (s) => {
        // StrictMode unmounts before a slow permission prompt resolves: don't leave that camera on.
        if (cancelled) {
          stopTracks(s);
          return;
        }
        stream = s;
        // Unplugged, or permission revoked mid-way. A track we stop ourselves doesn't fire this.
        for (const track of s.getVideoTracks()) {
          track.onended = () => {
            if (!cancelled) setState({ status: "error", stream: null });
          };
        }
        setState({ status: "ready", stream: s });
      },
      (error: unknown) => {
        if (!cancelled) setState({ status: statusFor(error), stream: null });
      },
    );
    return () => {
      cancelled = true;
      if (stream) {
        for (const track of stream.getVideoTracks()) track.onended = null;
        stopTracks(stream);
      }
    };
  }, [attempt]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  return { status: state.status, stream: state.stream, retry };
}
