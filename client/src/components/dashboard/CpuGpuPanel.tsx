/**
 * Combined CPU + GPU dashboard panel.
 *
 * Compact: ONE card split in half — top "CPU" + value + bar, bottom "GPU"
 * + value + bar. Same height as sibling stat cards.
 * Expanded: same card grows in place to show full details for both halves
 * (model, temp, power, VRAM, etc.). Rendered as an absolute overlay over
 * an invisible spacer so the surrounding grid layout does not shift.
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

interface SectionProps {
  title: string;
  percent: number;
  meta?: string;
  submeta?: string;
  deltaLabel: string;
  deltaToneClass: string;
  gradient: string;
  shadow: string;
  icon: React.ReactNode;
  expanded: boolean;
  onClick?: () => void;
}

function Section({
  title, percent, meta, submeta, deltaLabel, deltaToneClass,
  gradient, shadow, icon, expanded, onClick,
}: SectionProps) {
  const clamped = Math.min(Math.max(percent, 0), 100);

  if (!expanded) {
    // Compact: title + value + thin bar only
    return (
      <button
        type="button"
        onClick={onClick}
        className="block w-full text-left"
      >
        <p className="text-xs uppercase tracking-[0.28em] text-slate-500">{title}</p>
        <p className="mt-1 text-2xl font-semibold text-white tabular-nums">
          {formatNumber(percent, 1)}%
        </p>
        <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
          <div
            className={`h-full rounded-full bg-gradient-to-r ${gradient} transition-all duration-500`}
            style={{ width: `${clamped}%` }}
          />
        </div>
      </button>
    );
  }

  // Expanded: full stat-card-style row
  return (
    <button
      type="button"
      onClick={onClick}
      className="block w-full text-left"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-xs uppercase tracking-[0.28em] text-slate-500">{title}</p>
          <p className="mt-2 text-2xl sm:text-3xl font-semibold text-white truncate tabular-nums">
            {formatNumber(percent, 1)}%
          </p>
        </div>
        <div
          className={`flex h-11 w-11 sm:h-12 sm:w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br ${gradient} text-white`}
          style={{ boxShadow: shadow }}
        >
          {icon}
        </div>
      </div>
      <div className="mt-3 flex flex-col gap-1">
        {meta && (
          <div className="flex items-center justify-between gap-2 text-xs text-slate-400">
            <span className="truncate flex-1 min-w-0">{meta}</span>
            <span className={`${deltaToneClass} shrink-0`}>{deltaLabel}</span>
          </div>
        )}
        {submeta && <div className="text-xs text-slate-500 truncate">{submeta}</div>}
      </div>
      <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-slate-800">
        <div
          className={`h-full rounded-full bg-gradient-to-r ${gradient} transition-all duration-500`}
          style={{ width: `${clamped}%` }}
        />
      </div>
    </button>
  );
}

interface BodyProps {
  cpu: CpuPart;
  gpu: GpuPart;
  expanded: boolean;
  onCpuClick: () => void;
  onGpuClick: () => void;
}

function PanelBody({ cpu, gpu, expanded, onCpuClick, onGpuClick }: BodyProps) {
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
    : undefined;

  return (
    <>
      <Section
        title="CPU"
        percent={cpu.usagePercent}
        meta={cpu.meta}
        submeta={cpu.submeta}
        deltaLabel={cpu.delta.label}
        deltaToneClass={cpuTone}
        gradient="from-violet-500 to-fuchsia-500"
        shadow="0 12px 38px rgba(139,92,246,0.35)"
        icon={cpuIcon}
        expanded={expanded}
        onClick={onCpuClick}
      />
      <div className={`${expanded ? 'my-4' : 'my-3'} h-px bg-slate-800/70`} />
      <Section
        title="GPU"
        percent={gpuUsage}
        meta={expanded ? gpuMeta : undefined}
        submeta={gpuVram}
        deltaLabel="Live"
        deltaToneClass="text-sky-400"
        gradient="from-emerald-500 to-teal-500"
        shadow="0 12px 38px rgba(16,185,129,0.35)"
        icon={gpuIcon}
        expanded={expanded}
        onClick={onGpuClick}
      />
    </>
  );
}

export function CpuGpuPanel({ cpu, gpu }: Props) {
  const navigate = useNavigate();
  const { t } = useTranslation('dashboard');
  const [expanded, setExpanded] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);

  // Close overlay when clicking outside
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

  const goCpu = () => navigate('/system?tab=cpu');
  const goGpu = () => navigate('/system?tab=gpu');

  return (
    <div ref={wrapperRef} className="relative">
      {/* Invisible spacer reserves grid cell height at the compact size */}
      <div aria-hidden className="invisible pointer-events-none">
        <div className="card border-slate-800/40 bg-slate-900/60">
          <PanelBody cpu={cpu} gpu={gpu} expanded={false} onCpuClick={goCpu} onGpuClick={goGpu} />
          {/* extra space so the chevron has room */}
          <div className="h-3" />
        </div>
      </div>

      {/* Real card — absolute over the spacer, grows downward when expanded */}
      <div
        className={`absolute inset-x-0 top-0 card border-slate-800/40 transition-all duration-200 ${
          expanded
            ? 'bg-slate-900/95 z-20 shadow-[0_24px_60px_rgba(0,0,0,0.55)] backdrop-blur'
            : 'bg-slate-900/60 hover:border-slate-700/60 hover:bg-slate-900/80'
        }`}
      >
        <PanelBody cpu={cpu} gpu={gpu} expanded={expanded} onCpuClick={goCpu} onGpuClick={goGpu} />

        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); setExpanded((v) => !v); }}
          aria-expanded={expanded}
          aria-label={t('stats.gpuToggle', 'Toggle full CPU/GPU details')}
          className="absolute bottom-2 right-2 flex h-7 w-7 items-center justify-center rounded-full border border-slate-700/60 bg-slate-900/80 text-slate-400 hover:border-emerald-500/50 hover:text-emerald-400 transition-colors"
        >
          <ChevronDown className={`h-4 w-4 transition-transform ${expanded ? 'rotate-180' : ''}`} />
        </button>
      </div>
    </div>
  );
}
