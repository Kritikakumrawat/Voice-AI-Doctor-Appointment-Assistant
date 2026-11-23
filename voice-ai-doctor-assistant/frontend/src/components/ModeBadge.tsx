import type { AppConfig } from "../types";

export function ModeBadge({ config }: { config: AppConfig | null }) {
  if (!config) return <span className="badge badge-muted">Loading…</span>;
  return config.app_mode === "live" ? (
    <span className="badge badge-live"><i className="dot" />Live mode</span>
  ) : (
    <span className="badge badge-demo"><i className="dot" />Demo mode</span>
  );
}
