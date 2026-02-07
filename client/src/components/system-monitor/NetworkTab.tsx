/**
 * NetworkTab -- Network monitoring tab with download/upload speed charts.
 */

import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { MetricChart } from '../monitoring';
import type { TimeRange } from '../../api/monitoring';
import { useNetworkMonitoring } from '../../hooks/useMonitoring';
import { StatCard } from '../ui/StatCard';
import { formatNumber } from '../../lib/formatters';

export function NetworkTab({ timeRange }: { timeRange: TimeRange }) {
  const { t } = useTranslation(['system', 'common']);
  const { current, history, loading, error } = useNetworkMonitoring({ historyDuration: timeRange });

  // Filter and map network data - only include valid samples
  const chartData = useMemo(() => {
    return history
      .filter((s) => s.download_mbps !== undefined && s.upload_mbps !== undefined)
      .map((s) => ({
        time: s.timestamp,
        download: s.download_mbps,
        upload: s.upload_mbps,
      }));
  }, [history]);

  if (error) {
    return <div className="text-red-400 text-center py-8">{error}</div>;
  }

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Current Stats */}
      <div className="grid grid-cols-2 gap-3 sm:gap-5">
        <StatCard
          label={t('monitor.download')}
          value={current?.download_mbps != null ? formatNumber(current.download_mbps, 2) : '0'}
          unit="Mbit/s"
          color="blue"
          icon={<span className="text-blue-400 text-base sm:text-xl">↓</span>}
        />
        <StatCard
          label={t('monitor.upload')}
          value={current?.upload_mbps != null ? formatNumber(current.upload_mbps, 2) : '0'}
          unit="Mbit/s"
          color="green"
          icon={<span className="text-green-400 text-base sm:text-xl">↑</span>}
        />
      </div>

      {/* Chart */}
      <div className="card border-slate-800/60 bg-slate-900/55 p-4 sm:p-6">
        <h3 className="mb-3 sm:mb-4 text-base sm:text-lg font-semibold text-white">{t('monitor.networkHistory')}</h3>
        <MetricChart
          data={chartData}
          lines={[
            { dataKey: 'download', name: t('monitor.downloadMbps'), color: '#3b82f6' },
            { dataKey: 'upload', name: t('monitor.uploadMbps'), color: '#10b981' },
          ]}
          yAxisLabel="Mbit/s"
          height={300}
          loading={loading}
          timeRange={timeRange}
        />
      </div>
    </div>
  );
}
