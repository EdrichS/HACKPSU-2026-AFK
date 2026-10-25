// Shared bits for the rough test UI: where the API is, microphone capture to 16 kHz WAV, speaking.
// This is a test harness for the API, not the product UI.

const API = new URLSearchParams(location.search).get("api") || location.origin;
const WS_BASE = API.replace(/^http/, "ws");

function el(id) { return document.getElementById(id); }

async function api(path, options = {}) {
  const r = await fetch(API + path, options);
  const text = await r.text();
  let body;
  try { body = JSON.parse(text); } catch { body = text; }
  return { status: r.status, ok: r.ok, body };
}

// Float32 samples at 16 kHz -> a 16-bit PCM mono WAV blob (the contract's format).
function wavBlob(samples, rate = 16000) {
  const buf = new ArrayBuffer(44 + samples.length * 2);
  const v = new DataView(buf);
  const str = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  str(0, "RIFF"); v.setUint32(4, 36 + samples.length * 2, true); str(8, "WAVE");
  str(12, "fmt "); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, rate, true); v.setUint32(28, rate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  str(36, "data"); v.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    v.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([buf], { type: "audio/wav" });
}

// Downsample float32 audio from `from` Hz to 16 kHz by averaging (good enough for speech).
function to16k(samples, from) {
  if (from === 16000) return Float32Array.from(samples);
  const ratio = from / 16000, n = Math.floor(samples.length / ratio), out = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const a = Math.floor(i * ratio), b = Math.max(a + 1, Math.floor((i + 1) * ratio));
    let s = 0;
    for (let j = a; j < b; j++) s += samples[j];
    out[i] = s / (b - a);
  }
  return out;
}

function concat(chunks) {
  const n = chunks.reduce((a, c) => a + c.length, 0), out = new Float32Array(n);
  let o = 0;
  for (const c of chunks) { out.set(c, o); o += c.length; }
  return out;
}

// Microphone capture: onChunk(Float32Array at 16 kHz) for every block; `level` is the latest RMS.
class Mic {
  constructor(onChunk) { this.onChunk = onChunk; this.level = 0; }
  async start() {
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
    this.ctx = new (window.AudioContext || window.webkitAudioContext)();
    const src = this.ctx.createMediaStreamSource(this.stream);
    this.proc = this.ctx.createScriptProcessor(4096, 1, 1);
    const sink = this.ctx.createGain();
    sink.gain.value = 0; // the processor needs an output, but we must not play the mic back
    this.proc.onaudioprocess = (e) => {
      const x = e.inputBuffer.getChannelData(0);
      let s = 0;
      for (let i = 0; i < x.length; i++) s += x[i] * x[i];
      this.level = Math.sqrt(s / x.length);
      this.onChunk(to16k(x, this.ctx.sampleRate));
    };
    src.connect(this.proc); this.proc.connect(sink); sink.connect(this.ctx.destination);
  }
  stop() {
    this.proc?.disconnect(); this.ctx?.close(); this.stream?.getTracks().forEach(t => t.stop());
  }
}

// The frontend speaks every `text` the server sends (the contract); the browser voice is local.
function speak(text) {
  if (!("speechSynthesis" in window) || !el("tts")?.checked) return;
  const u = new SpeechSynthesisUtterance(text);
  u.rate = 0.95;
  speechSynthesis.speak(u);
}
function speaking() { return "speechSynthesis" in window && speechSynthesis.speaking; }

// Read a file input as bytes (the no-camera / no-mic fallbacks).
function fileFrom(input) { return input.files && input.files[0] ? input.files[0] : null; }
