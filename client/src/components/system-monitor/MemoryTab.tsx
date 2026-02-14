/**
 * MemoryTab -- RAM monitoring tab with usage chart.
 */

import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { MetricChart } from '../monitoring';
import type { TimeRange } from '../../api/monitoring';
import { useMemoryMonitoring } from '../../hooks/useMonitoring';
import { formatBytes, formatNumber } from '../../lib/formatters';
import { StatCard } from '../ui/StatCard';

export function MemoryTab({ timeRange }: { timeRange: TimeRange }) {
  const { t } = useTranslation(['system', 'common']);
  const { current, history, loading, error } = useMemoryMonitoring({ historyDuration: timeRange });

  // Calculate total RAM in GB for chart domain
  const totalGb = current ? current.total_bytes / (1024 * 1024 * 1024) : 16;

  // Filter out samples with invalid data and convert to GB
  const chartData = useMemo(() => {
    return history
      .filter((s) => s.used_bytes > 0 && s.total_bytes > 0) // Only valid samples
      .map((s) => ({
        time: s.timestamp,
        usedGb: s.used_bytes / (1024 * 1024 * 1024),
        baluhostGb: s.baluhost_memory_bytes && s.baluhost_memory_bytes > 0
          ? s.baluhost_memory_bytes / (1024 * 1024 * 1024)
          : null,
      }));
  }, [history]);

  const hasBaluhostData = chartData.some((d) => d.baluhostGb !== null);

  if (error) {
    return <div className="text-red-400 text-center py-8">{error}</div>;
  }

  return (
    <div className="space-y-4 sm:space-y-6 min-w-0">
      {/* Current Stats */}
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
        <StatCard
          label="BaluHost"
          value={current?.baluhost_memory_bytes ? formatBytes(current.baluhost_memory_bytes) : '-'}
          color="cyan"
          icon={<span className="text-cyan-400 text-base sm:text-xl">🏠</span>}
        />
      </div>

      {/* Chart - Absolute values in GB */}
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
