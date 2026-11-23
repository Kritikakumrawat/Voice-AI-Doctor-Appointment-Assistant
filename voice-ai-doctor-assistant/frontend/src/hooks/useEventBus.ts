import { useCallback, useEffect, useRef, useState } from "react";
import { eventsUrl } from "../services/api";
import type { ServerEvent } from "../types";

const TYPES = [
  "call.started", "call.connected", "call.ended", "transcript", "speaking", "tool.started",
  "tool.finished", "appointment.booked", "appointment.cancelled", "slots.changed", "error",
];

export type Listener = (event: ServerEvent, isLive: boolean) => void;

/**
 * One EventSource for the whole app. Components subscribe with `subscribe(fn)`.
 * `isLive` is false for events replayed from before this page was opened.
 */
export function useEventBus() {
  const [connected, setConnected] = useState(false);
  const listeners = useRef(new Set<Listener>());
  const openedAt = useRef(Date.now());

  useEffect(() => {
    const es = new EventSource(eventsUrl());
    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false); // the browser reconnects and resumes via Last-Event-ID
    const onMessage = (m: MessageEvent) => {
      try {
        const event = JSON.parse(m.data) as ServerEvent;
        const isLive = Date.parse(event.ts) >= openedAt.current - 1500;
        listeners.current.forEach((fn) => fn(event, isLive));
      } catch {
        /* ignore malformed frames */
      }
    };
    TYPES.forEach((t) => es.addEventListener(t, onMessage));
    return () => es.close();
  }, []);

  const subscribe = useCallback((fn: Listener) => {
    listeners.current.add(fn);
    return () => {
      listeners.current.delete(fn);
    };
  }, []);

  return { connected, subscribe };
}

export type EventBus = ReturnType<typeof useEventBus>;
