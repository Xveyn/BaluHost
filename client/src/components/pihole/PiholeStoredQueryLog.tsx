import { useState, useEffect, useCallback } from "react";
import { Search, ChevronLeft, ChevronRight } from "lucide-react";
import toast from "react-hot-toast";
import {
  getStoredQueries,
  type StoredQueryEntry,
  type Period,
} from "../../api/pihole";

const STATUS_COLORS: Record<string, string> = {
  FORWARDED: "text-emerald-400",
  BLOCKED: "text-red-400",
  CACHED: "text-violet-400",
};

const PERIODS: { key: Period; label: string }[] = [
  { key: "24h", label: "24h" },
  { key: "7d", label: "7d" },
  { key: "30d", label: "30d" },
];

export default function PiholeStoredQueryLog() {
  const [queries, setQueries] = useState<StoredQueryEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState<Period>("24h");
  const [domainFilter, setDomainFilter] = useState("");
  const [clientFilter, setClientFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  const pageSize = 100;

  const fetchQueries = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = {
        page,
        page_size: pageSize,
        period,
      };
      if (domainFilter) params.domain = domainFilter;
      if (clientFilter) params.client = clientFilter;
      if (statusFilter) params.status = statusFilter;

      const res = await getStoredQueries(params as any);
      setQueries(res.queries);
      setTotal(res.total);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to load stored queries");
    } finally {
      setLoading(false);
    }
  }, [page, period, domainFilter, clientFilter, statusFilter]);

  useEffect(() => {
    fetchQueries();
  }, [fetchQueries]);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  const handleSearch = () => {
    setPage(1);
    fetchQueries();
  };

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex-1 min-w-[140px]">
          <label className="mb-1 block text-xs text-slate-400">Domain</label>
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
            <input
              type="text"
              value={domainFilter}
              onChange={(e) => setDomainFilter(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              placeholder="Filter by domain..."
              className="w-full rounded-lg border border-slate-700 bg-slate-800/80 py-2 pl-9 pr-3 text-sm text-slate-200 placeholder-slate-500 focus:border-sky-500 focus:outline-none"
            />
          </div>
        </div>
        <div className="min-w-[100px]">
          <label className="mb-1 block text-xs text-slate-400">Client</label>
          <input
            type="text"
            value={clientFilter}
            onChange={(e) => setClientFilter(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            placeholder="IP address"
            className="w-full rounded-lg border border-slate-700 bg-slate-800/80 py-2 px-3 text-sm text-slate-200 placeholder-slate-500 focus:border-sky-500 focus:outline-none"
          />
        </div>
        <div className="min-w-[120px]">
          <label className="mb-1 block text-xs text-slate-400">Status</label>
          <select
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
            className="w-full rounded-lg border border-slate-700 bg-slate-800/80 py-2 px-3 text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
          >
            <option value="">All</option>
            <option value="FORWARDED">Forwarded</option>
            <option value="BLOCKED">Blocked</option>
            <option value="CACHED">Cached</option>
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs text-slate-400">Period</label>
          <div className="flex gap-1 rounded-lg border border-slate-700 bg-slate-800/80 p-0.5">
            {PERIODS.map((p) => (
              <button
                key={p.key}
                onClick={() => { setPeriod(p.key); setPage(1); }}
                className={`rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors ${
                  period === p.key
                    ? "bg-slate-700 text-white"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>
        <button
          onClick={handleSearch}
          className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 transition-colors"
        >
          Search
        </button>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-xl border border-slate-700/50 bg-slate-800/60">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-700/50 text-left text-xs text-slate-400">
              <th className="px-4 py-3">Time</th>
              <th className="px-4 py-3">Domain</th>
              <th className="px-4 py-3">Client</th>
              <th className="px-4 py-3">Type</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3 text-right">Response</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              Array.from({ length: 10 }).map((_, i) => (
                <tr key={i} className="border-b border-slate-700/30">
                  {Array.from({ length: 6 }).map((_, j) => (
                    <td key={j} className="px-4 py-2.5">
                      <div className="h-4 animate-pulse rounded bg-slate-700" />
                    </td>
                  ))}
                </tr>
              ))
            ) : queries.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-slate-500">
                  No queries found for the selected filters.
                </td>
              </tr>
            ) : (
              queries.map((q) => (
                <tr key={q.id} className="border-b border-slate-700/30 hover:bg-slate-700/20">
                  <td className="whitespace-nowrap px-4 py-2.5 font-mono text-xs text-slate-400">
                    {new Date(q.timestamp).toLocaleString([], {
                      month: "short",
                      day: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                      second: "2-digit",
                    })}
                  </td>
                  <td className="max-w-[280px] truncate px-4 py-2.5 text-slate-200">
                    {q.domain}
                  </td>
                  <td className="px-4 py-2.5 font-mono text-xs text-slate-400">
                    {q.client}
                  </td>
                  <td className="px-4 py-2.5 text-slate-400">{q.query_type}</td>
                  <td className="px-4 py-2.5">
                    <span className={`font-medium ${STATUS_COLORS[q.status] ?? "text-slate-400"}`}>
                      {q.status}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-right font-mono text-xs text-slate-400">
                    {q.response_time_ms != null ? `${q.response_time_ms.toFixed(1)} ms` : "-"}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between text-sm text-slate-400">
        <span>
          {total.toLocaleString()} queries total
        </span>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="rounded-md border border-slate-700 p-1.5 hover:bg-slate-700/50 disabled:opacity-30"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <span className="text-slate-300">
            Page {page} of {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
            className="rounded-md border border-slate-700 p-1.5 hover:bg-slate-700/50 disabled:opacity-30"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
