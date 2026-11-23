import type { CallCard } from "../types";
import { IconCheck, IconX } from "./Icons";

export function ConfirmCard({ card, onClose }: { card: CallCard; onClose: () => void }) {
  const a = card.appointment;
  const booked = card.kind === "booked";
  return (
    <div className={`confirm ${booked ? "confirm-ok" : "confirm-cancel"}`} role="status">
      <div className="confirm-head">
        <span className="confirm-badge">{booked ? <IconCheck size={16} /> : <IconX size={16} />}</span>
        <strong>{booked ? "Appointment booked" : "Appointment cancelled"}</strong>
        <button className="confirm-close" onClick={onClose} aria-label="Dismiss">×</button>
      </div>
      <dl>
        <div><dt>Doctor</dt><dd>{a.doctor_name}</dd></div>
        <div><dt>When</dt><dd>{a.date_label} · {a.time_label}</dd></div>
        <div><dt>ID</dt><dd className="mono">{a.id}</dd></div>
        <div><dt>Phone</dt><dd className="mono">{a.phone_masked}</dd></div>
        {booked && <div><dt>Fee</dt><dd>₹{a.consultation_fee}</dd></div>}
      </dl>
    </div>
  );
}
