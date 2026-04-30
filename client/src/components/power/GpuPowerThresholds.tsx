import { useTranslation } from 'react-i18next';
import type { GpuPowerConfig } from '../../types/gpuPower';

interface Props {
  value: GpuPowerConfig;
  onChange: (next: GpuPowerConfig) => void;
  disabled?: boolean;
}

interface FieldDef {
  key: keyof Pick<
    GpuPowerConfig,
    'idle_window_seconds' | 'deep_idle_extra_seconds' | 'deep_idle_grace_seconds' | 'monitor_interval_seconds'
  >;
  labelKey: string;
  min: number;
  max: number;
  suffix: string;
}

const FIELDS: FieldDef[] = [
  { key: 'idle_window_seconds', labelKey: 'system:power.gpu.thresholds.idleWindow', min: 10, max: 600, suffix: 's' },
  { key: 'deep_idle_extra_seconds', labelKey: 'system:power.gpu.thresholds.deepIdleExtra', min: 30, max: 3600, suffix: 's' },
  { key: 'deep_idle_grace_seconds', labelKey: 'system:power.gpu.thresholds.deepIdleGrace', min: 0, max: 30, suffix: 's' },
  { key: 'monitor_interval_seconds', labelKey: 'system:power.gpu.thresholds.monitorInterval', min: 1, max: 60, suffix: 's' },
];

export function GpuPowerThresholds({ value, onChange, disabled }: Props) {
  const { t } = useTranslation(['system']);

  return (
    <div className="space-y-3">
      {FIELDS.map((f) => (
        <Row
          key={f.key}
          label={t(f.labelKey)}
          suffix={f.suffix}
          min={f.min}
          max={f.max}
          disabled={disabled}
          value={Number(value[f.key])}
          onChange={(v) => onChange({ ...value, [f.key]: v })}
        />
      ))}
      <Row
        label={t('system:power.gpu.thresholds.usageThreshold')}
        suffix="%"
        min={0}
        max={50}
        step={0.5}
        disabled={disabled}
        value={value.usage_threshold_percent}
        onChange={(v) => onChange({ ...value, usage_threshold_percent: v })}
      />
    </div>
  );
}

interface RowProps {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  suffix: string;
  disabled?: boolean;
  onChange: (v: number) => void;
}

function Row({ label, value, min, max, step = 1, suffix, disabled, onChange }: RowProps) {
  return (
    <label className="flex items-center justify-between gap-4">
      <span className="text-sm text-slate-300">{label}</span>
      <span className="flex items-center gap-2">
        <input
          type="number"
          min={min}
          max={max}
          step={step}
          disabled={disabled}
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          className="w-24 rounded-lg border border-slate-700/50 bg-slate-900/60 px-2 py-1 text-right text-sm text-white focus:outline-none focus:ring-1 focus:ring-emerald-500/40 disabled:opacity-50"
        />
        <span className="w-6 text-xs text-slate-500">{suffix}</span>
      </span>
    </label>
  );
}
