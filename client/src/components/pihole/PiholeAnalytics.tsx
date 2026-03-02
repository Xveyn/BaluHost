import { useState, useEffect, useCallback } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import {
  Globe,
  ShieldOff,
  Clock,
  Users,
  RefreshCw,
} from "lucide-react";
import toast from "react-hot-toast";
import {
  getStoredStats,
  getStoredTopDomains,
  getStoredTopBlocked,
  getStoredTopClients,
  getStoredHistory,
  type StoredStatsResponse,
  type StoredDomainEntry,
  type StoredClientEntry,
  type HourlyCountEntry,
  type Period,
} from "../../api/pihole";

function formatNumber(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return n.toLocaleString();
}

function formatHour(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

const PERIODS: { key: Period; label: string }[] = [
  { key: "24h", label: "24 Hours" },
  { key: "7d", label: "7 Days" },
  { key: "30d", label: "30 Days" },
];

export default function PiholeAnalytics() {
  const [period, setPeriod] = useState<Period>("24h");
  const [stats, setStats] = useState<StoredStatsResponse | null>(null);
  const [topDomains, setTopDomains] = useState<StoredDomainEntry[]>([]);
  const [topBlocked, setTopBlocked] = useState<StoredDomainEntry[]>([]);
  const [topClients, setTopClients] = useState<StoredClientEntry[]>([]);
  const [history, setHistory] = useState<HourlyCountEntry[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [s, d, b, c, h] = await Promise.all([
        getStoredStats(period),
        getStoredTopDomains(10, period),
        getStoredTopBlocked(10, period),
        getStoredTopClients(10, period),
        getStoredHistory(period),
      ]);
      setStats(s);
      setTopDomains(d.top_domains);
      setTopBlocked(b.top_blocked);
      setTopClients(c.top_clients);
      setHistory(h.history);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to load analytics");
    } finally {
      setLoading(false);
    }
  }, [period]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const chartData = history.map((e) => ({
    time: formatHour(e.hour),
    forwarded: e.forwarded_queries,
    cached: e.cached_queries,
    blocked: e.blocked_queries,
  }));

  return (
    <div className="space-y-6">
      {/* Period Selector + Refresh */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-lg font-medium text-slate-200">DNS Analytics</h3>
        <div className="flex items-center gap-2">
          <button
            onClick={fetchData}
            disabled={loading}
            className="rounded-lg border border-slate-700 p-1.5 text-slate-400 hover:bg-slate-700/50 hover:text-slate-200 transition-colors disabled:opacity-30"
            title="Refresh"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          </button>
          <div className="flex gap-1 rounded-lg border border-slate-700/50 bg-slate-800/40 p-1">
            {PERIODS.map((p) => (
              <button
                key={p.key}
                onClick={() => setPeriod(p.key)}
                className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                  period === p.key
                    ? "bg-slate-700/80 text-white"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <SummaryCard
          label="Total Queries"
          value={stats ? formatNumber(stats.total_queries) : "-"}
          icon={<Globe className="h-5 w-5" />}
          loading={loading}
        />
        <SummaryCard
          label="Block Rate"
          value={stats ? `${stats.block_rate}%` : "-"}
          icon={<ShieldOff className="h-5 w-5" />}
          accent="text-red-400"
          loading={loading}
        />
        <SummaryCard
          label="Avg Response"
          value={
            stats?.avg_response_time_ms != null
              ? `${stats.avg_response_time_ms.toFixed(1)} ms`
              : "-"
          }
          icon={<Clock className="h-5 w-5" />}
          accent="text-emerald-400"
          loading={loading}
        />
        <SummaryCard
          label="Unique Clients"
          value={stats ? formatNumber(stats.unique_clients) : "-"}
          icon={<Users className="h-5 w-5" />}
          accent="text-sky-400"
          loading={loading}
        />
      </div>

      {/* Timeline Chart */}
      <div className="rounded-xl border border-slate-700/50 bg-slate-800/60 p-4">
        <h3 className="mb-4 text-sm font-medium text-slate-300">
          Queries Over Time
        </h3>
        {loading ? (
          <div className="flex h-64 items-center justify-center">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-sky-500 border-t-transparent" />
          </div>
        ) : chartData.length === 0 ? (
          <div className="flex h-64 items-center justify-center text-sm text-slate-500">
            No data yet — the collector needs time to gather queries.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={chartData}>
              <defs>
                <linearGradient id="gradFwd" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#0ea5e9" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#0ea5e9" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="gradCached" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#a78bfa" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#a78bfa" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="gradBlk" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#f43f5e" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#f43f5e" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis
                dataKey="time"
                tick={{ fontSize: 11, fill: "#94a3b8" }}
                stroke="#475569"
              />
              <YAxis
                tick={{ fontSize: 11, fill: "#94a3b8" }}
                stroke="#475569"
                width={50}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#1e293b",
                  border: "1px solid rgba(51,65,85,0.5)",
                  borderRadius: "0.5rem",
                  fontSize: "0.8rem",
                }}
                labelStyle={{ color: "#94a3b8" }}
                itemStyle={{ color: "#e2e8f0" }}
              />
              <Area
                type="monotone"
                dataKey="forwarded"
                name="Forwarded"
                stackId="1"
                stroke="#0ea5e9"
                fill="url(#gradFwd)"
                strokeWidth={2}
              />
              <Area
                type="monotone"
                dataKey="cached"
                name="Cached"
                stackId="1"
                stroke="#a78bfa"
                fill="url(#gradCached)"
                strokeWidth={2}
              />
              <Area
                type="monotone"
                dataKey="blocked"
                name="Blocked"
                stackId="1"
                stroke="#f43f5e"
                fill="url(#gradBlk)"
                strokeWidth={2}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Top Tables */}
      <div className="grid gap-6 lg:grid-cols-3">
        <TopTable title="Top Domains" items={topDomains.map((d) => ({ name: d.domain, count: d.count }))} loading={loading} />
        <TopTable title="Top Blocked" items={topBlocked.map((d) => ({ name: d.domain, count: d.count }))} loading={loading} accent="text-red-400" />
        <TopTable title="Top Clients" items={topClients.map((c) => ({ name: c.client, count: c.count }))} loading={loading} accent="text-sky-400" />
      </div>
    </div>
  );
}

function SummaryCard({
  label,
  value,
  icon,
  accent,
  loading,
}: {
  label: string;
  value: string;
  icon: React.ReactNode;
  accent?: string;
  loading: boolean;
}) {
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
    </div>
  );
}

function TopTable({
  title,
  items,
  loading,
  accent,
}: {
  title: string;
  items: { name: string; count: number }[];
  loading: boolean;
  accent?: string;
}) {
  return (
    <div className="rounded-xl border border-slate-700/50 bg-slate-800/60 p-4">
      <h4 className="mb-3 text-sm font-medium text-slate-300">{title}</h4>
      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-5 animate-pulse rounded bg-slate-700" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <p className="text-sm text-slate-500">No data</p>
      ) : (
        <div className="space-y-1.5">
          {items.map((item, i) => (
            <div key={i} className="flex items-center justify-between text-sm">
              <span className="truncate text-slate-300 mr-2">{item.name}</span>
              <span className={`shrink-0 font-mono ${accent ?? "text-slate-400"}`}>
                {item.count.toLocaleString()}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
