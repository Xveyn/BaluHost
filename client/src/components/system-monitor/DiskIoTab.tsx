/**
 * DiskIoTab -- Disk I/O monitoring tab with per-disk throughput and IOPS charts.
 */

import { useState, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { MetricChart } from '../monitoring';
import type { TimeRange } from '../../api/monitoring';
import { formatTimestamp } from '../../lib/dateUtils';
import { useDiskIoMonitoring } from '../../hooks/useMonitoring';
import { StatCard } from '../ui/StatCard';
import { BenchmarkPanel } from '../benchmark';

export function DiskIoTab({ timeRange }: { timeRange: TimeRange }) {
  const { t } = useTranslation(['system', 'common']);
  const { disks, history, availableDisks, loading, error } = useDiskIoMonitoring({
    historyDuration: timeRange,
  });
  const [selectedDisk, setSelectedDisk] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<'throughput' | 'iops'>('throughput');

  // Auto-select first disk
  useEffect(() => {
    if (!selectedDisk && availableDisks.length > 0) {
      setSelectedDisk(availableDisks[0]);
    }
  }, [availableDisks, selectedDisk]);

  const chartData = useMemo(() => {
    if (!selectedDisk || !history[selectedDisk]) return [];
    return history[selectedDisk]
      .filter((s) => s.read_mbps !== undefined && s.write_mbps !== undefined)
      .map((s) => ({
        time: formatTimestamp(s.timestamp),
        read: viewMode === 'throughput' ? s.read_mbps : s.read_iops,
        write: viewMode === 'throughput' ? s.write_mbps : s.write_iops,
      }));
  }, [selectedDisk, history, viewMode]);

  const currentDisk = selectedDisk ? disks[selectedDisk] : null;

  if (error) {
    return <div className="text-red-400 text-center py-8">{error}</div>;
  }

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Disk Selector */}
      {availableDisks.length > 0 && (
        <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0">
          <div className="flex gap-2 sm:gap-3 sm:flex-wrap min-w-max sm:min-w-0">
            {availableDisks.map((disk) => (
              <button
                key={disk}
                onClick={() => setSelectedDisk(disk)}
                className={`whitespace-nowrap rounded-lg border px-3 sm:px-4 py-1.5 sm:py-2 text-xs sm:text-sm font-medium transition-all touch-manipulation active:scale-95 ${
                  selectedDisk === disk
                    ? 'border-blue-500 bg-blue-500/10 text-blue-400'
                    : 'border-slate-700 bg-slate-800/50 text-slate-400 hover:border-slate-600 hover:bg-slate-800'
                }`}
              >
                {disk}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Current Stats */}
      {selectedDisk && (
        <div className="grid grid-cols-2 gap-3 sm:gap-5 lg:grid-cols-6">
          <StatCard
            label={t('monitor.read')}
            value={currentDisk?.read_mbps?.toFixed(2) ?? '0'}
            unit="MB/s"
            color="blue"
            icon={<span className="text-blue-400 text-base sm:text-xl">📖</span>}
          />
          <StatCard
            label={t('monitor.write')}
            value={currentDisk?.write_mbps?.toFixed(2) ?? '0'}
            unit="MB/s"
            color="green"
            icon={<span className="text-green-400 text-base sm:text-xl">✏️</span>}
          />
          <StatCard
            label={t('monitor.readIops')}
            value={currentDisk?.read_iops?.toFixed(0) ?? '0'}
            color="purple"
            icon={<span className="text-purple-400 text-base sm:text-xl">⚡</span>}
          />
          <StatCard
            label={t('monitor.writeIops')}
            value={currentDisk?.write_iops?.toFixed(0) ?? '0'}
            color="orange"
            icon={<span className="text-orange-400 text-base sm:text-xl">⚡</span>}
          />
          <StatCard
            label={t('monitor.responseTime')}
            value={currentDisk?.avg_response_ms?.toFixed(2) ?? '-'}
            unit="ms"
            color="cyan"
            icon={<span className="text-cyan-400 text-base sm:text-xl">⏱</span>}
          />
          <StatCard
            label={t('monitor.activeTime')}
            value={currentDisk?.active_time_percent?.toFixed(1) ?? '-'}
            unit="%"
            color="teal"
            icon={<span className="text-teal-400 text-base sm:text-xl">📊</span>}
          />
        </div>
      )}

      {/* Chart */}
      {selectedDisk && (
        <div className="card border-slate-800/60 bg-slate-900/55 p-4 sm:p-6">
          <div className="mb-3 sm:mb-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
            <h3 className="text-base sm:text-lg font-semibold text-white">{selectedDisk} - {t('monitor.history')}</h3>
            <div className="flex gap-2">
              <button
                onClick={() => setViewMode('throughput')}
                className={`flex-1 sm:flex-initial rounded-lg px-3 py-1.5 text-xs sm:text-sm font-medium transition-all touch-manipulation active:scale-95 ${
                  viewMode === 'throughput'
                    ? 'bg-blue-500/20 text-blue-400'
                    : 'text-slate-400 hover:bg-slate-800'
                }`}
              >
                {t('monitor.throughput')}
              </button>
              <button
                onClick={() => setViewMode('iops')}
                className={`flex-1 sm:flex-initial rounded-lg px-3 py-1.5 text-xs sm:text-sm font-medium transition-all touch-manipulation active:scale-95 ${
                  viewMode === 'iops'
                    ? 'bg-blue-500/20 text-blue-400'
                    : 'text-slate-400 hover:bg-slate-800'
                }`}
              >
                {t('monitor.iops')}
              </button>
            </div>
          </div>
          <MetricChart
            data={chartData}
            lines={[
              {
                dataKey: 'read',
                name: viewMode === 'throughput' ? t('monitor.readMbs') : t('monitor.readIops'),
                color: '#3b82f6',
              },
              {
                dataKey: 'write',
                name: viewMode === 'throughput' ? t('monitor.writeMbs') : t('monitor.writeIops'),
                color: '#10b981',
              },
            ]}
            yAxisLabel={viewMode === 'throughput' ? 'MB/s' : 'IOPS'}
            height={300}
            loading={loading}
          />
        </div>
      )}

      {availableDisks.length === 0 && !loading && (
        <div className="text-center py-8 sm:py-12 text-slate-400">
          <p>{t('monitor.noDisksDetected')}</p>
          <p className="text-xs sm:text-sm text-slate-500 mt-1">{t('monitor.waitingForData')}</p>
        </div>
      )}

      {/* Disk Benchmark Section */}
      <div className="border-t border-slate-800 pt-6 mt-6">
        <BenchmarkPanel />
      </div>
    </div>
  );
}
