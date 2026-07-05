import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  getGpuHistory,
  type GpuSample,
  type TimeRange,
} from '../../api/monitoring';
import { useGpuPresence } from '../../hooks/useGpuPresence';
import { useGpuCurrent } from '../../hooks/useGpuCurrent';
import { MetricChart } from '../monitoring';

interface Props {
  timeRange: TimeRange;
}

function formatBytes(n: number | null): string {
  if (n == null) return '—';
  if (n >= 1 << 30) return `${(n / (1 << 30)).toFixed(1)} GB`;
  if (n >= 1 << 20) return `${(n / (1 << 20)).toFixed(1)} MB`;
  return `${n} B`;
}

function fmtTemp(v?: number | null): string {
  return v != null ? `${v.toFixed(0)}°C` : '—';
}

function fmtPct(v?: number | null): string {
  return v != null ? `${v.toFixed(0)}%` : '—';
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-800/60 bg-slate-900/40 p-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="text-lg font-semibold tabular-nums text-slate-100 mt-1">{value}</div>
    </div>
  );
}

export function GpuTab({ timeRange }: Props) {
  const { t } = useTranslation('system');
  const { info } = useGpuPresence();

  // Current sample: shared `gpu.current` query (#299) — same cache/poll as the
  // dashboard GPU widget. History stays a per-timeRange one-shot fetch.
  const current = useGpuCurrent();
  const [history, setHistory] = useState<GpuSample[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [engineView, setEngineView] = useState<'overview' | 'per-engine'>('overview');

  const usageChartData = useMemo(() => {
    return history
      .filter((s) => s.usage_percent != null && s.usage_percent >= 0)
      .map((s) => ({
        time: s.timestamp,
        usage: s.usage_percent ?? 0,
      }));
  }, [history]);

  useEffect(() => {
    let cancelled = false;
    setHistoryLoading(true);
    (async () => {
      try {
        const res = await getGpuHistory(timeRange);
        if (!cancelled) setHistory(res.samples);
      } catch { /* ignore */ }
      finally {
        if (!cancelled) setHistoryLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [timeRange]);

  if (!info) return null;

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-slate-800/60 bg-slate-900/40 p-4 flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs uppercase text-slate-500">{info.vendor}</span>
            <h2 className="text-xl font-semibold text-slate-100">{info.device_name}</h2>
          </div>
          <div className="text-xs text-slate-500 mt-1">
            {info.pci_slot ?? ''}
            {info.driver_version ? ` · ${info.driver_version}` : ''}
          </div>
        </div>
        <div className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" aria-label="live" />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Kpi
          label={t('monitor.gpu.usage', 'Usage')}
          value={current?.usage_percent != null ? `${Math.round(current.usage_percent)}%` : '—'}
        />
        <Kpi
          label={t('monitor.gpu.vram', 'VRAM')}
          value={`${formatBytes(current?.vram_used_bytes ?? null)} / ${formatBytes(current?.vram_total_bytes ?? null)}`}
        />
        <Kpi
          label={t('monitor.gpu.coreClock', 'Core Clock')}
          value={current?.core_clock_mhz != null ? `${current.core_clock_mhz.toFixed(0)} MHz` : '—'}
        />
        <Kpi
          label={t('monitor.gpu.power', 'Power')}
          value={current?.power_watts != null ? `${current.power_watts.toFixed(0)} W` : '—'}
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <Kpi label={t('monitor.gpu.tempEdge', 'Edge Temp')} value={fmtTemp(current?.temperature_edge_celsius)} />
        <Kpi label={t('monitor.gpu.tempJunction', 'Junction Temp')} value={fmtTemp(current?.temperature_junction_celsius)} />
        <Kpi label={t('monitor.gpu.tempMemory', 'Memory Temp')} value={fmtTemp(current?.temperature_memory_celsius)} />
      </div>

      <div className="card border-slate-800/60 bg-slate-900/55 p-4 sm:p-6">
        <h3 className="mb-3 sm:mb-4 text-base sm:text-lg font-semibold text-white">
          {t('monitor.gpu.usageChart', 'GPU Usage')}
        </h3>
        <MetricChart
          data={usageChartData}
          lines={[{ dataKey: 'usage', name: t('monitor.usagePercent', '%'), color: '#10b981' }]}
          yAxisLabel="%"
          yAxisDomain={[0, 100]}
          height={250}
          loading={historyLoading}
          showArea
          timeRange={timeRange}
        />
      </div>

      <div className="rounded-xl border border-slate-800/60 bg-slate-900/40 p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-medium text-slate-200">{t('monitor.gpu.engines', 'Engine activity')}</h3>
          <div className="flex gap-1 text-xs bg-slate-800 rounded p-0.5">
            <button
              type="button"
              className={`px-2 py-0.5 rounded ${engineView === 'overview' ? 'bg-slate-700 text-slate-100' : 'text-slate-400'}`}
              onClick={() => setEngineView('overview')}
            >
              {t('monitor.gpu.overview', 'Overview')}
            </button>
            <button
              type="button"
              className={`px-2 py-0.5 rounded ${engineView === 'per-engine' ? 'bg-slate-700 text-slate-100' : 'text-slate-400'}`}
              onClick={() => setEngineView('per-engine')}
            >
              {t('monitor.gpu.perEngine', 'Per-Engine')}
            </button>
          </div>
        </div>
        {engineView === 'per-engine' ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Kpi label={t('monitor.gpu.engineGfx', 'Graphics')} value={fmtPct(current?.engine_gfx_percent)} />
            <Kpi label={t('monitor.gpu.engineCompute', 'Compute')} value={fmtPct(current?.engine_compute_percent)} />
            <Kpi label={t('monitor.gpu.engineDecode', 'Decode')} value={fmtPct(current?.engine_decode_percent)} />
            <Kpi label={t('monitor.gpu.engineEncode', 'Encode')} value={fmtPct(current?.engine_encode_percent)} />
          </div>
        ) : (
          <div className="text-xs text-slate-500">
            {t('monitor.gpu.overviewHint', 'Stacked engine activity over the selected time range.')}
            <div className="text-slate-300 mt-2">
              {t('monitor.gpu.samplesLoaded', 'Samples loaded')}: {history.length}
            </div>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Kpi
          label={t('monitor.gpu.fanRpm', 'Fan')}
          value={current?.fan_rpm != null ? `${current.fan_rpm} RPM` : '—'}
        />
        <Kpi
          label={t('monitor.gpu.memoryClock', 'Memory Clock')}
          value={current?.memory_clock_mhz != null ? `${current.memory_clock_mhz.toFixed(0)} MHz` : '—'}
        />
      </div>
    </div>
  );
}
