/**
 * Combined CPU + GPU dashboard panel.
 *
 * Compact: shows the CPU stat card at the same height as sibling panels
 * with a chevron toggle. Expanded: GPU section drops down as an absolute
 * overlay so the surrounding grid layout stays still.
 */

import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ChevronDown } from 'lucide-react';
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
  <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M8.25 3v1.5M4.5 8.25H3m18 0h-1.5M4.5 12H3m18 0h-1.5m-15 3.75H3m18 0h-1.5M8.25 19.5V21M12 3v1.5m0 15V21m3.75-18v1.5m0 15V21m-9-1.5h10.5a1.5 1.5 0 001.5-1.5V6a1.5 1.5 0 00-1.5-1.5H6.75A1.5 1.5 0 005.25 6v12a1.5 1.5 0 001.5 1.5z"
    />
  </svg>
);

const gpuIcon = (
  <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 7.5h16.5v9H3.75v-9zm3 3h2.25v3H6.75v-3zm5.25 0h5.25v3H12v-3z" />
  </svg>
);

export function CpuGpuPanel({ cpu, gpu }: Props) {
  const navigate = useNavigate();
  const { t } = useTranslation('dashboard');
  const [expanded, setExpanded] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);

  // Close overlay when clicking anywhere outside
  useEffect(() => {
    if (!expanded) return;
    const onDocClick = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setExpanded(false);
      }
    };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, [expanded]);

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
    <div ref={wrapperRef} className="relative">
      {/* Compact CPU card — matches sibling stat cards in height */}
      <div
        onClick={() => navigate('/system?tab=cpu')}
        className="card border-slate-800/40 bg-slate-900/60 transition-all duration-200 hover:border-slate-700/60 hover:bg-slate-900/80 hover:shadow-[0_14px_44px_rgba(56,189,248,0.15)] active:scale-[0.98] touch-manipulation cursor-pointer"
      >
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-xs uppercase tracking-[0.28em] text-slate-500">{t('stats.cpu')}</p>
            <p className="mt-2 text-2xl sm:text-3xl font-semibold text-white truncate">
              {formatNumber(cpu.usagePercent, 1)}%
            </p>
          </div>
          <div className="flex h-11 w-11 sm:h-12 sm:w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-500 to-fuchsia-500 text-white shadow-[0_12px_38px_rgba(139,92,246,0.35)]">
            {cpuIcon}
          </div>
        </div>
        <div className="mt-3 sm:mt-4 flex flex-col gap-1">
          <div className="flex items-center justify-between gap-2 text-xs text-slate-400">
            <span className="truncate flex-1 min-w-0">{cpu.meta}</span>
            <span className={`${cpuTone} shrink-0`}>{cpu.delta.label}</span>
          </div>
          {cpu.submeta && (
            <div className="text-xs text-slate-500 truncate">{cpu.submeta}</div>
          )}
        </div>
        <div className="mt-4 sm:mt-5 h-2 w-full overflow-hidden rounded-full bg-slate-800">
          <div
            className="h-full rounded-full bg-gradient-to-r from-violet-500 to-fuchsia-500 transition-all duration-500"
            style={{ width: `${Math.min(Math.max(cpu.usagePercent, 0), 100)}%` }}
          />
        </div>
      </div>

      {/* Expand toggle — bottom right of the card, doesn't trigger card click */}
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); setExpanded((v) => !v); }}
        aria-expanded={expanded}
        aria-label={t('stats.gpuToggle', 'Toggle GPU panel')}
        className="absolute bottom-2 right-2 flex h-7 w-7 items-center justify-center rounded-full border border-slate-700/60 bg-slate-900/80 text-slate-400 hover:border-emerald-500/50 hover:text-emerald-400 transition-colors z-10"
      >
        <ChevronDown className={`h-4 w-4 transition-transform ${expanded ? 'rotate-180' : ''}`} />
      </button>

      {/* GPU overlay — absolute, drops below the card without affecting grid */}
      {expanded && (
        <div
          onClick={() => navigate('/system?tab=gpu')}
          className="absolute left-0 right-0 top-[calc(100%+0.5rem)] z-20 card border-slate-800/40 bg-slate-900/95 backdrop-blur shadow-[0_24px_60px_rgba(0,0,0,0.55)] cursor-pointer transition-all duration-200 hover:border-slate-700/60 hover:bg-slate-900"
        >
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0 flex-1">
              <p className="text-xs uppercase tracking-[0.28em] text-slate-500">{t('stats.gpu', 'GPU')}</p>
              <p className="mt-2 text-2xl sm:text-3xl font-semibold text-white truncate">
                {formatNumber(gpuUsage, 1)}%
              </p>
            </div>
            <div className="flex h-11 w-11 sm:h-12 sm:w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-emerald-500 to-teal-500 text-white shadow-[0_12px_38px_rgba(16,185,129,0.35)]">
              {gpuIcon}
            </div>
          </div>
          <div className="mt-3 sm:mt-4 flex flex-col gap-1">
            <div className="flex items-center justify-between gap-2 text-xs text-slate-400">
              <span className="truncate flex-1 min-w-0">{gpuMeta}</span>
              <span className="text-sky-400 shrink-0">Live</span>
            </div>
            {gpuVram && (
              <div className="text-xs text-slate-500 truncate">{gpuVram}</div>
            )}
          </div>
          <div className="mt-4 sm:mt-5 h-2 w-full overflow-hidden rounded-full bg-slate-800">
            <div
              className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-teal-500 transition-all duration-500"
              style={{ width: `${Math.min(Math.max(gpuUsage, 0), 100)}%` }}
            />
          </div>
        </div>
      )}
    </div>
  );
}
