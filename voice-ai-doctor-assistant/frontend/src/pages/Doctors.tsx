import { useMemo, useState } from "react";
import type { Dashboard } from "../hooks/useDashboard";
import { IconSearch } from "../components/Icons";
import { initials } from "../services/format";
import type { Doctor } from "../types";

function DoctorCard({ doc, date }: { doc: Doctor; date: string }) {
  const [all, setAll] = useState(false);
  const days = doc.availability.filter((day) => !date || day.date === date);
  const shown = all ? days : days.slice(0, 1);
  return (
    <article className="doc card">
      <header>
        <div className="monogram" aria-hidden="true">{initials(doc.name)}</div>
        <div>
          <h3>{doc.name}</h3>
          <p className="doc-spec">{doc.speciality}</p>
        </div>
        <span className="fee">₹{doc.consultation_fee}</span>
      </header>
      <p className="doc-meta">{doc.qualifications}{doc.experience_years ? ` · ${doc.experience_years} yrs` : ""}</p>
      {days.length === 0 ? (
        <p className="empty small">No open slots{date ? " on this day" : " soon"}.</p>
      ) : (
        <div className="days">
          {shown.map((day) => (
            <div key={day.date} className="day">
              <h4>{day.date_label}<span>{day.total} open</span></h4>
              <div className="slots">
                {day.slots.map((s) => <span key={s.id} className="slot">{s.label}</span>)}
              </div>
            </div>
          ))}
          {days.length > 1 && (
            <button className="link" onClick={() => setAll((v) => !v)}>{all ? "Show less" : `Show ${days.length - 1} more day${days.length > 2 ? "s" : ""}`}</button>
          )}
        </div>
      )}
    </article>
  );
}

export function Doctors({ d }: { d: Dashboard }) {
  const [q, setQ] = useState("");
  const [spec, setSpec] = useState("All");
  const [date, setDate] = useState("");

  const dates = useMemo(() => {
    const seen = new Map<string, string>();
    d.doctors.forEach((doc) => doc.availability.forEach((day) => seen.set(day.date, day.date_label)));
    return [...seen.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [d.doctors]);

  const list = d.doctors.filter((doc) => {
    if (spec !== "All" && doc.speciality !== spec) return false;
    if (q && !`${doc.name} ${doc.speciality} ${doc.qualifications ?? ""}`.toLowerCase().includes(q.toLowerCase())) return false;
    if (date && !doc.availability.some((day) => day.date === date)) return false;
    return true;
  });

  return (
    <>
      <header className="page-head"><div><h1>Doctors</h1><p className="sub">Live availability. Slots disappear as soon as a call books them.</p></div></header>
      <div className="toolbar">
        <label className="search"><IconSearch size={16} /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search doctor or speciality" aria-label="Search doctors" /></label>
        <label className="select">
          <span className="sr">Day</span>
          <select value={date} onChange={(e) => setDate(e.target.value)} aria-label="Filter by day">
            <option value="">Any day</option>
            {dates.map(([iso, label]) => <option key={iso} value={iso}>{label}</option>)}
          </select>
        </label>
      </div>
      <div className="chips scroll" role="tablist" aria-label="Speciality">
        {["All", ...d.specialities].map((s) => (
          <button key={s} role="tab" aria-selected={spec === s} className={`chip ${spec === s ? "chip-on" : ""}`} onClick={() => setSpec(s)}>{s}</button>
        ))}
      </div>
      {d.loading ? <p className="empty">Loading doctors…</p> : list.length === 0 ? (
        <p className="empty">No doctors match. <button className="link" onClick={() => { setQ(""); setSpec("All"); setDate(""); }}>Clear filters</button></p>
      ) : (
        <div className="grid">{list.map((doc) => <DoctorCard key={doc.id} doc={doc} date={date} />)}</div>
      )}
    </>
  );
}
