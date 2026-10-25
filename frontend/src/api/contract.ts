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

export interface PersonPatch {
  name?: string;
  relationship?: string;
  small_context?: string;
}

/** The glasses user is a Person with this relationship; GET /user finds them. */
export const USER_RELATIONSHIP = "user";

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

export interface VoiceSample {
  voice_sample_id: number;
  created_at: string; // ISO 8601
}

/** Person context (contract/setup_api.py): one fact of the record behind the card. */
export interface Fact {
  id: number;
  text: string;
  source: "conversation" | "notes";
  created_at: string; // ISO 8601
}

/** A fact typed by the family: POST adds one, PATCH rewords one. Stored as written, source "notes". */
export interface FactIn {
  text: string; // 1 to 300 characters, not blank
}

export const FACT_MAX = 300;
export const CARD_MAX = 300;

/** What the real backend's one-shot sign-up, POST /enroll, returns. */
export interface EnrollOut {
  person: Person;
  photo_ids: number[];
  face_ids: number[];
  voice_sample_ids: number[];
  facts: number;
  skipped_photos: string[];
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

/** The visit is over: the server turns its transcript into facts and a card for each visitor. */
export interface EndVisitMessage {
  type: "end_visit";
}

export type ClientMessage = FrameMessage | AudioMessage | WhoMessage | EndVisitMessage;

// Server to client:

export interface PresentPerson {
  person_id: number;
  name: string;
  relationship: string;
  small_context: string;
  /** The newest few facts, for the bullets beside the name (empty before the first notes). */
  facts?: string[];
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
 * An utterance, transcribed, with the speaker voice recognition picked. Only a voice that matches
 * someone enrolled (the glasses user included) gets a name and an id; any other voice has
 * speaker and person_id null, and the bar shows it as "Someone".
 */
export interface CaptionMessage {
  type: "caption";
  speaker: string | null;
  person_id: number | null;
  text: string;
  /** False while the last word is still being transcribed; the server sends finished lines only. */
  final?: boolean;
  /** Seconds of audio since the connection opened. */
  start?: number;
  end?: number;
}

/** Nova's reply to a question that started with the wake word; spoken like any other sentence. */
export interface AnswerMessage {
  type: "answer";
  question: string;
  text: string;
}

/** After end_visit (or the connection closing): what was learned about one visitor. */
export interface VisitSavedMessage {
  type: "visit_saved";
  person_id: number;
  name: string;
  new_facts: string[];
  small_context: string;
}

export type ServerMessage =
  | PresentMessage
  | ArrivedMessage
  | UnknownMessage
  | WhoAnswerMessage
  | ErrorMessage
  | CaptionMessage
  | AnswerMessage
  | VisitSavedMessage;
