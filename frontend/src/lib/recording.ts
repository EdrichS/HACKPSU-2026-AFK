/** A finished voice recording, already in the contract's format (16 kHz mono 16-bit WAV). */
export interface Recording {
  wav: Blob;
  seconds: number;
  /** Normalized peaks, 0 to 1, one per waveform bar. */
  peaks: number[];
  /** Object URL of `wav`, for playback. Revoke it when the recording is discarded. */
  url: string;
}

/**
 * Shorter than this is "too short". The prompts take about 15 to 20 seconds to read; the
 * contract's own floor is 1 second, which is too little for a reliable voiceprint.
 */
export const MIN_RECORDING_SECONDS = 12; // the passages take about 30 s; under this, the whole text wasn't read
/** Recording stops by itself here, so a forgotten tab doesn't record forever. */
export const MAX_RECORDING_SECONDS = 60;

export function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
