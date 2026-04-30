/**
 * Combined CPU + GPU dashboard panel.
 *
 * Compact: single split card — top "CPU" + value + bar (with small vendor
 * icon), divider, bottom "GPU" + value + bar (with small vendor icon).
 * Same height as sibling stat cards.
 *
 * Expanded: same card grows in place to show full details. Rendered as
 * an absolute overlay above an invisible spacer so the surrounding grid
 * layout doesn't shift.
 *
 * Colors derive from the hardware vendor (AMD red, Intel blue, NVIDIA
 * green) — both halves can be different and blend in the middle.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ChevronDown } from 'lucide-react';
import { formatBytes, formatNumber } from '../../lib/formatters';
import type { GpuDeviceInfo, GpuSample } from '../../api/monitoring';

type DeltaTone = 'increase' | 'decrease' | 'steady' | 'live';
type Vendor = 'amd' | 'intel' | 'nvidia' | 'unknown';

interface CpuPart {
  vendor: Vendor;
  usagePercent: number;
  meta: string;
  submeta?: string;
  delta: { label: string; tone: DeltaTone };
}

interface GpuPart {
  vendor: Vendor;
  info: GpuDeviceInfo;
  sample: GpuSample | null;
}

interface Props {
  cpu: CpuPart;
  gpu: GpuPart;
}

interface VendorColor {
  text: string;       // tailwind class for icon color
  gradient: string;   // tailwind gradient classes
  shadow: string;     // inline shadow color
  rgb: string;        // "r,g,b" for inline gradient backgrounds
}

const VENDOR_COLORS: Record<Vendor, VendorColor> = {
  amd:     { text: 'text-rose-400',    gradient: 'from-rose-500 to-red-500',         shadow: '0 12px 38px rgba(244,63,94,0.35)',   rgb: '244,63,94' },
  intel:   { text: 'text-sky-400',     gradient: 'from-sky-500 to-blue-500',         shadow: '0 12px 38px rgba(14,165,233,0.35)',  rgb: '14,165,233' },
  nvidia:  { text: 'text-emerald-400', gradient: 'from-emerald-500 to-green-500',    shadow: '0 12px 38px rgba(16,185,129,0.35)',  rgb: '16,185,129' },
  unknown: { text: 'text-slate-300',   gradient: 'from-slate-500 to-slate-400',      shadow: '0 12px 38px rgba(148,163,184,0.30)', rgb: '148,163,184' },
};

const cpuIconLg = (
  <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M8.25 3v1.5M4.5 8.25H3m18 0h-1.5M4.5 12H3m18 0h-1.5m-15 3.75H3m18 0h-1.5M8.25 19.5V21M12 3v1.5m0 15V21m3.75-18v1.5m0 15V21m-9-1.5h10.5a1.5 1.5 0 001.5-1.5V6a1.5 1.5 0 00-1.5-1.5H6.75A1.5 1.5 0 005.25 6v12a1.5 1.5 0 001.5 1.5z"
    />
  </svg>
);

const cpuIconSm = (
  <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M8.25 3v1.5M4.5 8.25H3m18 0h-1.5M4.5 12H3m18 0h-1.5m-15 3.75H3m18 0h-1.5M8.25 19.5V21M12 3v1.5m0 15V21m3.75-18v1.5m0 15V21m-9-1.5h10.5a1.5 1.5 0 001.5-1.5V6a1.5 1.5 0 00-1.5-1.5H6.75A1.5 1.5 0 005.25 6v12a1.5 1.5 0 001.5 1.5z"
    />
  </svg>
);

const gpuIconLg = (
  <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 7.5h16.5v9H3.75v-9zm3 3h2.25v3H6.75v-3zm5.25 0h5.25v3H12v-3z" />
  </svg>
);

const gpuIconSm = (
  <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
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
  vendor: VendorColor;
  iconSm: React.ReactNode;
  iconLg: React.ReactNode;
  expanded: boolean;
  onClick?: () => void;
}

function Section({
  title, percent, meta, submeta, deltaLabel, deltaToneClass,
  vendor, iconSm, iconLg, expanded, onClick,
}: SectionProps) {
  const clamped = Math.min(Math.max(percent, 0), 100);

  if (!expanded) {
    return (
      <button type="button" onClick={onClick} className="block w-full text-left">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-xs uppercase tracking-[0.28em] text-slate-500">{title}</p>
            <p className="mt-1 text-2xl font-semibold text-white tabular-nums">
              {formatNumber(percent, 1)}%
            </p>
          </div>
          <div
            className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br ${vendor.gradient} text-white`}
            style={{ boxShadow: vendor.shadow }}
          >
            {iconSm}
          </div>
        </div>
        <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
          <div
            className={`h-full rounded-full bg-gradient-to-r ${vendor.gradient} transition-all duration-500`}
            style={{ width: `${clamped}%` }}
          />
        </div>
      </button>
    );
  }

  return (
    <button type="button" onClick={onClick} className="block w-full text-left">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-xs uppercase tracking-[0.28em] text-slate-500">{title}</p>
          <p className="mt-2 text-2xl sm:text-3xl font-semibold text-white truncate tabular-nums">
            {formatNumber(percent, 1)}%
          </p>
        </div>
        <div
          className={`flex h-11 w-11 sm:h-12 sm:w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br ${vendor.gradient} text-white`}
          style={{ boxShadow: vendor.shadow }}
        >
          {iconLg}
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
          className={`h-full rounded-full bg-gradient-to-r ${vendor.gradient} transition-all duration-500`}
          style={{ width: `${clamped}%` }}
        />
      </div>
    </button>
  );
}

interface BodyProps {
  cpu: CpuPart;
  gpu: GpuPart;
  cpuColor: VendorColor;
  gpuColor: VendorColor;
  expanded: boolean;
  onCpuClick: () => void;
  onGpuClick: () => void;
}

function PanelBody({ cpu, gpu, cpuColor, gpuColor, expanded, onCpuClick, onGpuClick }: BodyProps) {
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
        vendor={cpuColor}
        iconSm={cpuIconSm}
        iconLg={cpuIconLg}
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
        vendor={gpuColor}
        iconSm={gpuIconSm}
        iconLg={gpuIconLg}
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

  const cpuColor = VENDOR_COLORS[cpu.vendor];
  const gpuColor = VENDOR_COLORS[gpu.vendor];

  // Subtle vendor tint — only visible on hover so the compact card blends
  // with the rest of the dashboard at rest. Both vendor colors meet softly
  // in the middle of the panel.
  const hoverTintStyle = useMemo(() => ({
    background: `linear-gradient(to bottom, rgba(${cpuColor.rgb},0.10) 0%, rgba(${cpuColor.rgb},0.03) 45%, rgba(${gpuColor.rgb},0.03) 55%, rgba(${gpuColor.rgb},0.10) 100%)`,
  }), [cpuColor.rgb, gpuColor.rgb]);

  const goCpu = () => navigate('/system?tab=cpu');
  const goGpu = () => navigate('/system?tab=gpu');

  return (
    <div ref={wrapperRef} className="relative">
      {/* Invisible spacer reserves grid cell height at the compact size */}
      <div aria-hidden className="invisible pointer-events-none">
        <div className="card border-slate-800/40 bg-slate-900/60">
          <PanelBody
            cpu={cpu}
            gpu={gpu}
            cpuColor={cpuColor}
            gpuColor={gpuColor}
            expanded={false}
            onCpuClick={goCpu}
            onGpuClick={goGpu}
          />
          <div className="h-3" />
        </div>
      </div>

      {/* Real card — absolute over the spacer */}
      <div
        className={`group absolute inset-x-0 top-0 card border-slate-800/40 bg-slate-900/55 transition-all duration-200 hover:border-slate-700/60 ${
          expanded ? 'z-20 shadow-[0_24px_60px_rgba(0,0,0,0.55)] backdrop-blur' : ''
        }`}
      >
        {/* Vendor-blended tint — appears on hover, blends in the middle */}
        <div
          aria-hidden
          className="absolute inset-0 pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity duration-200"
          style={hoverTintStyle}
        />

        <div className="relative">
          <PanelBody
            cpu={cpu}
            gpu={gpu}
            cpuColor={cpuColor}
            gpuColor={gpuColor}
            expanded={expanded}
            onCpuClick={goCpu}
            onGpuClick={goGpu}
          />
        </div>

        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); setExpanded((v) => !v); }}
          aria-expanded={expanded}
          aria-label={t('stats.gpuToggle', 'Toggle full CPU/GPU details')}
          className="absolute bottom-2 right-2 z-10 flex h-7 w-7 items-center justify-center rounded-full border border-slate-700/60 bg-slate-900/80 text-slate-400 hover:border-slate-500 hover:text-slate-200 transition-colors"
        >
          <ChevronDown className={`h-4 w-4 transition-transform ${expanded ? 'rotate-180' : ''}`} />
        </button>
      </div>
    </div>
  );
}

// Vendor detection helpers for callers
export function detectCpuVendor(model: string | null | undefined): Vendor {
  if (!model) return 'unknown';
  const m = model.toLowerCase();
  if (m.includes('amd') || /\b(ryzen|epyc|threadripper|athlon)\b/.test(m)) return 'amd';
  if (m.includes('intel') || /\b(xeon|core\s*i[3579]|pentium|celeron)\b/.test(m)) return 'intel';
  return 'unknown';
}

export function detectGpuVendor(vendor: string | null | undefined): Vendor {
  if (!vendor) return 'unknown';
  const v = vendor.toLowerCase();
  if (v.includes('nvidia')) return 'nvidia';
  if (v.includes('amd') || v.includes('advanced micro') || v === '0x1002') return 'amd';
  if (v.includes('intel') || v === '0x8086') return 'intel';
  return 'unknown';
}

export type { Vendor };
