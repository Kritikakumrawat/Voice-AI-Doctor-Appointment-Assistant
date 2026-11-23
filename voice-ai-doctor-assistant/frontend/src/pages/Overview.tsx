import type { Dashboard } from "../hooks/useDashboard";
import { Feed } from "../components/Feed";
import { IconPhone } from "../components/Icons";
import { ModeBadge } from "../components/ModeBadge";
import { todayLong } from "../services/format";

export function Overview({ d, onCall, onNav }: { d: Dashboard; onCall: () => void; onNav: (p: "appointments" | "activity") => void }) {
  const { config, overview, appointments } = d;
  const upcoming = appointments
    .filter((a) => a.status === "booked")
    .sort((a, b) => (a.date + a.start_time).localeCompare(b.date + b.start_time))
    .slice(0, 5);
  const live = config?.app_mode === "live";
  const stack: [string, string][] = config
    ? [["Transport", config.stack.transport], ["Speech to text", config.stack.stt], ["Language model", config.stack.llm], ["Text to speech", config.stack.tts]]
    : [];

  return (
    <>
      <header className="page-head">
        <div>
          <h1>Front desk</h1>
          <p className="sub">{todayLong()}</p>
        </div>
      </header>

      <section className="status card">
        <div className="status-main">
          <ModeBadge config={config} />
          <h2>{live ? "The voice assistant is answering calls." : "The assistant is running in demo mode."}</h2>
          <p>
            {live
              ? "Callers are identified by the number they say aloud. Every booking is checked against real availability."
              : "A simple scripted agent stands in for the LLM, so no API keys are needed. Availability, bookings and cancellations are still real."}
          </p>
          {config && config.missing.length > 0 && (
            <p className="warn-text">Live mode is missing: {config.missing.join("; ")}</p>
          )}
          <button className="btn btn-primary" onClick={onCall}><IconPhone size={18} />Try call</button>
        </div>
        <dl className="stack">
          {stack.map(([k, v]) => (<div key={k}><dt>{k}</dt><dd>{v}</dd></div>))}
        </dl>
      </section>

      <section className="stats" aria-label="Summary">
        <div className="stat"><span className="stat-n">{overview?.open_slots ?? "–"}</span><span className="stat-l">Open slots</span></div>
        <div className="stat"><span className="stat-n">{overview?.booked ?? "–"}</span><span className="stat-l">Booked</span></div>
        <div className="stat"><span className="stat-n">{overview?.cancelled ?? "–"}</span><span className="stat-l">Cancelled</span></div>
        <div className="stat"><span className="stat-n">{overview?.doctors ?? "–"}</span><span className="stat-l">Doctors</span></div>
      </section>

      <div className="two-col">
        <section className="card">
          <div className="card-head"><h3>Upcoming</h3><button className="link" onClick={() => onNav("appointments")}>All appointments</button></div>
          {upcoming.length === 0 ? <p className="empty">No upcoming appointments yet. Place a call to book one.</p> : (
            <ul className="mini-list">
              {upcoming.map((a) => (
                <li key={a.id} className={d.highlight[a.id] ? "flash-" + d.highlight[a.id] : ""}>
                  <div><strong>{a.doctor_name}</strong><span>{a.speciality}</span></div>
                  <div className="right"><span>{a.date_label}</span><span className="mono">{a.time_label}</span></div>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="card">
          <div className="card-head"><h3>Live activity</h3><button className="link" onClick={() => onNav("activity")}>See all</button></div>
          <Feed events={d.feed} limit={7} empty="Nothing yet. Activity from calls appears here as it happens." />
        </section>
      </div>
    </>
  );
}
