/**
 * UptimeTab -- Uptime monitoring tab with live counters, status bars, and incident history.
 */

import { useState, useEffect, useMemo, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, CheckCircle } from 'lucide-react';
import type { TimeRange } from '../../api/monitoring';
import {
  getUptimeCurrent,
  getUptimeHistory,
  type CurrentUptimeResponse,
  type UptimeSample,
} from '../../api/monitoring';
import { StatCard } from '../ui/StatCard';
import { UptimeStatusBar } from './UptimeStatusBar';
import { formatUptime } from '../../lib/formatters';

interface RestartEvent {
  timestamp: string;
  sessionDuration: number;
}

function formatDateTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString();
  } catch {
    return iso;
  }
}

export function UptimeTab({ timeRange }: { timeRange: TimeRange }) {
  const { t } = useTranslation(['system', 'common']);
  const [current, setCurrent] = useState<CurrentUptimeResponse | null>(null);
  const [history, setHistory] = useState<UptimeSample[]>([]);
  const [error, setError] = useState<string | null>(null);

  // Tick counter for live update between polls
  const [tick, setTick] = useState(0);

  const fetchData = useCallback(async () => {
    try {
      const [currentData, historyData] = await Promise.all([
        getUptimeCurrent(),
        getUptimeHistory(timeRange),
      ]);
      setCurrent(currentData);
      setHistory(historyData.samples);
      setError(null);
    } catch (err) {
      if (!current) {
        setError(err instanceof Error ? err.message : 'Failed to load uptime data');
      }
    }
  }, [timeRange]);

  // Initial fetch + polling
  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, [fetchData]);

  // Client-side 1s tick for live counter
  useEffect(() => {
    const interval = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(interval);
  }, []);

  // Compute live uptime values (add tick seconds to last known values)
  const liveServerUptime = useMemo(() => {
    if (!current) return 0;
    return current.server_uptime_seconds + tick;
  }, [current, tick]);

  const liveSystemUptime = useMemo(() => {
    if (!current) return 0;
    return current.system_uptime_seconds + tick;
  }, [current, tick]);

  // Reset tick when fresh data arrives
  useEffect(() => {
    setTick(0);
  }, [current?.timestamp]);

  // Detect restarts from history (where server_uptime_seconds drops)
  const restarts = useMemo<RestartEvent[]>(() => {
    if (history.length < 2) return [];
    const events: RestartEvent[] = [];
    for (let i = 1; i < history.length; i++) {
      if (history[i].server_uptime_seconds < history[i - 1].server_uptime_seconds) {
        events.push({
          timestamp: history[i].timestamp,
          sessionDuration: history[i - 1].server_uptime_seconds,
        });
      }
    }
    return events;
  }, [history]);

  if (error && !current) {
    return <div className="text-red-400 text-center py-8">{error}</div>;
  }

  return (
    <div className="space-y-4 sm:space-y-6 min-w-0">
      {/* Current Stats */}
      <div className="grid grid-cols-1 min-[400px]:grid-cols-2 gap-3 sm:gap-5">
        <StatCard
          label={t('monitor.uptime.serverUptime')}
          value={formatUptime(liveServerUptime)}
          unit=""
          color="blue"
          icon={<span className="text-blue-400 text-base sm:text-xl">S</span>}
          subValue={current ? formatDateTime(current.server_start_time) : undefined}
        />
        <StatCard
          label={t('monitor.uptime.systemUptime')}
          value={formatUptime(liveSystemUptime)}
          unit=""
          color="green"
          icon={<span className="text-green-400 text-base sm:text-xl">OS</span>}
          subValue={current ? formatDateTime(current.system_boot_time) : undefined}
        />
      </div>

      {/* Status Bars */}
      <div className="space-y-3">
        <UptimeStatusBar
          samples={history}
          timeRange={timeRange}
          label={t('monitor.uptime.serverLabel')}
          uptimeField="server_uptime_seconds"
        />
        <UptimeStatusBar
          samples={history}
          timeRange={timeRange}
          label={t('monitor.uptime.systemLabel')}
          uptimeField="system_uptime_seconds"
        />
      </div>

      {/* Incidents / Restart History */}
      <div>
        <h3 className="text-base sm:text-lg font-semibold text-white mb-3 flex items-center gap-2">
          {restarts.length > 0 ? (
            <AlertTriangle className="w-4 h-4 text-amber-400" />
          ) : (
            <CheckCircle className="w-4 h-4 text-green-400" />
          )}
          {t('monitor.uptime.incidents')}
        </h3>
        {restarts.length === 0 ? (
          <div className="card border-green-500/20 bg-green-500/5 p-4 flex items-center gap-3">
            <CheckCircle className="w-5 h-5 text-green-400 flex-shrink-0" />
            <p className="text-sm text-green-300">{t('monitor.uptime.noIncidents')}</p>
          </div>
        ) : (
          <div className="space-y-2">
            {restarts.map((restart, idx) => (
              <div
                key={idx}
                className="card border-amber-500/20 bg-amber-500/5 p-3 flex items-center justify-between"
              >
                <div className="flex items-center gap-3">
                  <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0" />
                  <div>
                    <p className="text-sm font-medium text-white">
                      {formatDateTime(restart.timestamp)}
                    </p>
                    <p className="text-xs text-slate-400">
                      {t('monitor.uptime.sessionDuration')}: {formatUptime(restart.sessionDuration)}
                    </p>
                  </div>
                </div>
                <div className="rounded-full bg-amber-500/20 px-2 py-1">
                  <span className="text-xs text-amber-400">{t('monitor.uptime.restart')}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
