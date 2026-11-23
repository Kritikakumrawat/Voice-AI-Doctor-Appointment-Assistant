import { useState } from "react";
import type { Dashboard } from "../hooks/useDashboard";
import { IconEye, IconEyeOff, IconSearch } from "../components/Icons";
import type { AppointmentStatus } from "../types";

type Filter = "all" | AppointmentStatus;

export function Appointments({ d }: { d: Dashboard }) {
  const [filter, setFilter] = useState<Filter>("all");
  const [q, setQ] = useState("");
  const list = d.appointments.filter((a) => {
    if (filter !== "all" && a.status !== filter) return false;
    if (!q) return true;
    const hay = `${a.id} ${a.doctor_name} ${a.speciality} ${a.patient_name ?? ""}`.toLowerCase();
    return hay.includes(q.toLowerCase());
  });
  const count = (s: Filter) => (s === "all" ? d.appointments.length : d.appointments.filter((a) => a.status === s).length);

  return (
    <>
      <header className="page-head">
        <div><h1>Appointments</h1><p className="sub">Rows light up when the assistant books or cancels.</p></div>
        <button className="btn btn-ghost" onClick={() => d.setRevealPhone(!d.revealPhone)} aria-pressed={d.revealPhone}>
          {d.revealPhone ? <IconEyeOff size={16} /> : <IconEye size={16} />}{d.revealPhone ? "Hide numbers" : "Show full numbers"}
        </button>
      </header>
      <div className="toolbar">
        <div className="seg" role="tablist" aria-label="Status">
          {(["all", "booked", "cancelled"] as Filter[]).map((s) => (
            <button key={s} role="tab" aria-selected={filter === s} className={filter === s ? "seg-on" : ""} onClick={() => setFilter(s)}>
              {s[0].toUpperCase() + s.slice(1)} <span>{count(s)}</span>
            </button>
          ))}
        </div>
        <label className="search"><IconSearch size={16} /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search ID, doctor, patient" aria-label="Search appointments" /></label>
      </div>

      {d.loading ? <p className="empty">Loading appointments…</p> : list.length === 0 ? (
        <p className="empty">{d.appointments.length === 0 ? "No appointments yet. Start a call and book one." : "Nothing matches these filters."}</p>
      ) : (
        <div className="table-wrap card">
          <table className="table">
            <thead><tr><th>ID</th><th>Patient</th><th>Doctor</th><th>When</th><th>Phone</th><th>Status</th></tr></thead>
            <tbody>
              {list.map((a) => (
                <tr key={a.id} className={d.highlight[a.id] ? `flash-${d.highlight[a.id]}` : ""}>
                  <td data-label="ID" className="mono">{a.id}</td>
                  <td data-label="Patient">{a.patient_name ?? <span className="muted">Caller</span>}</td>
                  <td data-label="Doctor"><strong>{a.doctor_name}</strong><span className="muted block">{a.speciality}</span></td>
                  <td data-label="When">{a.date_label}<span className="mono block">{a.time_label}</span></td>
                  <td data-label="Phone" className="mono">{d.revealPhone && a.phone ? a.phone : a.phone_masked}</td>
                  <td data-label="Status"><span className={`pill pill-${a.status}`}>{a.status}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
