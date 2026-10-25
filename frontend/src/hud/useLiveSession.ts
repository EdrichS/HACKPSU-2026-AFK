// The live view's connection to the world: camera frames and mic audio out over /live, faces,
// people and sentences back. See contract/README.md, "/live messages".

import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from "react";

import { liveUrl } from "../api/client";
import type { PresentPerson, ServerMessage } from "../api/contract";
import { MIC_CONSTRAINTS, startPcmCapture, type PcmCapture } from "../lib/pcmCapture";
import { CONTRACT_MIN_SECONDS, concat, encodeWav, resampleTo16k, toBase64 } from "../lib/wav";
import { useCaptions, type CaptionLine } from "./captionLines";
import { frameToStage, type FrameGeometry } from "./geometry";
import { useSpeech } from "./speech";
import type { FaceSnapshot } from "./tracker";
import { useLiveSocket } from "./useLiveSocket";

const VIDEO_CONSTRAINTS: MediaTrackConstraints = { width: { ideal: 1280 }, height: { ideal: 720 } };
const FRAME_WIDTH = 640;
const JPEG_QUALITY = 0.7;
/** About 3 frames a second, one at a time: the next goes after the last one's "present". */
const FRAME_INTERVAL_MS = 333;
/** A frame unanswered this long lets one more go out, so a slow reply can't stall the loop. */
const FRAME_TIMEOUT_MS = 2000;
/** Never more than this many frames awaiting a "present", or a slow server falls ever further behind. */
const MAX_FRAMES_IN_FLIGHT = 2;
/**
 * Audio goes out as soon as a second of it is in (the contract's minimum per message): short
 * chunks keep live captions close behind the words; the server's own voice detector joins them.
 */
const AUDIO_POLL_MS = 250;

export interface LiveSession {
  started: boolean;
  /** Call from a click: speech and the camera and mic prompts need a user gesture. */
  start(): void;
  who(): void;
  connected: boolean;
  camera: boolean;
  /** The mic is on and not muted for the app's own speech. */
  voice: boolean;
  /** A transcript line has arrived at least once. */
  captions: boolean;
  faces: FaceSnapshot | null;
  /** present.people from the latest frame. */
  people: PresentPerson[];
  /** Everyone seen this session, latest details: a face held between frames keeps its tags. */
  directory: ReadonlyMap<number, PresentPerson>;
  voicePersonId: number | null;
  caption: CaptionLine | null;
}

async function ask(constraints: MediaStreamConstraints): Promise<MediaStream | null> {
  try {
    return await navigator.mediaDevices.getUserMedia(constraints);
  } catch (error) {
    console.warn("Name Tags live:", constraints.video ? "no camera" : "no microphone", error);
    return null;
  }
}

/** Camera and mic together (one prompt); if that fails, each alone, so one refusal keeps the other. */
async function requestDevices(): Promise<{ camera: MediaStream | null; mic: MediaStream | null }> {
  if (!navigator.mediaDevices?.getUserMedia) {
    console.warn("Name Tags live: the camera and microphone need https or localhost.");
    return { camera: null, mic: null };
  }
  const both = await ask({ video: VIDEO_CONSTRAINTS, audio: MIC_CONSTRAINTS });
  if (both) return { camera: new MediaStream(both.getVideoTracks()), mic: new MediaStream(both.getAudioTracks()) };
  const camera = await ask({ video: VIDEO_CONSTRAINTS });
  const mic = await ask({ audio: MIC_CONSTRAINTS });
  return { camera, mic };
}

function stopStream(stream: MediaStream | null) {
  stream?.getTracks().forEach((track) => track.stop());
}

/** Stops the stream's tracks when it's replaced or the view unmounts; clears it if a device goes away. */
function useStreamLifetime(stream: MediaStream | null, clear: () => void) {
  useEffect(() => {
    if (!stream) return;
    const tracks = stream.getTracks();
    tracks.forEach((track) => track.addEventListener("ended", clear));
    return () => {
      tracks.forEach((track) => track.removeEventListener("ended", clear));
      stopStream(stream);
    };
  }, [stream, clear]);
}

