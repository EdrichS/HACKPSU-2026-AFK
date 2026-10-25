// TypeScript mirror of contract/setup_api.py, contract/live.py and contract/embedders.py.
// Keep the field names identical; when the Python models change, change these.

export interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}

// Setup routes (contract/setup_api.py)

export interface Person {
  id: number;
  name: string;
  relationship: string;
  face_count: number;
  has_voice: boolean;
  small_context: string;
}

export interface PersonIn {
  name: string; // 1 to 80 characters
  relationship: string; // 1 to 40 characters
}

export const PERSON_NAME_MAX = 80;
export const PERSON_RELATIONSHIP_MAX = 40;

export interface DetectedFace {
  face_id: number;
  box: Box;
  person_id: number | null;
}

export interface PhotoOut {
  photo_id: number;
  width: number;
  height: number;
  faces: DetectedFace[];
}

export interface VoiceOut {
  voice_sample_id: number;
}

// Live socket (contract/live.py). Client to server:

export interface FrameMessage {
  type: "frame";
  ts: number; // milliseconds since the epoch
  jpeg: string; // base64
}

export interface AudioMessage {
  type: "audio";
  ts: number;
  wav: string; // base64, 16 kHz mono 16-bit WAV
}

export interface WhoMessage {
  type: "who";
}

export type ClientMessage = FrameMessage | AudioMessage | WhoMessage;

// Server to client:

export interface PresentPerson {
  person_id: number;
  name: string;
  relationship: string;
  small_context: string;
}

export interface TrackedFace {
  box: Box;
  state: "named" | "unsure" | "unknown";
  person_id: number | null;
}

export interface PresentMessage {
  type: "present";
  people: PresentPerson[];
  faces: TrackedFace[];
}

export interface ArrivedMessage {
  type: "arrived";
  person: PresentPerson;
  via: "face" | "voice";
  text: string;
}

export interface UnknownMessage {
  type: "unknown";
  text: string;
}

export interface WhoAnswerMessage {
  type: "who_answer";
  text: string;
}

export interface ErrorMessage {
  type: "error";
  message: string;
}

/**
 * PROPOSED, not in contract/live.py yet. The HUD caption bar needs a transcript line and the
 * speaker voice recognition picked; nothing on the server sends this today, so the bar stays
 * hidden until it does. See report.txt.
 */
export interface CaptionMessage {
  type: "caption";
  speaker: string | null; // the recognized person's name; null for an unknown speaker
  person_id: number | null;
  text: string; // the line so far
  final: boolean; // false while the last word is still being transcribed
}

export type ServerMessage =
  | PresentMessage
  | ArrivedMessage
  | UnknownMessage
  | WhoAnswerMessage
  | ErrorMessage
  | CaptionMessage;
