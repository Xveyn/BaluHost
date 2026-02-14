/**
 * CpuTab -- CPU monitoring tab with usage, frequency, and temperature charts.
 */

import { useState, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { MetricChart } from '../monitoring';
import type { TimeRange } from '../../api/monitoring';
import { useCpuMonitoring } from '../../hooks/useMonitoring';
import { StatCard } from '../ui/StatCard';
import { formatNumber } from '../../lib/formatters';

export function CpuTab({ timeRange }: { timeRange: TimeRange }) {
  const { t } = useTranslation(['system', 'common']);
  const { current, history, loading, error } = useCpuMonitoring({ historyDuration: timeRange });
  const [viewMode, setViewMode] = useState<'overall' | 'per-thread'>('overall');

  const usageChartData = useMemo(() => {
    return history
      .filter((s) => s.usage_percent !== undefined && s.usage_percent >= 0)
      .map((s) => ({
        time: s.timestamp,
        usage: s.usage_percent,
      }));
  }, [history]);

  // Generate individual chart data for each thread (Task Manager style)
  const individualThreadCharts = useMemo(() => {
    if (viewMode !== 'per-thread' || !current?.thread_usages) return [];

    const pCores = current.p_core_count ?? 0;
    const eCores = current.e_core_count ?? 0;
    const totalThreads = current.thread_usages.length;
    const pThreadCount = pCores * 2; // P-cores have hyperthreading

    return current.thread_usages.map((currentUsage, idx) => {
      // Determine thread type
      let threadType: 'P' | 'E' | 'normal' = 'normal';
      let color = '#3b82f6'; // Default blue

      if (pCores > 0 || eCores > 0) {
        // Hybrid CPU
        if (idx < pThreadCount) {
          threadType = 'P';
          color = `hsl(${210 + (idx % 4) * 10}, 75%, ${60 + (idx % 3) * 8}%)`; // Blue spectrum
        } else {
          threadType = 'E';
          color = `hsl(${140 + (idx % 4) * 15}, 70%, ${55 + (idx % 3) * 8}%)`; // Green spectrum
        }
      } else {
        // Normal CPU - use rainbow spectrum
        const hue = (idx / totalThreads) * 360;
        color = `hsl(${hue}, 70%, 60%)`;
      }

      // Create chart data for this specific thread
      const chartData = history.map((sample) => ({
        time: sample.timestamp,
        usage: sample.thread_usages?.[idx] ?? 0,
      }));

      return {
        threadIndex: idx,
        threadType,
        color,
        currentUsage,
        chartData,
        label: threadType === 'normal'
          ? `CPU ${idx}`
          : `${threadType === 'P' ? 'P-Core' : 'E-Core'} ${idx}`,
      };
    });
  }, [history, viewMode, current]);

  // Check if this is a hybrid CPU
  const isHybridCpu = (current?.p_core_count ?? 0) > 0 || (current?.e_core_count ?? 0) > 0;

  const temperatureChartData = useMemo(() => {
    return history
      .filter((s) => s.temperature_celsius !== null && s.temperature_celsius !== undefined)
      .map((s) => ({
        time: s.timestamp,
        temperature: s.temperature_celsius,
      }));
  }, [history]);

  const hasTemperatureData = temperatureChartData.length > 0;

  // Build core info string
  const coreInfo = useMemo(() => {
    if (!current) return null;
    const cores = current.core_count ?? 0;
    const threads = current.thread_count ?? cores;
    const pCores = current.p_core_count;
    const eCores = current.e_core_count;

    // Debug: Log thread_usages to console
    if (current.thread_usages) {
      console.log('[CPU Monitor] Thread usages received:', current.thread_usages.length, 'threads');
    } else {
      console.log('[CPU Monitor] No thread_usages data received from backend');
    }

    // If we have P/E core info (Intel hybrid)
    if (pCores !== null && pCores !== undefined && eCores !== null && eCores !== undefined) {
      return {
        main: t('monitor.coresThreads', { cores, threads }),
        detail: `${pCores} ${t('monitor.pCores')}, ${eCores} ${t('monitor.eCores')}`,
        isHybrid: true,
      };
    }

    return {
      main: `${cores} ${t('monitor.cores')}`,
      detail: `${threads} ${t('monitor.threads')}`,
      isHybrid: false,
    };
  }, [current]);

  if (error) {
    return <div className="text-red-400 text-center py-8">{error}</div>;
  }

  return (
    <div className="space-y-4 sm:space-y-6 min-w-0">
      {/* Current Stats */}
      <div className="grid grid-cols-1 min-[400px]:grid-cols-2 gap-3 sm:gap-5 lg:grid-cols-4">
        <StatCard
          label={t('monitor.cpuUsage')}
          value={current?.usage_percent != null ? formatNumber(current.usage_percent, 1) : '0'}
          unit="%"
          color="blue"
          icon={<span className="text-blue-400 text-base sm:text-xl">%</span>}
        />
        <StatCard
          label={t('monitor.frequency')}
          value={current?.frequency_mhz ? formatNumber(current.frequency_mhz / 1000, 2) : '-'}
          unit="GHz"
          color="purple"
          icon={<span className="text-purple-400 text-base sm:text-xl">~</span>}
        />
        <StatCard
          label={t('monitor.temperature')}
          value={current?.temperature_celsius != null ? formatNumber(current.temperature_celsius, 1) : '-'}
          unit="°C"
          color="orange"
          icon={<span className="text-orange-400 text-base sm:text-xl">🌡</span>}
        />
        {/* Cores & Threads Card */}
        <div className="card border-slate-800/60 bg-gradient-to-br from-green-500/10 to-transparent p-3 sm:p-5">
          <div className="flex items-center justify-between">
            <div className="min-w-0 flex-1">
              <p className="text-[10px] sm:text-xs font-medium uppercase tracking-wider text-slate-400">{t('monitor.processor')}</p>
              <p className="mt-1 sm:mt-2 text-base sm:text-xl font-semibold text-white truncate">
                {coreInfo?.main ?? '-'}
              </p>
              {coreInfo?.detail && (
                <p className={`mt-0.5 sm:mt-1 text-xs sm:text-sm truncate ${coreInfo.isHybrid ? 'text-cyan-400' : 'text-slate-400'}`}>
                  {coreInfo.detail}
                </p>
              )}
            </div>
            <div className="rounded-full bg-green-500/20 p-2 sm:p-3 flex-shrink-0 ml-2">
              <span className="text-green-400 text-base sm:text-xl">#</span>
            </div>
          </div>
        </div>
      </div>

      {/* Usage Chart - Toggle Buttons */}
      <div className="flex items-center justify-between">
        <h3 className="text-base sm:text-lg font-semibold text-white">
          {viewMode === 'overall' ? t('monitor.cpuUsage') : t('monitor.cpuUsagePerThread')}
        </h3>
        {current?.thread_usages && current.thread_usages.length > 0 && (
          <div className="flex gap-2">
            <button
              onClick={() => setViewMode('overall')}
              className={`flex-1 sm:flex-initial rounded-lg px-3 py-1.5 text-xs sm:text-sm font-medium transition-all touch-manipulation active:scale-95 ${
                viewMode === 'overall'
                  ? 'bg-blue-500/20 text-blue-400'
                  : 'text-slate-400 hover:bg-slate-800'
              }`}
            >
              {t('monitor.overall')}
            </button>
            <button
              onClick={() => setViewMode('per-thread')}
              className={`flex-1 sm:flex-initial rounded-lg px-3 py-1.5 text-xs sm:text-sm font-medium transition-all touch-manipulation active:scale-95 ${
                viewMode === 'per-thread'
                  ? 'bg-blue-500/20 text-blue-400'
                  : 'text-slate-400 hover:bg-slate-800'
              }`}
            >
              {t('monitor.perThread')}
            </button>
          </div>
        )}
      </div>

      {/* Overall CPU Chart */}
      {viewMode === 'overall' && (
        <div className="card border-slate-800/60 bg-slate-900/55 p-4 sm:p-6">
          <MetricChart
            data={usageChartData}
            lines={[{ dataKey: 'usage', name: t('monitor.usagePercent'), color: '#3b82f6' }]}
            yAxisLabel="%"
            yAxisDomain={[0, 100]}
            height={250}
            loading={loading}
            showArea
            timeRange={timeRange}
          />
        </div>
      )}

      {/* Per-Thread Charts - Task Manager Style Grid */}
      {viewMode === 'per-thread' && individualThreadCharts.length > 0 && (
        <>
          {/* P-Cores Section (for hybrid CPUs) */}
          {isHybridCpu && individualThreadCharts.some(tc => tc.threadType === 'P') && (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <div className="h-3 w-3 rounded-full bg-blue-500"></div>
                <h4 className="text-sm sm:text-base font-semibold text-white">
                  {t('monitor.pCoresPerformance')} - {t('monitor.coresThreadsCount', { cores: current?.p_core_count, threads: (current?.p_core_count ?? 0) * 2 })}
                </h4>
              </div>
              <div className="grid grid-cols-1 min-[400px]:grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-3">
                {individualThreadCharts
                  .filter(thread => thread.threadType === 'P')
                  .map((thread) => (
                    <div
                      key={thread.threadIndex}
                      className="card border-slate-800/60 bg-gradient-to-br from-blue-500/5 to-transparent p-3"
                    >
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs font-medium text-slate-300">{thread.label}</span>
                        <span className="text-xs font-bold text-blue-400">
                          {formatNumber(thread.currentUsage, 0)}%
                        </span>
                      </div>
                      <MetricChart
                        data={thread.chartData}
                        lines={[{ dataKey: 'usage', name: '', color: thread.color }]}
                        yAxisDomain={[0, 100]}
                        height={100}
                        loading={loading}
                        showArea
                        compact
                      />
                      {/* Progress bar indicator */}
                      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
                        <div
                          className="h-full rounded-full transition-all duration-300"
                          style={{
                            width: `${thread.currentUsage}%`,
                            backgroundColor: thread.color,
                          }}
                        />
                      </div>
                    </div>
                  ))}
              </div>
            </div>
          )}

          {/* E-Cores Section (for hybrid CPUs) */}
          {isHybridCpu && individualThreadCharts.some(tc => tc.threadType === 'E') && (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <div className="h-3 w-3 rounded-full bg-green-500"></div>
                <h4 className="text-sm sm:text-base font-semibold text-white">
                  {t('monitor.eCoresEfficiency')} - {t('monitor.coresThreadsCount', { cores: current?.e_core_count, threads: current?.e_core_count })}
                </h4>
              </div>
              <div className="grid grid-cols-1 min-[400px]:grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-3">
                {individualThreadCharts
                  .filter(thread => thread.threadType === 'E')
                  .map((thread) => (
                    <div
                      key={thread.threadIndex}
                      className="card border-slate-800/60 bg-gradient-to-br from-green-500/5 to-transparent p-3"
                    >
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs font-medium text-slate-300">{thread.label}</span>
                        <span className="text-xs font-bold text-green-400">
                          {formatNumber(thread.currentUsage, 0)}%
                        </span>
                      </div>
                      <MetricChart
                        data={thread.chartData}
                        lines={[{ dataKey: 'usage', name: '', color: thread.color }]}
                        yAxisDomain={[0, 100]}
                        height={100}
                        loading={loading}
                        showArea
                        compact
                      />
                      {/* Progress bar indicator */}
                      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
                        <div
                          className="h-full rounded-full transition-all duration-300"
                          style={{
                            width: `${thread.currentUsage}%`,
                            backgroundColor: thread.color,
                          }}
                        />
                      </div>
                    </div>
                  ))}
              </div>
            </div>
          )}

          {/* All Threads Section (for non-hybrid CPUs) */}
          {!isHybridCpu && (
            <div className="space-y-3">
              <h4 className="text-sm sm:text-base font-semibold text-white">
                {t('monitor.logicalProcessors')} ({individualThreadCharts.length})
              </h4>
              <div className="grid grid-cols-1 min-[400px]:grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-3">
                {individualThreadCharts.map((thread) => (
                  <div
                    key={thread.threadIndex}
                    className="card border-slate-800/60 bg-slate-900/55 p-3"
                    style={{
                      background: `linear-gradient(to bottom right, ${thread.color}08, transparent)`,
                    }}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-medium text-slate-300">{thread.label}</span>
                      <span
                        className="text-xs font-bold"
                        style={{ color: thread.color }}
                      >
                        {formatNumber(thread.currentUsage, 0)}%
                      </span>
                    </div>
                    <MetricChart
                      data={thread.chartData}
                      lines={[{ dataKey: 'usage', name: '', color: thread.color }]}
                      yAxisDomain={[0, 100]}
                      height={100}
                      loading={loading}
                      showArea
                      compact
                    />
                    {/* Progress bar indicator */}
                    <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
                      <div
                        className="h-full rounded-full transition-all duration-300"
                        style={{
                          width: `${thread.currentUsage}%`,
                          backgroundColor: thread.color,
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {/* Temperature Chart - only show if data available */}
      {hasTemperatureData && (
        <div className="card border-slate-800/60 bg-slate-900/55 p-4 sm:p-6">
          <h3 className="mb-3 sm:mb-4 text-base sm:text-lg font-semibold text-white">{t('monitor.cpuTemperature')}</h3>
          <MetricChart
            data={temperatureChartData}
            lines={[{ dataKey: 'temperature', name: t('monitor.temperatureUnit'), color: '#f97316' }]}
            yAxisLabel="°C"
            yAxisDomain={[0, 'auto']}
            height={250}
            loading={loading}
            showArea
            timeRange={timeRange}
          />
        </div>
      )}
    </div>
  );
}
