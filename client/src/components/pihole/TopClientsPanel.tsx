import { Monitor } from "lucide-react";
import type { ClientEntry } from "../../api/pihole";

interface TopClientsPanelProps {
  clients: ClientEntry[];
  loading: boolean;
}

export default function TopClientsPanel({
  clients,
  loading,
}: TopClientsPanelProps) {
  const maxCount = clients.length > 0
    ? Math.max(...clients.map((c) => c.count))
    : 1;

  return (
    <div className="rounded-xl border border-slate-700/50 bg-slate-800/60 p-4">
      <div className="mb-3 flex items-center gap-2">
        <Monitor className="h-4 w-4 text-sky-400" />
        <h3 className="text-sm font-medium text-slate-300">Top Clients</h3>
      </div>

      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="space-y-1.5">
              <div className="h-3 w-36 animate-pulse rounded bg-slate-700" />
              <div className="h-2 w-full animate-pulse rounded bg-slate-700" />
            </div>
          ))}
        </div>
      ) : clients.length === 0 ? (
        <p className="py-6 text-center text-sm text-slate-500">No data</p>
      ) : (
        <ol className="space-y-2.5">
          {clients.map((client, i) => {
            const pct = (client.count / maxCount) * 100;
            return (
              <li key={i}>
                <div className="flex items-baseline justify-between gap-2">
                  <div className="flex items-baseline gap-2 truncate">
                    <span className="font-mono text-xs text-slate-200">
                      {client.client}
                    </span>
                    {client.name && (
                      <span className="text-xs text-slate-500">
                        ({client.name})
                      </span>
                    )}
                  </div>
                  <span className="shrink-0 text-xs text-slate-500">
                    {client.count.toLocaleString()}
                  </span>
                </div>
                <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-slate-700/60">
                  <div
                    className="h-full rounded-full bg-sky-500 transition-all"
                    style={{ width: `${pct}%` }}
                  />
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
