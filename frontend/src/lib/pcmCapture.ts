// Raw microphone samples, for both the Recorder (voice enrollment) and the live view's audio
// chunks. MediaRecorder only gives compressed webm/opus, and the contract wants 16 kHz WAV.

/** The same constraints everywhere, so enrollment and live audio sound alike to the voice model. */
export const MIC_CONSTRAINTS: MediaTrackConstraints = {
  channelCount: 1,
  echoCancellation: true, // keeps the live view from hearing its own spoken announcements
  noiseSuppression: true,
  autoGainControl: true,
};

export interface PcmCapture {
  /** The rate the samples arrive at (the device's, usually 44100 or 48000). */
  readonly sampleRate: number;
  /** For drawing a live waveform. */
  readonly analyser: AnalyserNode;
  stop(): void;
}

// Collects 4096 frames before posting, so the main thread gets ~12 messages a second, not ~375.
const WORKLET = `
class NametagsTap extends AudioWorkletProcessor {
  constructor() { super(); this.buf = new Float32Array(4096); this.n = 0; }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (ch) {
      for (let i = 0; i < ch.length; i++) {
        this.buf[this.n++] = ch[i];
        if (this.n === this.buf.length) { this.port.postMessage(this.buf.slice(0)); this.n = 0; }
      }
    }
    return true;
  }
}
registerProcessor("nametags-tap", NametagsTap);
`;

/** Start delivering mono float samples from `stream` to `onSamples` until stop() is called. */
export async function startPcmCapture(
  stream: MediaStream,
  onSamples: (chunk: Float32Array) => void,
): Promise<PcmCapture> {
  const context = new AudioContext();
  try {
    return await connect(context, stream, onSamples);
  } catch (error) {
    void context.close(); // don't leak the audio device when the worklet can't load
    throw error;
  }
}

async function connect(
  context: AudioContext,
  stream: MediaStream,
  onSamples: (chunk: Float32Array) => void,
): Promise<PcmCapture> {
  if (context.state === "suspended") await context.resume();
  const source = context.createMediaStreamSource(stream);
  const analyser = context.createAnalyser();
  analyser.fftSize = 1024;
  source.connect(analyser);

  let disconnect: () => void;
  if (context.audioWorklet) {
    const url = URL.createObjectURL(new Blob([WORKLET], { type: "application/javascript" }));
    try {
      await context.audioWorklet.addModule(url);
    } finally {
      URL.revokeObjectURL(url);
    }
    const tap = new AudioWorkletNode(context, "nametags-tap", { numberOfInputs: 1, numberOfOutputs: 0 });
    tap.port.onmessage = (event: MessageEvent<Float32Array>) => onSamples(event.data);
    source.connect(tap);
    disconnect = () => {
      tap.port.onmessage = null;
      tap.disconnect();
    };
  } else {
    // Older Safari: ScriptProcessorNode is deprecated but still works there.
    const processor = context.createScriptProcessor(4096, 1, 1);
    processor.onaudioprocess = (event) => onSamples(new Float32Array(event.inputBuffer.getChannelData(0)));
    source.connect(processor);
    processor.connect(context.destination); // a ScriptProcessor only runs while connected
    disconnect = () => {
      processor.onaudioprocess = null;
      processor.disconnect();
    };
  }

  return {
    sampleRate: context.sampleRate,
    analyser,
    stop() {
      disconnect();
      source.disconnect();
      void context.close();
    },
  };
}

/** Current level per bar, 0 to 1, from an analyser: for the live waveform while recording. */
export function levels(analyser: AnalyserNode, bars: number): number[] {
  const data = new Uint8Array(analyser.fftSize);
  analyser.getByteTimeDomainData(data);
  const size = Math.floor(data.length / bars);
  const out: number[] = [];
  for (let b = 0; b < bars; b++) {
    let peak = 0;
    for (let i = b * size; i < (b + 1) * size; i++) peak = Math.max(peak, Math.abs(data[i] - 128) / 128);
    out.push(Math.min(1, peak * 2.5));
  }
  return out;
}
