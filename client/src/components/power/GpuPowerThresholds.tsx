import type { GpuPowerConfig } from "../../types/gpuPower";

interface Props {
  value: GpuPowerConfig;
  onChange: (next: GpuPowerConfig) => void;
  disabled?: boolean;
}

const fields: Array<{ key: keyof GpuPowerConfig; label: string; min: number; max: number; suffix: string }> = [
  { key: "idle_window_seconds", label: "Idle window", min: 10, max: 600, suffix: "s" },
  { key: "deep_idle_extra_seconds", label: "Grace before deep idle", min: 30, max: 3600, suffix: "s" },
  { key: "deep_idle_grace_seconds", label: "Plugin unload grace", min: 0, max: 30, suffix: "s" },
  { key: "monitor_interval_seconds", label: "Monitor interval", min: 1, max: 60, suffix: "s" },
];

export function GpuPowerThresholds({ value, onChange, disabled }: Props) {
  return (
    <div className="space-y-2">
      {fields.map((f) => (
        <label key={String(f.key)} className="flex items-center justify-between gap-4">
          <span className="text-sm">{f.label}</span>
          <span className="flex items-center gap-1">
            <input
              type="number"
              min={f.min}
              max={f.max}
              disabled={disabled}
              value={Number(value[f.key])}
              onChange={(e) => onChange({ ...value, [f.key]: Number(e.target.value) })}
              className="w-20 rounded border bg-transparent px-2 py-1 text-right"
            />
            <span className="text-xs text-zinc-500">{f.suffix}</span>
          </span>
        </label>
      ))}
      <label className="flex items-center justify-between gap-4">
        <span className="text-sm">Usage threshold</span>
        <span className="flex items-center gap-1">
          <input
            type="number"
            min={0}
            max={50}
            step={0.5}
            disabled={disabled}
            value={value.usage_threshold_percent}
            onChange={(e) =>
              onChange({ ...value, usage_threshold_percent: Number(e.target.value) })
            }
            className="w-20 rounded border bg-transparent px-2 py-1 text-right"
          />
          <span className="text-xs text-zinc-500">%</span>
        </span>
      </label>
    </div>
  );
}
