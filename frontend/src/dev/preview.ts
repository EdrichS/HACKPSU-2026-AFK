// Dev-only (npm run dev): add ?preview to a flow URL to start it with sample photos and a sample
// recording, so every screen can be checked without a camera or a microphone, the way
// Design/screens/index.html lets you click through the mockups. Production builds drop this.

import type { CapturedPhoto, Pose } from "../flows/visitor/state";
import type { Recording } from "../lib/recording";
import { encodeWav, peaks, TARGET_RATE } from "../lib/wav";

export function previewEnabled(): boolean {
  return import.meta.env.DEV && new URLSearchParams(location.search).has("preview");
}

function dataUrlToBlob(dataUrl: string): Blob {
  const [head, body] = dataUrl.split(",");
  const bytes = Uint8Array.from(atob(body), (c) => c.charCodeAt(0));
  return new Blob([bytes], { type: head.slice(5, head.indexOf(";")) });
}

/** The mockups' placeholder person, drawn with a slight turn for each pose. */
export function samplePhotos(): CapturedPhoto[] {
  const width = 960;
  const height = 720;
  // Type-only import above: importing POSES itself would make a cycle with state.tsx.
  const turn: Record<Pose, [number, number]> = { front: [0, 0], left: [-40, 0], right: [40, 0], up: [0, -30], down: [0, 30] };
  return (Object.keys(turn) as Pose[]).map((pose) => {
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const g = canvas.getContext("2d")!;
    const [dx, dy] = turn[pose];
    g.fillStyle = "#B9A792";
    g.fillRect(0, 0, width, height);
    g.fillStyle = "rgba(220,229,225,0.5)";
    g.fillRect(0, 60, 300, 260);
    g.fillStyle = "#7E9A82";
    g.beginPath();
    g.ellipse(width / 2, height + 120, 300, 260, 0, 0, Math.PI * 2);
    g.fill();
    g.fillStyle = "#2B1F1B";
    g.beginPath();
    g.ellipse(width / 2 + dx * 0.6, 300 + dy * 0.6, 150, 190, 0, 0, Math.PI * 2);
    g.fill();
    g.fillStyle = "#C98F6C";
    g.beginPath();
    g.ellipse(width / 2 + dx, 330 + dy, 108, 134, 0, 0, Math.PI * 2);
    g.fill();
    const blob = dataUrlToBlob(canvas.toDataURL("image/jpeg", 0.9));
    return { pose, blob, url: URL.createObjectURL(blob), width, height };
  });
}

/** 18 seconds of speech-like bursts, already a contract-format WAV. */
export function sampleRecording(): Recording {
  const seconds = 18;
  const samples = new Float32Array(seconds * TARGET_RATE);
  for (let i = 0; i < samples.length; i++) {
    const t = i / TARGET_RATE;
    const syllables = Math.max(0, Math.sin(t * 2 * Math.PI * 2.3)) * (0.5 + 0.5 * Math.sin(t * 0.9));
    samples[i] = 0.4 * syllables * Math.sin(2 * Math.PI * 180 * t);
  }
  const wav = new Blob([encodeWav(samples)], { type: "audio/wav" });
  return { wav, seconds, peaks: peaks(samples, 56), url: URL.createObjectURL(wav) };
}
