/** Tiny WebAudio sound cues (no audio files). Everything is user-controllable via the Sound toggle. */
let ctx: AudioContext | null = null;
let ringTimer: number | null = null;

const KEY = "meridian.sound";

export function soundEnabled(): boolean {
  try {
    return localStorage.getItem(KEY) !== "off";
  } catch {
    return true;
  }
}

export function setSoundEnabled(on: boolean): void {
  try {
    localStorage.setItem(KEY, on ? "on" : "off");
  } catch {
    /* storage can be unavailable; the toggle still works for this session via state */
  }
  if (!on) stopRing();
}

function audio(): AudioContext | null {
  try {
    ctx = ctx ?? new AudioContext();
    if (ctx.state === "suspended") void ctx.resume();
    return ctx;
  } catch {
    return null;
  }
}

function tone(freq: number, start: number, dur: number, gain = 0.06): void {
  const c = audio();
  if (!c) return;
  const osc = c.createOscillator();
  const g = c.createGain();
  osc.type = "sine";
  osc.frequency.value = freq;
  g.gain.setValueAtTime(0, c.currentTime + start);
  g.gain.linearRampToValueAtTime(gain, c.currentTime + start + 0.02);
  g.gain.linearRampToValueAtTime(0, c.currentTime + start + dur);
  osc.connect(g).connect(c.destination);
  osc.start(c.currentTime + start);
  osc.stop(c.currentTime + start + dur + 0.05);
}

export function startRing(): void {
  if (!soundEnabled()) return;
  stopRing();
  const burst = () => {
    tone(440, 0, 0.4);
    tone(480, 0, 0.4);
    tone(440, 0.5, 0.4);
    tone(480, 0.5, 0.4);
  };
  burst();
  ringTimer = window.setInterval(burst, 2400);
}

export function stopRing(): void {
  if (ringTimer !== null) window.clearInterval(ringTimer);
  ringTimer = null;
}

export function playConnected(): void {
  if (!soundEnabled()) return;
  tone(660, 0, 0.12);
  tone(880, 0.14, 0.18);
}

export function playEnded(): void {
  if (!soundEnabled()) return;
  tone(520, 0, 0.18);
  tone(390, 0.2, 0.3);
}

export function playSuccess(): void {
  if (!soundEnabled()) return;
  tone(784, 0, 0.1);
  tone(988, 0.12, 0.1);
  tone(1175, 0.24, 0.22);
}

/** Real audio level (0..1) from a MediaStream, read on demand. */
export class LevelMeter {
  private analyser: AnalyserNode;
  private source: MediaStreamAudioSourceNode;
  private data: Uint8Array<ArrayBuffer>;

  constructor(stream: MediaStream) {
    const c = audio();
    if (!c) throw new Error("WebAudio unavailable");
    this.analyser = c.createAnalyser();
    this.analyser.fftSize = 256;
    this.analyser.smoothingTimeConstant = 0.6;
    this.source = c.createMediaStreamSource(stream);
    this.source.connect(this.analyser);
    this.data = new Uint8Array(new ArrayBuffer(this.analyser.frequencyBinCount));
  }

  level(): number {
    this.analyser.getByteTimeDomainData(this.data);
    let sum = 0;
    for (let i = 0; i < this.data.length; i++) {
      const v = (this.data[i] - 128) / 128;
      sum += v * v;
    }
    return Math.min(1, Math.sqrt(sum / this.data.length) * 3.2);
  }

  close(): void {
    try {
      this.source.disconnect();
    } catch {
      /* already disconnected */
    }
  }
}
