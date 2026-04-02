import { useEffect, useState, useCallback } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import toast from "react-hot-toast";
import { getQueries, type QueryEntry } from "../../api/pihole";
import { useSortableTable } from '../../hooks/useSortableTable';
import { SortableHeader } from '../ui/SortableHeader';

const PAGE_SIZE = 25;

const statusBadge: Record<string, { bg: string; text: string }> = {
  FORWARDED: { bg: "bg-emerald-500/20", text: "text-emerald-400" },
  BLOCKED: { bg: "bg-red-500/20", text: "text-red-400" },
  CACHED: { bg: "bg-sky-500/20", text: "text-sky-400" },
};

function formatTimestamp(ts: number): string {
  return new Date(ts * 1000).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export default function PiholeQueryLog() {
  const [queries, setQueries] = useState<QueryEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(0);
  const { sortedData: sortedQueries, sortKey, sortDirection, toggleSort } = useSortableTable(queries);
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const fetchQueries = useCallback(async () => {
    setLoading(true);
    try {
      const result = await getQueries(PAGE_SIZE, page * PAGE_SIZE);
      setQueries(result.queries);
      setTotal(result.total);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to load query log");
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => {
    fetchQueries();
  }, [fetchQueries]);

  const goToPage = (p: number) => {
    if (p >= 0 && p < totalPages) setPage(p);
  };

  return (
    <div className="rounded-xl border border-slate-700/50 bg-slate-800/60">
      <div className="flex items-center justify-between border-b border-slate-700/50 px-4 py-3">
        <h3 className="text-sm font-medium text-slate-300">Query Log</h3>
        <span className="text-xs text-slate-500">
          {total.toLocaleString()} total queries
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-slate-700/50 text-xs uppercase text-slate-500">
              <SortableHeader label="Time" sortKey="timestamp" activeSortKey={sortKey} sortDirection={sortDirection} onSort={toggleSort} className="px-4 py-2.5" />
              <SortableHeader label="Domain" sortKey="domain" activeSortKey={sortKey} sortDirection={sortDirection} onSort={toggleSort} className="px-4 py-2.5" />
              <SortableHeader label="Client" sortKey="client" activeSortKey={sortKey} sortDirection={sortDirection} onSort={toggleSort} className="px-4 py-2.5" />
              <SortableHeader label="Type" sortKey="query_type" activeSortKey={sortKey} sortDirection={sortDirection} onSort={toggleSort} className="px-4 py-2.5" />
              <SortableHeader label="Status" sortKey="status" activeSortKey={sortKey} sortDirection={sortDirection} onSort={toggleSort} className="px-4 py-2.5" />
              <SortableHeader label="Response" sortKey="response_time" activeSortKey={sortKey} sortDirection={sortDirection} onSort={toggleSort} className="px-4 py-2.5 text-right" />
            </tr>
          </thead>
          <tbody>
            {loading ? (
              Array.from({ length: 8 }).map((_, i) => (
                <tr key={i} className="border-b border-slate-700/30">
                  {Array.from({ length: 6 }).map((_, j) => (
                    <td key={j} className="px-4 py-2.5">
                      <div className="h-4 w-20 animate-pulse rounded bg-slate-700" />
                    </td>
                  ))}
                </tr>
              ))
            ) : queries.length === 0 ? (
              <tr>
                <td
                  colSpan={6}
                  className="px-4 py-8 text-center text-slate-500"
                >
                  No queries found
                </td>
              </tr>
            ) : (
              sortedQueries.map((q, i) => {
                const badge = statusBadge[q.status] ?? {
                  bg: "bg-slate-500/20",
                  text: "text-slate-400",
                };
                return (
                  <tr
                    key={i}
                    className="border-b border-slate-700/30 hover:bg-slate-700/20"
                  >
                    <td className="whitespace-nowrap px-4 py-2.5 text-slate-400">
                      {formatTimestamp(q.timestamp)}
                    </td>
                    <td className="max-w-xs truncate px-4 py-2.5 font-mono text-xs text-slate-200">
                      {q.domain}
                    </td>
                    <td className="whitespace-nowrap px-4 py-2.5 font-mono text-xs text-slate-400">
                      {q.client}
                    </td>
                    <td className="px-4 py-2.5 text-slate-400">
                      {q.query_type}
                    </td>
                    <td className="px-4 py-2.5">
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-medium ${badge.bg} ${badge.text}`}
                      >
                        {q.status}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-right text-slate-500">
                      {q.response_time != null
                        ? `${q.response_time.toFixed(1)}ms`
                        : "\u2014"}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between border-t border-slate-700/50 px-4 py-2.5">
        <span className="text-xs text-slate-500">
          Page {page + 1} of {totalPages}
        </span>
        <div className="flex items-center gap-1">
          <button
            onClick={() => goToPage(page - 1)}
            disabled={page === 0 || loading}
            className="rounded p-1 text-slate-400 hover:bg-slate-700/50 hover:text-slate-200 disabled:cursor-not-allowed disabled:opacity-30"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <button
            onClick={() => goToPage(page + 1)}
            disabled={page >= totalPages - 1 || loading}
            className="rounded p-1 text-slate-400 hover:bg-slate-700/50 hover:text-slate-200 disabled:cursor-not-allowed disabled:opacity-30"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
