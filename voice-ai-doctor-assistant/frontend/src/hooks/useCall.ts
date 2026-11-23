import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../services/api";
import { LevelMeter, playConnected, playEnded, playSuccess, startRing, stopRing } from "../services/sound";
import type { AppConfig, Appointment, CallCard, CallState, ServerEvent, TranscriptLine } from "../types";
import type { EventBus } from "./useEventBus";
import { useToast } from "./useToasts";

const sleep = (ms: number) => new Promise((r) => window.setTimeout(r, ms));

function withTimeout<T>(p: Promise<T>, ms: number, message: string): Promise<T> {
  return new Promise((resolve, reject) => {
    const t = window.setTimeout(() => reject(new Error(message)), ms);
    p.then((v) => { window.clearTimeout(t); resolve(v); }, (e) => { window.clearTimeout(t); reject(e); });
  });
}

function micError(e: unknown): string {
  const name = (e as DOMException)?.name;
  if (name === "NotAllowedError" || name === "SecurityError") {
    return "Microphone access is blocked. Allow it in the address bar, then try again.";
  }
  if (name === "NotFoundError") return "No microphone was found on this device.";
  return "Couldn't open the microphone.";
}

export function useCall(config: AppConfig | null, bus: EventBus) {
  const toast = useToast();
  const [state, setState] = useState<CallState>("idle");
  const [lines, setLines] = useState<TranscriptLine[]>([]);
  const [muted, setMuted] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [card, setCard] = useState<CallCard | null>(null);
  const [speaking, setSpeaking] = useState({ user: false, assistant: false });
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);

  const stateRef = useRef<CallState>("idle");
  const callId = useRef<string | null>(null);
  const clickedAt = useRef(0);
  const connectedAt = useRef(0);
  const client = useRef<any>(null);
  const botAudio = useRef<HTMLAudioElement | null>(null);
  const micMeter = useRef<LevelMeter | null>(null);
  const botMeter = useRef<LevelMeter | null>(null);
  const listenStream = useRef<MediaStream | null>(null);
  const recognition = useRef<any>(null);
  const mutedRef = useRef(false);
  const keySeq = useRef(0);
  const busConnected = useRef(bus.connected);
  busConnected.current = bus.connected;

  const setCallState = (s: CallState) => {
    stateRef.current = s;
    setState(s);
  };

  // ---- transcript ------------------------------------------------------------------------
  const pushLine = useCallback((role: "user" | "assistant", text: string, final: boolean, ts?: string) => {
    setLines((prev) => {
      const clean = prev.filter((l) => !(l.role === role && !l.final)); // drop the old interim line
      const last = clean[clean.length - 1];
      if (final && last && last.role === role && last.final && last.text.trim() === text.trim()) return clean; // duplicate (event + response)
      return [...clean, { key: `l${keySeq.current++}`, role, text, final, ts: ts ?? new Date().toISOString() }];
    });
  }, []);

  // ---- server events for the active call --------------------------------------------------
  useEffect(
    () =>
      bus.subscribe((e: ServerEvent, isLive: boolean) => {
        if (!isLive) return;
        if (e.type === "call.started" && stateRef.current === "connecting" && !callId.current && Date.parse(e.ts) >= clickedAt.current - 2000) {
          callId.current = e.call_id;
          return;
        }
        if (!callId.current || e.call_id !== callId.current) return;
        if (e.type === "transcript") {
          pushLine(e.payload.role, e.payload.text, e.payload.final !== false, e.ts);
        } else if (e.type === "speaking") {
          setSpeaking((s) => ({ ...s, [e.payload.who]: !!e.payload.active }));
        } else if (e.type === "appointment.booked" || e.type === "appointment.cancelled") {
          const kind = e.type === "appointment.booked" ? "booked" : "cancelled";
          setCard({ kind, appointment: e.payload.appointment as Appointment });
          playSuccess();
        } else if (e.type === "call.ended" && stateRef.current === "connected") {
          void finish("ended");
        } else if (e.type === "error" && e.payload.fatal) {
          void finish("error", e.payload.message);
        }
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [bus, pushLine],
  );

  // ---- timer -------------------------------------------------------------------------------
  useEffect(() => {
    if (state !== "connected") return;
    const t = window.setInterval(() => setSeconds(Math.floor((Date.now() - connectedAt.current) / 1000)), 500);
    return () => window.clearInterval(t);
  }, [state]);

  // ---- cleanup -----------------------------------------------------------------------------
  const releaseMedia = () => {
    micMeter.current?.close();
    botMeter.current?.close();
    micMeter.current = botMeter.current = null;
    listenStream.current?.getTracks().forEach((t) => t.stop());
    listenStream.current = null;
    try { recognition.current?.stop(); } catch { /* not running */ }
    recognition.current = null;
    setListening(false);
    if (botAudio.current) {
      botAudio.current.srcObject = null;
      botAudio.current = null;
    }
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
  };

  const finish = async (to: "ended" | "error", message?: string) => {
    if (stateRef.current === "ended" || stateRef.current === "error" || stateRef.current === "idle") return;
    stopRing();
    const c = client.current;
    client.current = null;
    try { await c?.disconnect?.(); } catch { /* already closed */ }
    releaseMedia();
    setSpeaking({ user: false, assistant: false });
    setBusy(false);
    if (to === "error") {
      setError(message ?? "The call failed.");
      toast("error", message ?? "The call failed.");
    } else {
      playEnded();
    }
    setCallState(to);
  };

  useEffect(() => () => { void finish("ended"); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ---- start -------------------------------------------------------------------------------
  const start = useCallback(async () => {
    if (!config) { toast("error", "Still loading. Try again in a second."); return; }
    if (stateRef.current === "connecting" || stateRef.current === "connected") return;
    callId.current = null;
    clickedAt.current = Date.now();
    setLines([]); setCard(null); setError(null); setSeconds(0); setMuted(false); mutedRef.current = false;
    setSpeaking({ user: false, assistant: false });
    setCallState("connecting");
    startRing();
    try {
      if (config.app_mode === "mock") await startMock();
      else await startLive();
    } catch (e) {
      const msg = e instanceof ApiError || e instanceof Error ? e.message : "The call could not be started.";
      await finish("error", msg);
    }
  }, [config]); // eslint-disable-line react-hooks/exhaustive-deps

  const markConnected = () => {
    stopRing();
    connectedAt.current = Date.now();
    setCallState("connected");
    playConnected();
  };

  const startMock = async () => {
    const [res] = await Promise.all([api.startCall(), sleep(1800)]);
    callId.current = res.call_id;
    pushLine("assistant", res.greeting, true);
    markConnected();
  };

  const startLive = async () => {
    try {
      const probe = await navigator.mediaDevices.getUserMedia({ audio: true });
      probe.getTracks().forEach((t) => t.stop());
    } catch (e) {
      throw new Error(micError(e));
    }
    const [{ PipecatClient }, { SmallWebRTCTransport }] = await Promise.all([
      import("@pipecat-ai/client-js"),
      import("@pipecat-ai/small-webrtc-transport"),
    ]);
    const pc: any = new (PipecatClient as any)({
      transport: new (SmallWebRTCTransport as any)(),
      enableMic: true,
      enableCam: false,
      callbacks: {
        onTrackStarted: (track: MediaStreamTrack, participant?: { local?: boolean }) => {
          if (track.kind !== "audio") return;
          const stream = new MediaStream([track]);
          try {
            if (participant?.local) {
              micMeter.current?.close();
              micMeter.current = new LevelMeter(stream);
            } else {
              const el = botAudio.current ?? new Audio();
              el.autoplay = true;
              el.srcObject = stream;
              void el.play().catch(() => toast("info", "Click anywhere to let the browser play the assistant's voice."));
              botAudio.current = el;
              botMeter.current?.close();
              botMeter.current = new LevelMeter(stream);
            }
          } catch { /* meters are cosmetic */ }
        },
        onDisconnected: () => {
          if (stateRef.current === "connected") void finish("ended");
        },
        onError: (m: any) => {
          const text = m?.data?.message ?? m?.message ?? "A connection error occurred.";
          toast("error", String(text));
        },
      },
    });
    client.current = pc;
    await withTimeout(
      pc.connect({ webrtcUrl: api.webrtcUrl }),
      25000,
      "Connecting took too long. Check that the backend is running in live mode and your API keys are valid.",
    );
    markConnected();
  };

  // ---- controls ----------------------------------------------------------------------------
  const end = useCallback(async () => {
    const id = callId.current;
    if (stateRef.current !== "connecting" && stateRef.current !== "connected") return;
    if (id) api.endCall(id).catch(() => {});
    await finish("ended");
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const toggleMute = useCallback(() => {
    const next = !mutedRef.current;
    mutedRef.current = next;
    setMuted(next);
    try { client.current?.enableMic?.(!next); } catch { /* demo mode has no client */ }
    if (next) { try { recognition.current?.stop(); } catch { /* idle */ } setListening(false); }
  }, []);

  const send = useCallback(async (text: string) => {
    const id = callId.current;
    const t = text.trim();
    if (!id || !t || stateRef.current !== "connected") return;
    pushLine("user", t, true);
    setBusy(true);
    try {
      const res = await api.say(id, t);
      // Normally the reply arrives over the event stream. Only use the HTTP response when the stream is down.
      if (!busConnected.current) pushLine("assistant", res.reply, true);
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Message failed.");
    } finally {
      setBusy(false);
    }
  }, [pushLine, toast]);

  /** Demo mode only: use the browser's built-in speech recognition to fill the transcript. */
  const toggleListening = useCallback(async () => {
    if (stateRef.current !== "connected" || mutedRef.current) return;
    if (recognition.current) {
      try { recognition.current.stop(); } catch { /* idle */ }
      return;
    }
    const SR = (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition;
    if (!SR) { toast("info", "Speech recognition isn't available in this browser. Type instead."); return; }
    try {
      listenStream.current = await navigator.mediaDevices.getUserMedia({ audio: true });
      micMeter.current?.close();
      micMeter.current = new LevelMeter(listenStream.current);
    } catch (e) {
      toast("error", micError(e));
      return;
    }
    const rec = new SR();
    rec.lang = "en-IN";
    rec.interimResults = false;
    rec.continuous = false;
    rec.onresult = (ev: any) => {
      const said = ev.results?.[0]?.[0]?.transcript;
      if (said) void send(said);
    };
    rec.onerror = (ev: any) => {
      if (ev.error === "not-allowed" || ev.error === "service-not-allowed") toast("error", "Speech recognition was blocked by the browser.");
      else if (ev.error !== "no-speech" && ev.error !== "aborted") toast("error", `Speech recognition error: ${ev.error}`);
    };
    rec.onend = () => {
      recognition.current = null;
      setListening(false);
      micMeter.current?.close();
      micMeter.current = null;
      listenStream.current?.getTracks().forEach((t) => t.stop());
      listenStream.current = null;
    };
    recognition.current = rec;
    setListening(true);
    rec.start();
  }, [send, toast]);

  const getLevels = useCallback(() => ({
    mic: micMeter.current && !mutedRef.current ? micMeter.current.level() : 0,
    bot: botMeter.current ? botMeter.current.level() : 0,
  }), []);

  const reset = useCallback(() => {
    if (stateRef.current === "ended" || stateRef.current === "error") {
      setLines([]); setCard(null); setError(null); setSeconds(0);
      setCallState("idle");
    }
  }, []);

  return {
    state, lines, muted, seconds, error, card, speaking, busy, listening,
    start, end, toggleMute, send, toggleListening, getLevels, reset,
    dismissCard: () => setCard(null),
    mode: config?.app_mode ?? "mock",
  };
}

export type CallController = ReturnType<typeof useCall>;
