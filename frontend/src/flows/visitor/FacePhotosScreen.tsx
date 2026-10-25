import { useEffect, useEffectEvent, useRef, useState } from "react";
import { useNavigate } from "react-router";

import { Button } from "../../components/Button";
import { CameraViewfinder, type ChipBadge } from "../../components/CameraViewfinder";
import { ActionBar, PageShell, TitleBlock } from "../../components/PageShell";
import { PhotoStrip } from "../../components/PhotoStrip";
import { useCamera } from "../../lib/useCamera";
import styles from "./FacePhotosScreen.module.css";
import { POSES, useVisitorFlow, type CapturedPhoto, type Pose } from "./state";

// The capturing state isn't designed: each pose gets its instruction and a 3, 2, 1 countdown.
const COUNT_FROM = 3;
const COUNT_MS = 1000;
/** How long "n of 5 photos taken" shows before the next pose's countdown. */
const BETWEEN_MS = 700;
const DARK_MS = 1500;
/** Mean luma (0 to 255) under which a frame counts as too dark. */
const DARK_LUMA = 45;

type Step =
  | { kind: "countdown"; pose: Pose; count: number }
  | { kind: "dark"; pose: Pose }
  | { kind: "failed" }
  /** Nothing in progress: the chip shows how many photos are taken. */
  | null;

/** Mean luma of the current frame, from a 32 × 24 copy: cheap enough to run before every photo. */
function meanLuma(video: HTMLVideoElement): number | null {
  try {
    const canvas = document.createElement("canvas");
    canvas.width = 32;
    canvas.height = 24;
    const context = canvas.getContext("2d", { willReadFrequently: true });
    if (!context) return null;
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    const { data } = context.getImageData(0, 0, canvas.width, canvas.height);
    let sum = 0;
    for (let i = 0; i < data.length; i += 4) sum += 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
    return sum / (data.length / 4);
  } catch {
    return null;
  }
}

/** The current frame as a JPEG, unmirrored, at the camera's own resolution. */
async function grabFrame(video: HTMLVideoElement): Promise<{ blob: Blob; width: number; height: number } | null> {
  const width = video.videoWidth;
  const height = video.videoHeight;
  if (!width || !height) return null;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) return null;
  context.drawImage(video, 0, 0, width, height);
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.92));
  return blob ? { blob, width, height } : null;
}

export function FacePhotosScreen() {
  const { photos, setPhotos } = useVisitorFlow();
  const navigate = useNavigate();
  const camera = useCamera();
  const videoRef = useRef<HTMLVideoElement>(null);
  // The stream the <video> is actually showing frames from; a new stream isn't live until it plays.
  const [playing, setPlaying] = useState<MediaStream | null>(null);
  const [step, setStep] = useState<Step>(null);
  const [run, setRun] = useState(0);
  const live = camera.status === "ready" && camera.stream !== null && playing === camera.stream;

  // Read once when a run starts. Not a dependency: every photo taken changes `photos`.
  const photosSoFar = useEffectEvent(() => photos);

  useEffect(() => {
    const video = videoRef.current;
    if (!live || !video) return;
    let cancelled = false;
    const timers = new Set<number>();
    const wait = (ms: number) =>
      new Promise<void>((resolve) => {
        const id = window.setTimeout(() => {
          timers.delete(id);
          resolve();
        }, ms);
        timers.add(id);
      });

    async function sequence(video: HTMLVideoElement) {
      let taken = photosSoFar();
      let first = true;
      // Only the poses still missing, so a visitor who left mid-way carries on, and one who
      // comes back with all five isn't made to start again.
      for (const { pose } of POSES) {
        if (taken.some((p) => p.pose === pose)) continue;
        if (!first) {
          await wait(BETWEEN_MS);
          if (cancelled) return;
        }
        first = false;
        for (let count = COUNT_FROM; count > 0; count--) {
          setStep({ kind: "countdown", pose, count });
          await wait(COUNT_MS);
          if (cancelled) return;
        }
        const luma = meanLuma(video);
        if (luma !== null && luma < DARK_LUMA) {
          // A hint, not a gate: the photo is taken anyway, and Upload says so if no photo has a face.
          setStep({ kind: "dark", pose });
          await wait(DARK_MS);
          if (cancelled) return;
        }
        const frame = await grabFrame(video);
        if (cancelled) return;
        if (!frame) {
          setStep({ kind: "failed" });
          return;
        }
        const photo: CapturedPhoto = { pose, ...frame, url: URL.createObjectURL(frame.blob) };
        taken = [...taken, photo];
        setPhotos(taken);
        setStep(null);
      }
    }

    sequence(video).catch(() => {
      if (!cancelled) setStep({ kind: "failed" });
    });
    return () => {
      cancelled = true;
      for (const id of timers) window.clearTimeout(id);
      setStep(null);
    };
  }, [live, run, setPhotos]);

  const retake = () => {
    setPhotos([]);
    setStep(null);
    if (camera.status === "ready" || camera.status === "starting") setRun((n) => n + 1);
    else camera.retry(); // blocked, missing or stopped: ask again; the run starts once it plays
  };

  let chip: { badge: ChipBadge; text: string };
  if (!live) chip = { badge: "loading", text: "Starting camera…" };
  else if (step?.kind === "countdown") chip = { badge: step.count, text: POSES.find((p) => p.pose === step.pose)!.instruction };
  else if (step?.kind === "dark") chip = { badge: "alert", text: "It's a bit dark. Try facing a light." };
  else if (step?.kind === "failed") chip = { badge: "alert", text: "We couldn't take a photo. Press Retry." };
  else chip = { badge: "check", text: `${photos.length} of ${POSES.length} photos taken` };

  const active = live && step && step.kind !== "failed" ? step.pose : null;
  const shots = POSES.map(({ pose, label }) => ({ id: pose, label, url: photos.find((p) => p.pose === pose)?.url ?? null }));

  return (
    <PageShell
      title="Face photos"
      step={{ current: 2, total: 4 }}
      footer={
        <ActionBar>
          <Button variant="secondary" icon="rotate-ccw" onClick={retake}>
            Retry
          </Button>
          {/* Disabled until all five are taken: the handoff's suggestion; the state isn't designed. */}
          <Button icon="arrow-right" iconAfter disabled={photos.length < POSES.length} onClick={() => navigate("/visitor/voice")}>
            Continue
          </Button>
        </ActionBar>
      }
    >
      <main className={styles.main}>
        <div className={styles.text}>
          <TitleBlock
            title="Take a few photos"
            lead="Keep your face inside the oval and look at the camera. We'll take five photos as you turn your head a little."
          />
        </div>
        <div className={styles.camera}>
          <CameraViewfinder
            status={camera.status}
            stream={camera.stream}
            videoRef={videoRef}
            onPlaying={() => setPlaying(camera.stream)}
            chip={chip}
          />
          <PhotoStrip shots={shots} active={active} />
        </div>
      </main>
    </PageShell>
  );
}
