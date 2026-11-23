import type { ServerEvent } from "../types";
import { clockTime, describeEvent } from "../services/format";

export function Feed({ events, limit, empty }: { events: ServerEvent[]; limit?: number; empty: string }) {
  const items = events.map(describeEvent).filter((x): x is NonNullable<typeof x> => x !== null).slice(0, limit ?? 100);
  if (items.length === 0) return <p className="empty">{empty}</p>;
  return (
    <ol className="feed">
      {items.map((it) => (
        <li key={it.key} className={`feed-item tone-${it.tone}`}>
          <i className="feed-dot" />
          <div>
            <p className="feed-title">{it.title}</p>
            {it.detail && <p className="feed-detail">{it.detail}</p>}
          </div>
          <time>{clockTime(it.ts)}</time>
        </li>
      ))}
    </ol>
  );
}
