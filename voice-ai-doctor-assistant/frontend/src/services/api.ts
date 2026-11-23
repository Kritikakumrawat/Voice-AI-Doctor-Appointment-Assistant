import type { Appointment, AppConfig, DayAvailability, Doctor, Overview } from "../types";

const BASE = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "") ?? "";

export class ApiError extends Error {
  code: string;
  status: number;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(0, "network", "Can't reach the server. Is the backend running?");
  }
  const text = await res.text();
  const body = text ? JSON.parse(text) : {};
  if (!res.ok) {
    const e = body?.error;
    throw new ApiError(res.status, e?.code ?? "error", e?.message ?? `Request failed (${res.status})`);
  }
  return body as T;
}

export const eventsUrl = (since?: number) => `${BASE}/api/events${since ? `?since=${since}` : ""}`;

export const api = {
  config: () => request<AppConfig>("/api/config"),
  overview: () => request<Overview>("/api/overview"),
  doctors: () => request<{ doctors: Doctor[]; specialities: string[] }>("/api/doctors?days=7"),
  availability: (id: string, date?: string) =>
    request<{ availability: DayAvailability[] }>(`/api/doctors/${id}/availability${date ? `?date=${date}` : ""}`),
  appointments: (revealPhone: boolean) =>
    request<{ appointments: Appointment[] }>(`/api/appointments${revealPhone ? "?reveal_phone=true" : ""}`),
  startCall: () =>
    request<{ call_id: string; mode: string; greeting: string }>("/api/calls", { method: "POST" }),
  say: (callId: string, text: string) =>
    request<{ reply: string; ended: boolean }>(`/api/calls/${callId}/say`, {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
  endCall: (callId: string) => request<unknown>(`/api/calls/${callId}/end`, { method: "POST" }),
  webrtcUrl: `${BASE}/api/offer`,
};
