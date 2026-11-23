import { useEffect, useState, type ReactNode } from "react";
import { IconActivity, IconCalendar, IconCross, IconDoctors, IconOverview, IconPhone, IconVolume, IconVolumeOff } from "./components/Icons";
import { ModeBadge } from "./components/ModeBadge";
import { PhoneCall } from "./components/PhoneCall";
import { useCall } from "./hooks/useCall";
import { useDashboard } from "./hooks/useDashboard";
import { useEventBus } from "./hooks/useEventBus";
import { ToastProvider } from "./hooks/useToasts";
import { Activity } from "./pages/Activity";
import { Appointments } from "./pages/Appointments";
import { Doctors } from "./pages/Doctors";
import { Overview } from "./pages/Overview";
import { setSoundEnabled, soundEnabled } from "./services/sound";

type Page = "overview" | "doctors" | "appointments" | "activity";
const PAGES: Page[] = ["overview", "doctors", "appointments", "activity"];
const readHash = (): Page => {
  const h = window.location.hash.replace("#/", "") as Page;
  return PAGES.includes(h) ? h : "overview";
};

function Shell() {
  const bus = useEventBus();
  const d = useDashboard(bus);
  const call = useCall(d.config, bus);
  const [page, setPage] = useState<Page>(readHash);
  const [phoneOpen, setPhoneOpen] = useState(false);
  const [sound, setSound] = useState(soundEnabled());

  useEffect(() => {
    const onHash = () => setPage(readHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const go = (p: Page) => { window.location.hash = `#/${p}`; };
  const openCall = () => { setPhoneOpen(true); void call.start(); };

  const nav: { id: Page; label: string; icon: ReactNode; badge?: number }[] = [
    { id: "overview", label: "Overview", icon: <IconOverview /> },
    { id: "doctors", label: "Doctors", icon: <IconDoctors /> },
    { id: "appointments", label: "Appointments", icon: <IconCalendar />, badge: d.overview?.booked },
    { id: "activity", label: "Activity", icon: <IconActivity /> },
  ];

  return (
    <div className="app">
      <aside className="rail">
        <div className="brand"><span className="brand-mark"><IconCross size={18} /></span><div><strong>Meridian</strong><span>Front desk</span></div></div>
        <nav aria-label="Main">
          {nav.map((n) => (
            <button key={n.id} className={`nav ${page === n.id ? "nav-on" : ""}`} aria-current={page === n.id ? "page" : undefined} onClick={() => go(n.id)}>
              {n.icon}<span>{n.label}</span>{n.badge ? <em>{n.badge}</em> : null}
            </button>
          ))}
        </nav>
        <div className="rail-foot">
          <button className="rail-btn" onClick={() => { const v = !sound; setSound(v); setSoundEnabled(v); }} aria-pressed={sound}>
            {sound ? <IconVolume size={16} /> : <IconVolumeOff size={16} />}Call sounds {sound ? "on" : "off"}
          </button>
          <p className={`stream ${bus.connected ? "stream-ok" : "stream-bad"}`}><i />{bus.connected ? "Live feed connected" : "Reconnecting to server…"}</p>
        </div>
      </aside>

      <main className="main">
        <div className="topbar">
          <ModeBadge config={d.config} />
          <button className="btn btn-primary" onClick={openCall}><IconPhone size={18} />Try call</button>
        </div>
        {d.error && (
          <div className="banner" role="alert">
            <span>{d.error}</span><button className="link" onClick={() => void d.reload()}>Retry</button>
          </div>
        )}
        {page === "overview" && <Overview d={d} onCall={openCall} onNav={go} />}
        {page === "doctors" && <Doctors d={d} />}
        {page === "appointments" && <Appointments d={d} />}
        {page === "activity" && <Activity d={d} />}
      </main>

      <PhoneCall call={call} config={d.config} open={phoneOpen} onClose={() => setPhoneOpen(false)} />
    </div>
  );
}

export default function App() {
  return (
    <ToastProvider>
      <Shell />
    </ToastProvider>
  );
}
