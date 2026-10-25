// Speaks the server's sentences with an on-device voice. Names must never reach a cloud voice, so
// without a local English voice nothing is spoken (the text still shows in the caption bar).

import { useCallback, useEffect, useRef, useState } from "react";

import { PREFERRED_VOICES } from "../config";

const RATE = 0.95;
/** The mic stays muted this long after speech ends, for the room's echo. */
const MUTE_TAIL_MS = 300;

interface SpeakerEvents {
  onSpeakingChange(speaking: boolean): void;
  onStart(text: string): void;
  onEnd(text: string): void;
}

class Speaker {
  private readonly synth: SpeechSynthesis | null = typeof speechSynthesis === "undefined" ? null : speechSynthesis;
  private readonly events: SpeakerEvents;
  // Holding the utterances also keeps Chrome from collecting them before onend fires.
  private readonly pending = new Map<SpeechSynthesisUtterance, { text: string; watchdog: number }>();
  private voice: SpeechSynthesisVoice | null = null;
  private queueEnd = 0;
  private toldNoVoice = false;
  private disposed = false;

  constructor(events: SpeakerEvents) {
    this.events = events;
    this.synth?.addEventListener("voiceschanged", this.pickVoice);
    this.pickVoice();
  }

  /**
   * The first installed voice from PREFERRED_VOICES (a name match, so "Samantha" also finds the
   * better "Samantha (Enhanced)" once it's downloaded), else the system's default English voice.
   */
  private readonly pickVoice = () => {
    const local = (this.synth?.getVoices() ?? []).filter((v) => v.localService && v.lang.toLowerCase().startsWith("en"));
    const preferred = PREFERRED_VOICES.map((name) => name.toLowerCase())
      .map((name) => local.find((v) => v.name.toLowerCase().includes(name)))
      .find((v) => v !== undefined);
    this.voice = preferred ?? local.find((v) => v.default) ?? local.find((v) => /^en[-_]us$/i.test(v.lang)) ?? local[0] ?? null;
  };

  /** Some browsers only allow speech after one call inside a user gesture. Says nothing. */
  unlock() {
    if (!this.synth) return;
    this.pickVoice();
    const silent = new SpeechSynthesisUtterance("");
    silent.volume = 0;
    if (this.voice) silent.voice = this.voice;
    this.synth.speak(silent);
  }

  /** Queue `text`; false if there is no on-device voice to say it with. */
  speak(text: string): boolean {
    if (this.disposed) return false;
    if (!this.synth) return this.noVoice();
    if (!this.voice) this.pickVoice();
    const voice = this.voice;
    if (!voice) return this.noVoice();

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.voice = voice;
    utterance.lang = voice.lang;
    utterance.rate = RATE;
    utterance.onstart = () => {
      if (!this.disposed) this.events.onStart(text);
    };
    utterance.onend = () => this.finish(utterance);
    utterance.onerror = () => this.finish(utterance);

    // onend never fires when a speech engine hangs; without this the mic would stay muted for good.
    const now = performance.now();
    this.queueEnd = Math.max(this.queueEnd, now) + 6000 + text.length * 90;
    const watchdog = window.setTimeout(() => this.giveUp(), this.queueEnd - now);
    if (this.pending.size === 0) this.events.onSpeakingChange(true);
    this.pending.set(utterance, { text, watchdog });
    this.synth.speak(utterance);
    return true;
  }

  private noVoice(): false {
    if (!this.toldNoVoice) {
      console.info("Name Tags: no on-device English voice, so announcements are shown but not spoken.");
      this.toldNoVoice = true;
    }
    return false;
  }

  private finish(utterance: SpeechSynthesisUtterance) {
    const entry = this.pending.get(utterance);
    if (!entry || this.disposed) return;
    window.clearTimeout(entry.watchdog);
    this.pending.delete(utterance);
    this.events.onEnd(entry.text);
    if (this.pending.size === 0) {
      this.queueEnd = 0;
      this.events.onSpeakingChange(false);
    }
  }

  private giveUp() {
    for (const utterance of [...this.pending.keys()]) this.finish(utterance);
    this.synth?.cancel();
  }

  dispose() {
    this.disposed = true;
    for (const { watchdog } of this.pending.values()) window.clearTimeout(watchdog);
    this.pending.clear();
    this.synth?.removeEventListener("voiceschanged", this.pickVoice);
    this.synth?.cancel();
  }
}

export interface Speech {
  /** True from the moment a sentence is queued until the queue is empty. */
  speaking: boolean;
  speak(text: string): boolean;
  unlock(): void;
  /** While speaking and for a moment after: the live audio is dropped, not sent. */
  isMuted(): boolean;
}

export function useSpeech(events: { onStart(text: string): void; onEnd(text: string): void }): Speech {
  const [speaking, setSpeaking] = useState(false);
  const speaker = useRef<Speaker | null>(null);
  const mutedUntil = useRef(0);
  const latest = useRef(events);
  useEffect(() => {
    latest.current = events;
  });

  useEffect(() => {
    const instance = new Speaker({
      onSpeakingChange: (on) => {
        mutedUntil.current = on ? Number.POSITIVE_INFINITY : performance.now() + MUTE_TAIL_MS;
        setSpeaking(on);
      },
      onStart: (text) => latest.current.onStart(text),
      onEnd: (text) => latest.current.onEnd(text),
    });
    speaker.current = instance;
    return () => {
      instance.dispose();
      speaker.current = null;
      mutedUntil.current = 0;
    };
  }, []);

  const speak = useCallback((text: string) => speaker.current?.speak(text) ?? false, []);
  const unlock = useCallback(() => speaker.current?.unlock(), []);
  const isMuted = useCallback(() => performance.now() < mutedUntil.current, []);
  return { speaking, speak, unlock, isMuted };
}
