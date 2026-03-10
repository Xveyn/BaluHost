/**
 * Backend Logs Tab Component
 *
 * Terminal-style real-time log viewer using SSE streaming.
 * Admin only. Displays logs from the Python backend ring buffer.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Pause, Play, Trash2, Search, ArrowDownToLine } from 'lucide-react';
import toast from 'react-hot-toast';
import { backendLogsApi, getLevelColor } from '../../api/backend-logs';
import type { LogEntry } from '../../api/backend-logs';

const MAX_FRONTEND_ENTRIES = 2000;
const LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'] as const;

export function BackendLogsTab() {
  const { t } = useTranslation(['system', 'common']);
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [levelFilter, setLevelFilter] = useState<string>('');
  const [searchText, setSearchText] = useState('');
  const [paused, setPaused] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);
  const [connected, setConnected] = useState(false);
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());

  const scrollRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const latestIdRef = useRef(0);

  // Auto-scroll to bottom when new entries arrive
  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [entries, autoScroll]);

  // Load initial history
  useEffect(() => {
    (async () => {
      try {
        const res = await backendLogsApi.getLogs({ limit: 500 });
        setEntries(res.entries);
        latestIdRef.current = res.latest_id;
      } catch {
        // Silently fail — SSE will pick up new entries
      }
    })();
  }, []);

  // SSE connection management
  const connectSSE = useCallback(() => {
    const token = localStorage.getItem('token');
    if (!token) return;

    const url = backendLogsApi.getStreamUrl(token);
    const es = new EventSource(url);
    eventSourceRef.current = es;

    es.addEventListener('log', (e) => {
      try {
        const entry: LogEntry = JSON.parse(e.data);
        latestIdRef.current = Math.max(latestIdRef.current, entry.id);
        setEntries((prev) => {
          const next = [...prev, entry];
          return next.length > MAX_FRONTEND_ENTRIES
            ? next.slice(next.length - MAX_FRONTEND_ENTRIES)
            : next;
        });
      } catch {
        // Ignore malformed events
      }
    });

    es.onopen = () => setConnected(true);
    es.onerror = () => {
      setConnected(false);
      es.close();
      eventSourceRef.current = null;
      // Auto-reconnect after 3s
      setTimeout(() => {
        if (!paused) connectSSE();
      }, 3000);
    };
  }, [paused]);

  useEffect(() => {
    if (!paused) {
      connectSSE();
    }
    return () => {
      eventSourceRef.current?.close();
      eventSourceRef.current = null;
    };
  }, [paused, connectSSE]);

  // Pause/Resume
  const togglePause = () => {
    if (paused) {
      setPaused(false);
    } else {
      eventSourceRef.current?.close();
      eventSourceRef.current = null;
      setConnected(false);
      setPaused(true);
    }
  };

  // Clear logs
  const handleClear = async () => {
    if (!confirm(t('monitor.backendLogs.clearConfirm'))) return;
    try {
      const res = await backendLogsApi.clearLogs();
      setEntries([]);
      latestIdRef.current = 0;
      toast.success(t('monitor.backendLogs.cleared', { count: res.cleared }));
    } catch {
      toast.error(t('common:error'));
    }
  };

  // Toggle traceback expansion
  const toggleExpand = (id: number) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // Client-side filtering
  const filtered = entries.filter((e) => {
    if (levelFilter) {
      const minIdx = LEVELS.indexOf(levelFilter as typeof LEVELS[number]);
      const entryIdx = LEVELS.indexOf(e.level as typeof LEVELS[number]);
      if (entryIdx < minIdx) return false;
    }
    if (searchText) {
      const needle = searchText.toLowerCase();
      if (
        !e.message.toLowerCase().includes(needle) &&
        !e.logger_name.toLowerCase().includes(needle)
      ) {
        return false;
      }
    }
    return true;
  });

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-white">{t('monitor.backendLogs.title')}</h2>
          <p className="text-xs sm:text-sm text-slate-400">
            {t('monitor.backendLogs.description')}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* Connection status */}
          <span className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border ${
            connected
              ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-400'
              : paused
              ? 'border-amber-500/40 bg-amber-500/10 text-amber-400'
              : 'border-red-500/40 bg-red-500/10 text-red-400'
          }`}>
            <span className={`h-1.5 w-1.5 rounded-full ${connected ? 'bg-emerald-400 animate-pulse' : paused ? 'bg-amber-400' : 'bg-red-400'}`} />
            {connected
              ? t('monitor.backendLogs.connected')
              : paused
              ? t('monitor.backendLogs.pause')
              : t('monitor.backendLogs.disconnected')}
          </span>
          <span className="text-xs text-slate-500">
            {t('monitor.backendLogs.entries', { count: filtered.length })}
          </span>
        </div>
      </div>

      {/* Toolbar */}
      <div className="flex flex-col sm:flex-row gap-2">
        {/* Level filter */}
        <select
          value={levelFilter}
          onChange={(e) => setLevelFilter(e.target.value)}
          className="rounded-lg border border-slate-700 bg-slate-900/70 px-3 py-2 text-xs sm:text-sm text-slate-200 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
        >
          <option value="">{t('monitor.backendLogs.allLevels')}</option>
          {LEVELS.map((l) => (
            <option key={l} value={l}>{l}</option>
          ))}
        </select>

        {/* Search */}
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
          <input
            type="text"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            placeholder={t('monitor.backendLogs.search')}
            className="w-full rounded-lg border border-slate-700 bg-slate-900/70 pl-9 pr-3 py-2 text-xs sm:text-sm text-slate-200 placeholder-slate-500 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
          />
        </div>

        {/* Action buttons */}
        <div className="flex gap-2">
          <button
            onClick={togglePause}
            className={`flex items-center gap-1.5 rounded-lg border px-3 py-2 text-xs sm:text-sm font-medium transition-all touch-manipulation active:scale-95 ${
              paused
                ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/20'
                : 'border-amber-500/40 bg-amber-500/10 text-amber-300 hover:bg-amber-500/20'
            }`}
          >
            {paused ? <Play className="h-4 w-4" /> : <Pause className="h-4 w-4" />}
            <span className="hidden sm:inline">{paused ? t('monitor.backendLogs.resume') : t('monitor.backendLogs.pause')}</span>
          </button>

          <button
            onClick={() => setAutoScroll((v) => !v)}
            className={`flex items-center gap-1.5 rounded-lg border px-3 py-2 text-xs sm:text-sm font-medium transition-all touch-manipulation active:scale-95 ${
              autoScroll
                ? 'border-sky-500/40 bg-sky-500/10 text-sky-300'
                : 'border-slate-700 bg-slate-900/70 text-slate-400 hover:bg-slate-800/60'
            }`}
            title={t('monitor.backendLogs.autoScroll')}
          >
            <ArrowDownToLine className="h-4 w-4" />
            <span className="hidden sm:inline">{t('monitor.backendLogs.autoScroll')}</span>
          </button>

          <button
            onClick={handleClear}
            className="flex items-center gap-1.5 rounded-lg border border-red-500/40 bg-red-500/10 text-red-300 hover:bg-red-500/20 px-3 py-2 text-xs sm:text-sm font-medium transition-all touch-manipulation active:scale-95"
          >
            <Trash2 className="h-4 w-4" />
            <span className="hidden sm:inline">{t('monitor.backendLogs.clear')}</span>
          </button>
        </div>
      </div>

      {/* Log output */}
      <div
        ref={scrollRef}
        className="h-[calc(100vh-380px)] min-h-[300px] overflow-y-auto rounded-xl border border-slate-800/60 bg-slate-950/80 p-3 font-mono text-xs leading-relaxed"
      >
        {filtered.length === 0 ? (
          <div className="flex items-center justify-center h-full text-slate-500">
            {t('monitor.backendLogs.noLogs')}
          </div>
        ) : (
          <div className="space-y-0.5">
            {filtered.map((entry) => (
              <div key={entry.id} className="group hover:bg-slate-800/30 rounded px-1.5 py-0.5">
                <div className="flex items-start gap-2">
                  {/* Timestamp */}
                  <span className="text-slate-500 whitespace-nowrap flex-shrink-0">
                    {entry.timestamp.slice(11, 23)}
                  </span>

                  {/* Level badge */}
                  <span className={`inline-flex items-center px-1.5 py-0 rounded text-[10px] font-semibold flex-shrink-0 border ${getLevelColor(entry.level)}`}>
                    {entry.level.padEnd(8)}
                  </span>

                  {/* Logger name */}
                  <span className="text-cyan-400/70 flex-shrink-0 max-w-[200px] truncate" title={entry.logger_name}>
                    {entry.logger_name.replace(/^app\./, '')}
                  </span>

                  {/* Message */}
                  <span className={`break-all ${
                    entry.level === 'ERROR' || entry.level === 'CRITICAL'
                      ? 'text-red-300'
                      : entry.level === 'WARNING'
                      ? 'text-amber-200'
                      : 'text-slate-200'
                  }`}>
                    {entry.message}
                  </span>
                </div>

                {/* Expandable traceback */}
                {entry.exc_info && (
                  <div className="ml-[88px]">
                    <button
                      onClick={() => toggleExpand(entry.id)}
                      className="text-[10px] text-red-400/60 hover:text-red-400 underline mt-0.5"
                    >
                      {expandedIds.has(entry.id)
                        ? t('monitor.backendLogs.hideTraceback')
                        : t('monitor.backendLogs.showTraceback')}
                    </button>
                    {expandedIds.has(entry.id) && (
                      <pre className="mt-1 text-red-300/80 whitespace-pre-wrap text-[11px] bg-red-950/30 border border-red-900/30 rounded p-2">
                        {entry.exc_info}
                      </pre>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
