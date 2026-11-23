import type { Dashboard } from "../hooks/useDashboard";
import { Feed } from "../components/Feed";

export function Activity({ d }: { d: Dashboard }) {
  return (
    <>
      <header className="page-head">
        <div><h1>Live activity</h1><p className="sub">What the assistant did, as it happens.</p></div>
        <button className="btn btn-ghost" onClick={d.clearFeed} disabled={d.feed.length === 0}>Clear</button>
      </header>
      <section className="card"><Feed events={d.feed} empty="No activity yet. Start a call to see availability checks, bookings and cancellations here." /></section>
    </>
  );
}
