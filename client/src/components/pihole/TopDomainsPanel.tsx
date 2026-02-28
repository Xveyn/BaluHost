import { Globe, ShieldOff } from "lucide-react";
import type { DomainEntry } from "../../api/pihole";

interface TopDomainsPanelProps {
  topPermitted: DomainEntry[];
  topBlocked: DomainEntry[];
  loading: boolean;
}

function DomainList({
  title,
  icon,
  domains,
  accent,
  barColor,
  loading,
}: {
  title: string;
  icon: React.ReactNode;
  domains: DomainEntry[];
  accent: string;
  barColor: string;
  loading: boolean;
}) {
  const maxCount = domains.length > 0
    ? Math.max(...domains.map((d) => d.count))
    : 1;

  return (
    <div className="flex-1 rounded-xl border border-slate-700/50 bg-slate-800/60 p-4">
      <div className="mb-3 flex items-center gap-2">
        <span className={accent}>{icon}</span>
        <h3 className="text-sm font-medium text-slate-300">{title}</h3>
      </div>

      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="space-y-1.5">
              <div className="h-3 w-32 animate-pulse rounded bg-slate-700" />
              <div className="h-2 w-full animate-pulse rounded bg-slate-700" />
            </div>
          ))}
        </div>
      ) : domains.length === 0 ? (
        <p className="py-6 text-center text-sm text-slate-500">No data</p>
      ) : (
        <ol className="space-y-2.5">
          {domains.map((entry, i) => {
            const pct = (entry.count / maxCount) * 100;
            return (
              <li key={i}>
                <div className="flex items-baseline justify-between gap-2">
                  <span className="truncate font-mono text-xs text-slate-200">
                    {entry.domain}
                  </span>
                  <span className="shrink-0 text-xs text-slate-500">
                    {entry.count.toLocaleString()}
                  </span>
                </div>
                <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-slate-700/60">
                  <div
                    className={`h-full rounded-full ${barColor} transition-all`}
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

export default function TopDomainsPanel({
  topPermitted,
  topBlocked,
  loading,
}: TopDomainsPanelProps) {
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <DomainList
        title="Top Permitted"
        icon={<Globe className="h-4 w-4" />}
        domains={topPermitted}
        accent="text-emerald-400"
        barColor="bg-emerald-500"
        loading={loading}
      />
      <DomainList
        title="Top Blocked"
        icon={<ShieldOff className="h-4 w-4" />}
        domains={topBlocked}
        accent="text-red-400"
        barColor="bg-red-500"
        loading={loading}
      />
    </div>
  );
}
