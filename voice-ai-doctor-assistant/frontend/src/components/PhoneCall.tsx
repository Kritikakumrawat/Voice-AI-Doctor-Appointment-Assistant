import { useEffect, useRef, useState, type FormEvent } from "react";
import type { CallController } from "../hooks/useCall";
import type { AppConfig } from "../types";
import { ConfirmCard } from "./ConfirmCard";
import { IconCross, IconEnd, IconMic, IconMicOff, IconSend, IconVolume, IconVolumeOff, IconX } from "./Icons";
import { Waveform } from "./Waveform";

const fmt = (s: number) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
const clock = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });

const SUGGESTIONS = ["I'd like to see a cardiologist", "What slots does Dr. Nair have?", "I need to cancel my appointment"];

interface Props {
  call: CallController;
  config: AppConfig | null;
  open: boolean;
  onClose: () => void;
}

export function PhoneCall({ call, config, open, onClose }: Props) {
  const { state } = call;
  const live = config?.app_mode === "live";
  const [text, setText] = useState("");
  const [speakReplies, setSpeakReplies] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);
  const spokenKey = useRef<string>("");

  useEffect(() => {
    // Jump (no animation) after layout so the newest line or confirmation card is always in view.
    const el = scroller.current;
    if (!el) return;
    const id = requestAnimationFrame(() => { el.scrollTop = el.scrollHeight; });
    return () => cancelAnimationFrame(id);
  }, [call.lines, call.busy, call.card]);

  // Demo mode only: optionally read the agent's replies aloud with the browser's own voice.
  useEffect(() => {
    if (!speakReplies || live || !("speechSynthesis" in window)) return;
    const last = [...call.lines].reverse().find((l) => l.role === "assistant" && l.final);
    if (!last || last.key === spokenKey.current) return;
    spokenKey.current = last.key;
    const u = new SpeechSynthesisUtterance(last.text);
    u.lang = "en-IN";
    window.speechSynthesis.speak(u);
  }, [call.lines, speakReplies, live]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && state !== "connected" && state !== "connecting") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, state, onClose]);

  if (!open) return null;

  const active = state === "connecting" || state === "connected";
  const statusText =
    state === "connecting" ? (live ? "Connecting…" : "Ringing…")
    : state === "connected" ? fmt(call.seconds)
    : state === "ended" ? `Call ended · ${fmt(call.seconds)}`
    : state === "error" ? "Call failed"
    : "Ready";

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!text.trim()) return;
    void call.send(text);
    setText("");
  };

  const close = async () => {
    if (active) await call.end();
    call.reset();
    onClose();
  };

  return (
    <div className="phone-overlay" role="presentation">
      <section className={`phone phone-${state}`} role="dialog" aria-modal="true" aria-label="Voice call">
        <header className="phone-top">
          <button className="phone-x" onClick={close} aria-label="Close call window"><IconX size={16} /></button>
          <span className={`mode-chip ${live ? "mode-live" : "mode-demo"}`}>
            {live ? "Live · Gemini + ElevenLabs" : "Demo · simulated agent"}
          </span>
          {!live && (
            <button
              className={`phone-tool ${speakReplies ? "on" : ""}`}
              onClick={() => { setSpeakReplies((v) => !v); if (speakReplies) window.speechSynthesis?.cancel(); }}
              aria-pressed={speakReplies}
              title="Read the agent's replies aloud with your browser's voice"
            >
              {speakReplies ? <IconVolume size={16} /> : <IconVolumeOff size={16} />}
            </button>
          )}
        </header>

        <div className="phone-id">
          <div className={`avatar ${state === "connecting" ? "avatar-ring" : ""}`}><IconCross size={26} /></div>
          <h2>{config?.clinic_name ?? "Front desk"}</h2>
          <p className={`phone-status status-${state}`} aria-live="polite">
            {state === "connected" && <i className="dot" />}
            {statusText}
          </p>
          {state === "connected" && (
            <p className="phone-sub">
              {call.speaking.assistant ? "Assistant is speaking" : call.speaking.user ? "Listening to you" : call.busy ? "Assistant is thinking…" : "On the line"}
            </p>
          )}
        </div>

        {(state === "connected" || state === "ended") && (
          <div className="wave-wrap">
            <Waveform getLevels={call.getLevels} active={state === "connected"} />
            {!live && state === "connected" && !call.listening && <span className="wave-hint">Mic meter shows when you use the mic button</span>}
          </div>
        )}

        {state === "error" && (
          <div className="phone-error" role="alert">
            <p>{call.error}</p>
          </div>
        )}

        <div className="transcript" ref={scroller} aria-live="polite" aria-label="Live transcript">
          {call.lines.length === 0 && state !== "error" && (
            <p className="transcript-empty">{state === "connecting" ? "The transcript will appear here." : "No transcript yet."}</p>
          )}
          {call.lines.map((l) => (
            <div key={l.key} className={`bubble bubble-${l.role} ${l.final ? "" : "bubble-interim"}`}>
              <span className="bubble-meta">{l.role === "assistant" ? "Assistant" : "Caller"} · {clock(l.ts)}</span>
              <p>{l.text}</p>
            </div>
          ))}
          {call.busy && <div className="bubble bubble-assistant typing" aria-label="Assistant is typing"><i /><i /><i /></div>}
          {call.card && <ConfirmCard card={call.card} onClose={call.dismissCard} />}
        </div>

        {!live && state === "connected" && (
          <div className="demo-input">
            {call.lines.filter((l) => l.role === "user").length === 0 && (
              <div className="chips">
                {SUGGESTIONS.map((s) => <button key={s} className="chip" onClick={() => void call.send(s)}>{s}</button>)}
              </div>
            )}
            <form onSubmit={submit}>
              <button type="button" className={`round ${call.listening ? "round-on" : ""}`} onClick={() => void call.toggleListening()} aria-pressed={call.listening} aria-label="Speak using your browser microphone" disabled={call.muted}>
                <IconMic size={18} />
              </button>
              <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Type what the caller says…" aria-label="Caller message" autoFocus />
              <button type="submit" className="round round-send" aria-label="Send" disabled={!text.trim()}><IconSend size={18} /></button>
            </form>
          </div>
        )}

        <footer className="phone-controls">
          {active && (
            <>
              <button className={`ctl ${call.muted ? "ctl-on" : ""}`} onClick={call.toggleMute} aria-pressed={call.muted} disabled={state !== "connected"}>
                {call.muted ? <IconMicOff /> : <IconMic />}<span>{call.muted ? "Unmute" : "Mute"}</span>
              </button>
              <button className="ctl ctl-end" onClick={() => void call.end()}>
                <IconEnd /><span>End call</span>
              </button>
            </>
          )}
          {!active && (
            <>
              <button className="ctl ctl-call" onClick={() => void call.start()}><IconMic /><span>{state === "idle" ? "Start call" : "Call again"}</span></button>
              <button className="ctl" onClick={() => void close()}><IconX /><span>Close</span></button>
            </>
          )}
        </footer>
      </section>
    </div>
  );
}
