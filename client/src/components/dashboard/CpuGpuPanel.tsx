/**
 * Combined CPU + GPU dashboard panel.
 *
 * Top half = CPU, bottom half = GPU. Used in place of the standalone CPU
 * stat card on the Dashboard when a dedicated GPU is detected.
 */

import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { formatBytes, formatNumber } from '../../lib/formatters';
import type { GpuDeviceInfo, GpuSample } from '../../api/monitoring';

type DeltaTone = 'increase' | 'decrease' | 'steady' | 'live';

interface CpuPart {
  usagePercent: number;
  meta: string;
  submeta?: string;
  delta: { label: string; tone: DeltaTone };
}

interface GpuPart {
  info: GpuDeviceInfo;
  sample: GpuSample | null;
}

interface Props {
  cpu: CpuPart;
  gpu: GpuPart;
}

const cpuIcon = (
  <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M8.25 3v1.5M4.5 8.25H3m18 0h-1.5M4.5 12H3m18 0h-1.5m-15 3.75H3m18 0h-1.5M8.25 19.5V21M12 3v1.5m0 15V21m3.75-18v1.5m0 15V21m-9-1.5h10.5a1.5 1.5 0 001.5-1.5V6a1.5 1.5 0 00-1.5-1.5H6.75A1.5 1.5 0 005.25 6v12a1.5 1.5 0 001.5 1.5z"
    />
  </svg>
);

const gpuIcon = (
  <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 7.5h16.5v9H3.75v-9zm3 3h2.25v3H6.75v-3zm5.25 0h5.25v3H12v-3z" />
  </svg>
);

export function CpuGpuPanel({ cpu, gpu }: Props) {
  const navigate = useNavigate();
  const { t } = useTranslation('dashboard');

  const cpuTone = cpu.delta.tone === 'decrease'
    ? 'text-emerald-400'
    : cpu.delta.tone === 'increase'
      ? 'text-rose-300'
      : cpu.delta.tone === 'steady'
        ? 'text-slate-400'
        : 'text-sky-400';

  const gpuUsage = gpu.sample?.usage_percent ?? 0;
  const gpuTempC = gpu.sample?.temperature_edge_celsius;
  const gpuPower = gpu.sample?.power_watts;
  const gpuMeta = gpu.info.device_name +
    (gpuTempC != null ? ` · ${formatNumber(gpuTempC, 1)}°C` : '') +
    (gpuPower != null ? ` · ${formatNumber(gpuPower, 0)} W` : '');
  const gpuVram = gpu.sample?.vram_used_bytes != null && gpu.sample?.vram_total_bytes != null
    ? `VRAM ${formatBytes(gpu.sample.vram_used_bytes)} / ${formatBytes(gpu.sample.vram_total_bytes)}`
    : null;

  return (
    <div className="card border-slate-800/40 bg-slate-900/60 transition-all duration-200 hover:border-slate-700/60 hover:bg-slate-900/80 hover:shadow-[0_14px_44px_rgba(56,189,248,0.15)] !p-0 overflow-hidden">
      {/* CPU half */}
      <button
        type="button"
        onClick={() => navigate('/system?tab=cpu')}
        className="block w-full text-left p-5 hover:bg-slate-900/40 transition-colors active:scale-[0.99] touch-manipulation"
      >
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-xs uppercase tracking-[0.28em] text-slate-500">{t('stats.cpu')}</p>
            <p className="mt-2 text-2xl sm:text-3xl font-semibold text-white truncate">
              {formatNumber(cpu.usagePercent, 1)}%
            </p>
          </div>
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-500 to-fuchsia-500 text-white shadow-[0_12px_38px_rgba(139,92,246,0.35)]">
            {cpuIcon}
          </div>
        </div>
        <div className="mt-3 flex flex-col gap-1">
          <div className="flex items-center justify-between gap-2 text-xs text-slate-400">
            <span className="truncate flex-1 min-w-0">{cpu.meta}</span>
            <span className={`${cpuTone} shrink-0`}>{cpu.delta.label}</span>
          </div>
          {cpu.submeta && (
            <div className="text-xs text-slate-500 truncate">{cpu.submeta}</div>
          )}
        </div>
        <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
          <div
            className="h-full rounded-full bg-gradient-to-r from-violet-500 to-fuchsia-500 transition-all duration-500"
            style={{ width: `${Math.min(Math.max(cpu.usagePercent, 0), 100)}%` }}
          />
        </div>
      </button>

      {/* Divider */}
      <div className="h-px bg-slate-800/70" />

      {/* GPU half */}
      <button
        type="button"
        onClick={() => navigate('/system?tab=gpu')}
        className="block w-full text-left p-5 hover:bg-slate-900/40 transition-colors active:scale-[0.99] touch-manipulation"
      >
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-xs uppercase tracking-[0.28em] text-slate-500">{t('stats.gpu', 'GPU')}</p>
            <p className="mt-2 text-2xl sm:text-3xl font-semibold text-white truncate">
              {formatNumber(gpuUsage, 1)}%
            </p>
          </div>
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-emerald-500 to-teal-500 text-white shadow-[0_12px_38px_rgba(16,185,129,0.35)]">
            {gpuIcon}
          </div>
        </div>
        <div className="mt-3 flex flex-col gap-1">
          <div className="flex items-center justify-between gap-2 text-xs text-slate-400">
            <span className="truncate flex-1 min-w-0">{gpuMeta}</span>
            <span className="text-sky-400 shrink-0">Live</span>
          </div>
          {gpuVram && (
            <div className="text-xs text-slate-500 truncate">{gpuVram}</div>
          )}
        </div>
        <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
          <div
            className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-teal-500 transition-all duration-500"
            style={{ width: `${Math.min(Math.max(gpuUsage, 0), 100)}%` }}
          />
        </div>
      </button>
    </div>
  );
}