export function useLiveSession(videoRef: RefObject<HTMLVideoElement | null>, mirror: boolean): LiveSession {
  const [started, setStarted] = useState(false);
  const [camera, setCamera] = useState<MediaStream | null>(null);
  const [mic, setMic] = useState<MediaStream | null>(null);
  const [faces, setFaces] = useState<FaceSnapshot | null>(null);
  const [people, setPeople] = useState<PresentPerson[]>([]);
  const [directory, setDirectory] = useState<ReadonlyMap<number, PresentPerson>>(() => new Map());
  const [voicePersonId, setVoicePersonId] = useState<number | null>(null);
  const [captionsHeard, setCaptionsHeard] = useState(false);

  const captions = useCaptions();
  const { heard, spokenStart, spokenEnd } = captions;
  const { speaking, speak, unlock, isMuted } = useSpeech({ onStart: spokenStart, onEnd: spokenEnd });

  const alive = useRef(true);
  const startedOnce = useRef(false);
  const mirrorRef = useRef(mirror);
  /**
   * Frames awaiting their "present", oldest first. The server answers every frame, in order, so
   * each present's boxes are in the pixels of the frame at the head of this queue.
   */
  const inFlight = useRef<(FrameGeometry & { sentAt: number })[]>([]);
  const lastGeometry = useRef<FrameGeometry | null>(null);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  useEffect(() => {
    mirrorRef.current = mirror;
  }, [mirror]);

  const clearCamera = useCallback(() => setCamera(null), []);
  const clearMic = useCallback(() => setMic(null), []);
  useStreamLifetime(camera, clearCamera);
  useStreamLifetime(mic, clearMic);

  const remember = useCallback((list: PresentPerson[]) => {
    setDirectory((previous) => {
      const next = new Map(previous);
      for (const person of list) next.set(person.person_id, person);
      return next;
    });
  }, []);

  // The backend composes every sentence; it's spoken exactly as received and shown on screen.
  const say = useCallback(
    (text: string) => {
      if (!speak(text)) spokenEnd(text);
    },
    [speak, spokenEnd],
  );

  const onMessage = useCallback(
    (message: ServerMessage) => {
      switch (message.type) {
        case "present": {
          const geometry = inFlight.current.shift() ?? lastGeometry.current;
          lastGeometry.current = geometry;
          // Only people the glasses know get a box and a tag; a stranger or an unsure face shows nothing.
          const stageFaces = geometry
            ? message.faces
                .filter((face) => face.state === "named" && face.person_id !== null)
                .map((face) => ({
                  box: frameToStage(face.box, geometry, mirrorRef.current),
                  state: face.state,
                  personId: face.person_id,
                }))
            : [];
          setFaces({ faces: stageFaces, at: performance.now() });
          setPeople(message.people);
          remember(message.people);
          break;
        }
        // The glasses speak only when spoken to: "Who is this?" and Nova. Arrivals update the
        // tags and the panel silently, and a stranger is never called out.
        case "arrived":
          remember([message.person]);
          if (message.via === "voice") setVoicePersonId(message.person.person_id);
          break;
        case "unknown":
          break;
        case "who_answer":
          say(message.text);
          break;
        case "caption":
          setCaptionsHeard(true);
          heard(message);
          break;
        case "answer":
          say(message.text); // Nova's reply, spoken by this device like every other sentence
          break;
        case "visit_saved":
          console.info("Name Tags live: visit saved for", message.name, message.new_facts);
          break;
        case "error":
          console.warn("Name Tags live:", message.message);
          break;
      }
    },
    [heard, remember, say],
  );

  const url = useMemo(() => (started ? liveUrl() : null), [started]);
  const { open, send } = useLiveSocket(url, onMessage);

  // Who's in the room is only known while connected.
  useEffect(() => {
    if (open) return;
    setPeople((previous) => (previous.length ? [] : previous));
    setVoicePersonId(null);
  }, [open]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !camera) return;
    video.srcObject = camera;
    video.play().catch(() => {
      // autoplay of a muted, inline video is allowed; a failure here means the stream went away
    });
    return () => {
      video.srcObject = null;
    };
  }, [camera, videoRef]);

  // Frames: one in flight at a time, about 3 a second, 640px wide JPEG.
  useEffect(() => {
    if (!camera || !open) return;
    const canvas = document.createElement("canvas");
    const context = canvas.getContext("2d");
    if (!context) return;
    inFlight.current = [];
    let lastSent = 0;
    const timer = window.setInterval(() => {
      const video = videoRef.current;
      if (!video || video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA || !video.videoWidth) return;
      const now = performance.now();
      const queue = inFlight.current;
      // A frame the server answered with an error (no "present") would otherwise wait here forever.
      while (queue.length > 0 && now - queue[0].sentAt >= FRAME_TIMEOUT_MS) queue.shift();
      if (queue.length >= MAX_FRAMES_IN_FLIGHT) return;
      if (now - lastSent < FRAME_INTERVAL_MS) return;
      const geometry: FrameGeometry = {
        frameWidth: FRAME_WIDTH,
        frameHeight: Math.round((FRAME_WIDTH * video.videoHeight) / video.videoWidth),
        videoWidth: video.videoWidth,
        videoHeight: video.videoHeight,
      };
      canvas.width = geometry.frameWidth;
      canvas.height = geometry.frameHeight;
      context.drawImage(video, 0, 0, canvas.width, canvas.height);
      const dataUrl = canvas.toDataURL("image/jpeg", JPEG_QUALITY);
      const jpeg = dataUrl.slice(dataUrl.indexOf(",") + 1);
      if (send({ type: "frame", ts: Date.now(), jpeg })) {
        queue.push({ ...geometry, sentAt: now });
        lastSent = now;
      }
    }, 50);
    return () => window.clearInterval(timer);
  }, [camera, open, send, videoRef]);

  // Audio: chunks of about 1 s of 16 kHz WAV. While the app speaks the samples are dropped, which
  // is how the contract mutes the mic.
  useEffect(() => {
    if (!mic) return;
    let capture: PcmCapture | null = null;
    let stopped = false;
    let chunks: Float32Array[] = [];
    let chunkStart = 0;

    startPcmCapture(mic, (samples) => {
      if (isMuted()) {
        chunks = []; // keep each chunk one unbroken stretch of the room
        return;
      }
      if (chunks.length === 0) chunkStart = Date.now();
      chunks.push(samples);
    }).then(
      (running) => {
        if (stopped) running.stop();
        else capture = running;
      },
      (error) => {
        console.warn("Name Tags live: can't read the microphone", error);
        if (!stopped) setMic(null);
      },
    );

    const timer = window.setInterval(() => {
      if (!capture || chunks.length === 0) return;
      const rate = capture.sampleRate;
      const samples = concat(chunks);
      if (samples.length < rate * CONTRACT_MIN_SECONDS) {
        chunks = [samples]; // under the contract's 1 s: keep collecting
        return;
      }
      chunks = [];
      const ts = chunkStart;
      void resampleTo16k(samples, rate).then((pcm) => {
        if (!stopped) send({ type: "audio", ts, wav: toBase64(encodeWav(pcm)) });
      });
    }, AUDIO_POLL_MS);

    return () => {
      stopped = true;
      window.clearInterval(timer);
      capture?.stop();
    };
  }, [mic, isMuted, send]);

  const start = useCallback(() => {
    if (startedOnce.current) return;
    startedOnce.current = true;
    unlock(); // must run inside the click, before any await
    setStarted(true);
    void requestDevices().then((devices) => {
      if (!alive.current) {
        stopStream(devices.camera);
        stopStream(devices.mic);
        return;
      }
      setCamera(devices.camera);
      setMic(devices.mic);
    });
  }, [unlock]);

  const who = useCallback(() => {
    send({ type: "who" });
  }, [send]);

  return {
    started,
    start,
    who,
    connected: open,
    camera: camera !== null,
    voice: mic !== null && !speaking,
    captions: captionsHeard,
    faces,
    people,
    directory,
    voicePersonId,
    caption: captions.line,
  };
}
