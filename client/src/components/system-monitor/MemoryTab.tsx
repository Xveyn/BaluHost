/**
 * MemoryTab -- RAM monitoring tab with usage chart and BaluHost per-unit breakdown.
 */

import { useMemo, useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { MetricChart } from '../monitoring';
import type { TimeRange } from '../../api/monitoring';
import { useMemoryMonitoring } from '../../hooks/useMonitoring';
import { formatBytes, formatNumber } from '../../lib/formatters';
import { StatCard } from '../ui/StatCard';

// Display order of units in the breakdown (matches BALUHOST_PROCESS_PATTERNS in backend).
const UNIT_DISPLAY_ORDER = [
  'baluhost-backend',
  'baluhost-backend-local',
  'baluhost-scheduler',
  'baluhost-webdav',
  'baluhost-monitoring',
  'baluhost-tui',
  'baluhost-frontend-dev',
] as const;

// i18n key per unit (under `system:monitor.units.*`).
const UNIT_LABEL_KEY: Record<string, string> = {
  'baluhost-backend':       'monitor.units.backend',
  'baluhost-backend-local': 'monitor.units.backendLocal',
  'baluhost-scheduler':     'monitor.units.scheduler',
  'baluhost-webdav':        'monitor.units.webdav',
  'baluhost-monitoring':    'monitor.units.monitoring',
  'baluhost-tui':           'monitor.units.tui',
  'baluhost-frontend-dev':  'monitor.units.frontendDev',
};

export function MemoryTab({ timeRange }: { timeRange: TimeRange }) {
  const { t } = useTranslation(['system', 'common']);
  const { current, history, loading, error } = useMemoryMonitoring({ historyDuration: timeRange });
  const [breakdownOpen, setBreakdownOpen] = useState(false);

  const totalGb = current ? current.total_bytes / (1024 * 1024 * 1024) : 16;

  const chartData = useMemo(() => {
    return history
      .filter((s) => s.used_bytes > 0 && s.total_bytes > 0)
      .map((s) => ({
        time: s.timestamp,
        usedGb: s.used_bytes / (1024 * 1024 * 1024),
        baluhostGb: s.baluhost_memory_bytes && s.baluhost_memory_bytes > 0
          ? s.baluhost_memory_bytes / (1024 * 1024 * 1024)
          : null,
      }));
  }, [history]);

  const hasBaluhostData = chartData.some((d) => d.baluhostGb !== null);

  // Visible units = units with > 0 bytes, in canonical order.
  const visibleUnits = useMemo(() => {
    const breakdown = current?.baluhost_memory_breakdown;
    if (!breakdown) return [];
    return UNIT_DISPLAY_ORDER
      .filter((name) => (breakdown[name] ?? 0) > 0)
      .map((name) => ({ name, bytes: breakdown[name] }));
  }, [current]);

  if (error) {
    return <div className="text-red-400 text-center py-8">{error}</div>;
  }

  return (
    <div className="space-y-4 sm:space-y-6 min-w-0">
      <div className="grid grid-cols-1 min-[400px]:grid-cols-2 gap-3 sm:gap-5 lg:grid-cols-5">
        <StatCard
          label={t('monitor.used')}
          value={current ? formatBytes(current.used_bytes) : '-'}
          color="purple"
          icon={<span className="text-purple-400 text-base sm:text-xl">📊</span>}
        />
        <StatCard
          label={t('monitor.total')}
          value={current ? formatBytes(current.total_bytes) : '-'}
          color="blue"
          icon={<span className="text-blue-400 text-base sm:text-xl">Σ</span>}
        />
        <StatCard
          label={t('monitor.available')}
          value={current?.available_bytes ? formatBytes(current.available_bytes) : '-'}
          color="green"
          icon={<span className="text-green-400 text-base sm:text-xl">✓</span>}
        />
        <StatCard
          label={t('monitor.utilization')}
          value={current?.percent != null ? formatNumber(current.percent, 1) : '0'}
          unit="%"
          color="orange"
          icon={<span className="text-orange-400 text-base sm:text-xl">%</span>}
        />

        {/* BaluHost breakdown card. overflow-visible (overrides .card) + relative
            let the expanded breakdown render as an overlay anchored below the
            card, so toggling it open never changes the height of the sibling
            stat cards in the same grid row. */}
        <div className="card relative overflow-visible border-slate-800/60 bg-slate-900/55 p-3 sm:p-4 flex flex-col">
          <button
            type="button"
            onClick={() => setBreakdownOpen((v) => !v)}
            className="flex items-center justify-between gap-2 text-left"
            aria-expanded={breakdownOpen}
          >
            <span className="flex items-center gap-2 text-xs sm:text-sm text-slate-400">
              <span className="text-cyan-400 text-base sm:text-xl">🏠</span>
              BaluHost
            </span>
            {visibleUnits.length > 0 && (
              breakdownOpen
                ? <ChevronDown className="h-4 w-4 text-slate-500" />
                : <ChevronRight className="h-4 w-4 text-slate-500" />
            )}
          </button>
          <div className="mt-1 text-xl sm:text-2xl font-semibold text-white tabular-nums">
            {current?.baluhost_memory_bytes ? formatBytes(current.baluhost_memory_bytes) : '-'}
          </div>

          {breakdownOpen && visibleUnits.length > 0 && (
            <ul className="absolute left-0 right-0 top-full z-20 mt-2 space-y-1 rounded-2xl border border-slate-700/70 bg-slate-900/95 p-3 text-xs shadow-[0_20px_60px_rgba(2,6,23,0.65)] backdrop-blur-xl sm:text-sm">
              {visibleUnits.map((unit) => (
                <li key={unit.name} className="flex justify-between gap-2">
                  <span className="text-slate-400 truncate">
                    {t(UNIT_LABEL_KEY[unit.name] ?? unit.name)}
                  </span>
                  <span className="text-slate-200 tabular-nums shrink-0">
                    {formatBytes(unit.bytes)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="card border-slate-800/60 bg-slate-900/55 p-4 sm:p-6">
        <h3 className="mb-3 sm:mb-4 text-base sm:text-lg font-semibold text-white">{t('monitor.ramHistory')}</h3>
        <MetricChart
          data={chartData}
          lines={[
            { dataKey: 'usedGb', name: t('monitor.usedGb'), color: '#a855f7' },
            ...(hasBaluhostData
              ? [{ dataKey: 'baluhostGb', name: t('monitor.baluhostGb'), color: '#06b6d4' }]
              : []),
          ]}
          yAxisLabel="GB"
          yAxisDomain={[0, Math.ceil(totalGb)]}
          height={300}
          loading={loading}
          showArea
          timeRange={timeRange}
        />
      </div>
    </div>
  );
}
