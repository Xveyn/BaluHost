/**
 * UptimeTab -- Uptime monitoring tab with live counters, restart history, and charts.
 */

import { useState, useEffect, useMemo, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { MetricChart } from '../monitoring';
import type { TimeRange } from '../../api/monitoring';
import {
  getUptimeCurrent,
  getUptimeHistory,
  type CurrentUptimeResponse,
  type UptimeSample,
} from '../../api/monitoring';
import { StatCard } from '../ui/StatCard';
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
  const [loading, setLoading] = useState(true);
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
    } finally {
      setLoading(false);
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

  // Chart data
  const chartData = useMemo(() => {
    return history.map((s) => ({
      time: s.timestamp,
      server: Math.round(s.server_uptime_seconds / 3600 * 100) / 100,
      system: Math.round(s.system_uptime_seconds / 3600 * 100) / 100,
    }));
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

      {/* Restart History */}
      <div>
        <h3 className="text-base sm:text-lg font-semibold text-white mb-3">
          {t('monitor.uptime.restartHistory')}
        </h3>
        {restarts.length === 0 ? (
          <div className="card border-slate-800/60 bg-slate-900/60 p-4">
            <p className="text-sm text-slate-400">{t('monitor.uptime.noRestarts')}</p>
          </div>
        ) : (
          <div className="space-y-2">
            {restarts.map((restart, idx) => (
              <div
                key={idx}
                className="card border-slate-800/60 bg-slate-900/60 p-3 flex items-center justify-between"
              >
                <div>
                  <p className="text-sm font-medium text-white">
                    {formatDateTime(restart.timestamp)}
                  </p>
                  <p className="text-xs text-slate-400">
                    {t('monitor.uptime.sessionDuration')}: {formatUptime(restart.sessionDuration)}
                  </p>
                </div>
                <div className="rounded-full bg-amber-500/20 px-2 py-1">
                  <span className="text-xs text-amber-400">{t('monitor.uptime.restart')}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Uptime Chart */}
      <div>
        <h3 className="text-base sm:text-lg font-semibold text-white mb-3">
          {t('monitor.uptime.uptimeChart')}
        </h3>
        <div className="card border-slate-800/60 bg-slate-900/60 p-3 sm:p-5">
          <MetricChart
            data={chartData}
            lines={[
              { dataKey: 'server', name: t('monitor.uptime.serverLabel'), color: '#3b82f6' },
              { dataKey: 'system', name: t('monitor.uptime.systemLabel'), color: '#22c55e' },
            ]}
            yAxisLabel={t('monitor.uptime.hours')}
            yAxisDomain={[0, 'auto']}
            showArea
            loading={loading}
            emptyMessage={t('monitor.uptime.noData')}
            timeRange={timeRange}
          />
        </div>
      </div>
    </div>
  );
}
