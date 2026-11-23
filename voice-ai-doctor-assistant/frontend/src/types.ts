export type AppMode = "mock" | "live";

export interface AppConfig {
  app_mode: AppMode;
  clinic_name: string;
  live_ready: boolean;
  missing: string[];
  stack: { transport: string; stt: string; llm: string; tts: string };
}

export interface Slot {
  id: number;
  date: string;
  start_time: string;
  end_time: string;
  label: string;
}

export interface DayAvailability {
  date: string;
  date_label: string;
  slots: Slot[];
  total: number;
}

export interface Doctor {
  id: string;
  name: string;
  speciality: string;
  qualifications: string | null;
  experience_years: number | null;
  consultation_fee: number;
  currency: string;
  availability: DayAvailability[];
  open_slots: number;
}

export type AppointmentStatus = "booked" | "cancelled";

export interface Appointment {
  id: string;
  doctor_id: string;
  doctor_name: string;
  speciality: string;
  consultation_fee: number;
  patient_name: string | null;
  date: string;
  start_time: string;
  end_time: string;
  date_label: string;
  time_label: string;
  phone_masked: string;
  phone?: string;
  status: AppointmentStatus;
  created_at: string;
  updated_at: string;
}

export interface Overview {
  doctors: number;
  open_slots: number;
  booked: number;
  cancelled: number;
  active_calls: number;
  next_appointment: Appointment | null;
}

export type ServerEventType =
  | "call.started" | "call.connected" | "call.ended" | "transcript" | "speaking"
  | "tool.started" | "tool.finished" | "appointment.booked" | "appointment.cancelled"
  | "slots.changed" | "error";

export interface ServerEvent {
  id: number;
  type: ServerEventType;
  ts: string;
  call_id: string | null;
  payload: Record<string, any>;
}

export type CallState = "idle" | "connecting" | "connected" | "ended" | "error";

export interface TranscriptLine {
  key: string;
  role: "user" | "assistant";
  text: string;
  final: boolean;
  ts: string;
}

export interface CallCard {
  kind: "booked" | "cancelled";
  appointment: Appointment;
}
