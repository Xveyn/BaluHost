import { Globe, ShieldOff, BarChart3, Layers } from "lucide-react";
import type { PiholeSummary } from "../../api/pihole";

interface PiholeSummaryCardsProps {
  summary: PiholeSummary | null;
  loading: boolean;
}

function formatNumber(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return n.toLocaleString();
}

interface StatCardProps {
  label: string;
  value: string;
  icon: React.ReactNode;
  accent?: string;
  loading: boolean;
  extra?: React.ReactNode;
}

function StatCard({ label, value, icon, accent, loading, extra }: StatCardProps) {
  return (
    <div className="rounded-xl border border-slate-700/50 bg-slate-800/60 p-4">
      <div className="flex items-center justify-between">
        <span className="text-sm text-slate-400">{label}</span>
        <span className={accent ?? "text-slate-400"}>{icon}</span>
      </div>
      {loading ? (
        <div className="mt-2 h-8 w-28 animate-pulse rounded bg-slate-700" />
      ) : (
        <p className={`mt-2 text-2xl font-bold ${accent ?? "text-slate-100"}`}>
          {value}
        </p>
      )}
      {extra}
    </div>
  );
}

export default function PiholeSummaryCards({
  summary,
  loading,
}: PiholeSummaryCardsProps) {
  const s = summary ?? { total_queries: 0, blocked_queries: 0, percent_blocked: 0, unique_domains: 0 };
  const pctBlocked = s.total_queries > 0
    ? ((s.blocked_queries / s.total_queries) * 100).toFixed(1)
    : "0.0";

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <StatCard
        label="Total Queries"
        value={formatNumber(s.total_queries)}
        icon={<Globe className="h-5 w-5" />}
        loading={loading}
      />
      <StatCard
        label="Blocked Queries"
        value={formatNumber(s.blocked_queries)}
        icon={<ShieldOff className="h-5 w-5" />}
        accent="text-red-400"
        loading={loading}
      />
      <StatCard
        label="% Blocked"
        value={`${pctBlocked}%`}
        icon={<BarChart3 className="h-5 w-5" />}
        accent="text-amber-400"
        loading={loading}
        extra={
          !loading ? (
            <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-slate-700">
              <div
                className="h-full rounded-full bg-amber-500 transition-all"
                style={{ width: `${Math.min(parseFloat(pctBlocked), 100)}%` }}
              />
            </div>
          ) : null
        }
      />
      <StatCard
        label="Unique Domains"
        value={formatNumber(s.unique_domains)}
        icon={<Layers className="h-5 w-5" />}
        accent="text-sky-400"
        loading={loading}
      />
    </div>
  );
}
