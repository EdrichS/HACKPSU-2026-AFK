// The one audio format the contract accepts (contract/audio.py): WAV, 16 kHz, mono, 16-bit, at
// least a second long. Browsers record at 44.1 or 48 kHz, so everything goes through here first.

export const TARGET_RATE = 16000;
export const CONTRACT_MIN_SECONDS = 1.0;

/** Half the filter's length, in output samples: longer is a sharper cutoff and more work. */
const HALF_TAPS = 16;
/** The cutoff, as a fraction of the 8 kHz Nyquist limit: room for the filter to roll off. */
const CUTOFF = 0.9;
/** Kernel table entries per input sample; the kernel between entries is interpolated. */
const TABLE_STEPS = 64;

/** One side of the windowed-sinc kernel, sampled TABLE_STEPS times per input sample. */
function kernelTable(fc: number, reach: number): Float32Array {
  const table = new Float32Array(Math.ceil(reach * TABLE_STEPS) + 2);
  for (let k = 0; k < table.length; k++) {
    const t = Math.min(k / TABLE_STEPS, reach);
    const x = 2 * fc * t;
    const sinc = x === 0 ? 1 : Math.sin(Math.PI * x) / (Math.PI * x);
    const window = 0.42 + 0.5 * Math.cos((Math.PI * t) / reach) + 0.08 * Math.cos((2 * Math.PI * t) / reach); // Blackman
    table[k] = sinc * window;
  }
  return table;
}

/**
 * Mono float samples in [-1, 1] at any rate, low-passed and resampled to 16 kHz in JavaScript.
 * Not OfflineAudioContext: Chromium and WebKit resample a buffer by linear interpolation with no
 * anti-alias filter, so 8 to 24 kHz (sibilants, breath, hiss) would fold back into the voice band.
 */
export async function resampleTo16k(samples: Float32Array, sampleRate: number): Promise<Float32Array> {
  if (sampleRate === TARGET_RATE || samples.length === 0) return samples;
  const ratio = sampleRate / TARGET_RATE; // input samples per output sample
  // Downsampling cuts at the output's Nyquist; upsampling (a rare 8 kHz mic) at the input's.
  const fc = (CUTOFF * 0.5) / Math.max(ratio, 1); // cycles per input sample
  const reach = HALF_TAPS * Math.max(ratio, 1); // input samples on each side of the center
  const table = kernelTable(fc, reach);
  const frames = Math.max(1, Math.round(samples.length / ratio));
  const out = new Float32Array(frames);
  for (let i = 0; i < frames; i++) {
    const center = i * ratio;
    const first = Math.max(0, Math.ceil(center - reach));
    const last = Math.min(samples.length - 1, Math.floor(center + reach));
    let sum = 0;
    let weights = 0;
    for (let j = first; j <= last; j++) {
      const at = Math.abs(j - center) * TABLE_STEPS;
      const k = at | 0;
      const w = table[k] + (table[k + 1] - table[k]) * (at - k);
      sum += samples[j] * w;
      weights += w;
    }
    out[i] = weights !== 0 ? sum / weights : 0;
  }
  return out;
}

/** 16-bit PCM mono WAV bytes for 16 kHz float samples. */
export function encodeWav(samples: Float32Array, sampleRate: number = TARGET_RATE): ArrayBuffer {
  const bytes = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(bytes);
  const text = (offset: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(offset + i, s.charCodeAt(i));
  };
  text(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  text(8, "WAVE");
  text(12, "fmt ");
  view.setUint32(16, 16, true); // fmt chunk size
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); // byte rate
  view.setUint16(32, 2, true); // block align
  view.setUint16(34, 16, true); // bits per sample
  text(36, "data");
  view.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return bytes;
}

/** Join captured chunks into one buffer. */
export function concat(chunks: Float32Array[]): Float32Array {
  const out = new Float32Array(chunks.reduce((n, c) => n + c.length, 0));
  let offset = 0;
  for (const c of chunks) {
    out.set(c, offset);
    offset += c.length;
  }
  return out;
}

/** Base64 of raw bytes, for the /live socket's `wav` and `jpeg` fields. */
export function toBase64(bytes: ArrayBuffer): string {
  const view = new Uint8Array(bytes);
  let binary = "";
  for (let i = 0; i < view.length; i += 0x8000) {
    binary += String.fromCharCode(...view.subarray(i, i + 0x8000));
  }
  return btoa(binary);
}

/** Peak level per bucket, 0 to 1, for drawing a recorded waveform. */
export function peaks(samples: Float32Array, buckets: number): number[] {
  const out: number[] = [];
  const size = Math.max(1, Math.floor(samples.length / buckets));
  for (let b = 0; b < buckets; b++) {
    let peak = 0;
    const end = Math.min(samples.length, (b + 1) * size);
    for (let i = b * size; i < end; i++) peak = Math.max(peak, Math.abs(samples[i]));
    out.push(peak);
  }
  const loudest = Math.max(...out, 1e-6);
  return out.map((p) => p / loudest);
}
