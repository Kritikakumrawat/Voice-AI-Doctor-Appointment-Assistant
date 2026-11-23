import type { ServerEvent } from "../types";

export const todayLong = () =>
  new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });

export const clockTime = (iso: string) =>
  new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });

export const initials = (name: string) =>
  name.replace(/^Dr\.?\s+/i, "").split(/\s+/).map((p) => p[0]).slice(0, 2).join("").toUpperCase();

export type Tone = "ok" | "warn" | "bad" | "info";

export interface FeedView {
  key: number;
  tone: Tone;
  title: string;
  detail: string;
  ts: string;
}

const TOOL_TITLES: Record<string, string> = {
  check_doctor_availability: "Availability checked",
  book_appointment: "Booking step",
  cancel_appointment: "Cancellation step",
};

/** Turns a server event into one human line for the activity feed (or null to hide it). */
export function describeEvent(e: ServerEvent): FeedView | null {
  const p = e.payload;
  const base = { key: e.id, ts: e.ts };
  switch (e.type) {
    case "appointment.booked":
      return { ...base, tone: "ok", title: "Booking confirmed", detail: `${p.appointment.doctor_name} · ${p.appointment.date_label}, ${p.appointment.time_label} · ${p.appointment.id}` };
    case "appointment.cancelled":
      return { ...base, tone: "warn", title: "Cancellation completed", detail: `${p.appointment.doctor_name} · ${p.appointment.date_label}, ${p.appointment.time_label} · ${p.appointment.id}` };
    case "tool.finished": {
      if (p.status === "booked" || p.status === "cancelled") return null; // shown by the appointment events
      const isError = p.status === "error" || p.status === "no_match";
      return { ...base, tone: isError ? "bad" : p.status === "needs_confirmation" ? "info" : "info",
        title: isError ? "Tool reported a problem" : TOOL_TITLES[p.tool] ?? "Tool called", detail: p.summary ?? "" };
    }
    case "call.started":
      return { ...base, tone: "info", title: p.mode === "live" ? "Live call started" : "Demo call started", detail: p.agent ?? "" };
    case "call.ended":
      return { ...base, tone: "info", title: "Call ended", detail: String(p.reason ?? "").replace(/_/g, " ") };
    case "error":
      return { ...base, tone: "bad", title: "Error", detail: p.message ?? "" };
    default:
      return null;
  }
}
