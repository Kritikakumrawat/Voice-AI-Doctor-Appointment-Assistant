import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../services/api";
import type { AppConfig, Appointment, Doctor, Overview, ServerEvent } from "../types";
import type { EventBus } from "./useEventBus";
import { useToast } from "./useToasts";

const FEED_TYPES = new Set(["call.started", "call.ended", "tool.finished", "appointment.booked", "appointment.cancelled", "error"]);

export function useDashboard(bus: EventBus) {
  const toast = useToast();
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [doctors, setDoctors] = useState<Doctor[]>([]);
  const [specialities, setSpecialities] = useState<string[]>([]);
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [revealPhone, setRevealPhone] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [feed, setFeed] = useState<ServerEvent[]>([]);
  const [highlight, setHighlight] = useState<Record<string, "booked" | "cancelled">>({});
  const revealRef = useRef(false);
  revealRef.current = revealPhone;

  const loadAll = useCallback(async () => {
    try {
      const [ov, docs, appts] = await Promise.all([api.overview(), api.doctors(), api.appointments(revealRef.current)]);
      setOverview(ov);
      setDoctors(docs.doctors);
      setSpecialities(docs.specialities);
      setAppointments(appts.appointments);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong while loading data.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    api.config().then(setConfig).catch((e) => setError(e instanceof ApiError ? e.message : "Can't load configuration."));
    void loadAll();
  }, [loadAll]);

  // Reload appointments when the "show full numbers" switch changes.
  useEffect(() => {
    api.appointments(revealPhone).then((r) => setAppointments(r.appointments)).catch(() => {});
  }, [revealPhone]);

  const refreshTimer = useRef<number | null>(null);
  const scheduleRefresh = useCallback(() => {
    if (refreshTimer.current !== null) window.clearTimeout(refreshTimer.current);
    refreshTimer.current = window.setTimeout(() => void loadAll(), 150);
  }, [loadAll]);

  useEffect(
    () =>
      bus.subscribe((event, isLive) => {
        if (FEED_TYPES.has(event.type)) setFeed((f) => [event, ...f].slice(0, 150));
        if (event.type === "appointment.booked" || event.type === "appointment.cancelled" || event.type === "slots.changed") {
          scheduleRefresh();
        }
        if (event.type === "appointment.booked" || event.type === "appointment.cancelled") {
          const appt = event.payload.appointment as Appointment | undefined;
          if (appt && isLive) {
            const kind = event.type === "appointment.booked" ? "booked" : "cancelled";
            setHighlight((h) => ({ ...h, [appt.id]: kind }));
            window.setTimeout(
              () =>
                setHighlight((h) => {
                  const { [appt.id]: _gone, ...rest } = h;
                  return rest;
                }),
              6000,
            );
          }
        }
        if (event.type === "error" && isLive) toast("error", event.payload.message ?? "Something went wrong.");
      }),
    [bus, scheduleRefresh, toast],
  );

  // Re-sync after the live stream reconnects (events may have been missed while it was down).
  const hadConnection = useRef(false);
  const lostConnection = useRef(false);
  useEffect(() => {
    if (bus.connected) {
      if (hadConnection.current && lostConnection.current) void loadAll();
      hadConnection.current = true;
      lostConnection.current = false;
    } else if (hadConnection.current) {
      lostConnection.current = true;
    }
  }, [bus.connected, loadAll]);

  return {
    config, overview, doctors, specialities, appointments, revealPhone, setRevealPhone,
    loading, error, feed, clearFeed: () => setFeed([]), highlight, reload: loadAll,
  };
}

export type Dashboard = ReturnType<typeof useDashboard>;
