import type {
  AmdProfileMode,
  AmdStateConfig,
  GpuPowerCapabilities,
  GpuPowerConfig,
  NvidiaStateConfig,
} from "../../types/gpuPower";

interface Props {
  value: GpuPowerConfig;
  caps: GpuPowerCapabilities | null;
  onChange: (next: GpuPowerConfig) => void;
  disabled?: boolean;
}

const STATES: Array<{ key: "active" | "standby" | "deep_idle"; label: string }> = [
  { key: "active", label: "Active" },
  { key: "standby", label: "Standby" },
  { key: "deep_idle", label: "Deep idle" },
];

export function GpuPowerHardware({ value, caps, onChange, disabled }: Props) {
  if (!caps || caps.vendor === null) {
    return <p className="text-xs text-zinc-500">No GPU detected — hardware overrides unavailable.</p>;
  }
  if (caps.vendor === "amd" || caps.vendor === "dev") {
    return <AmdSection value={value} caps={caps} onChange={onChange} disabled={disabled} />;
  }
  if (caps.vendor === "nvidia") {
    return <NvidiaSection value={value} caps={caps} onChange={onChange} disabled={disabled} />;
  }
  return null;
}

function AmdSection({ value, caps, onChange, disabled }: Props) {
  const setField = (state: "active" | "standby" | "deep_idle", patch: Partial<AmdStateConfig>) => {
    const key = `amd_${state}` as const;
    onChange({ ...value, [key]: { ...value[key], ...patch } });
  };

  return (
    <div className="space-y-3">
      <h4 className="text-sm font-medium">AMD per-state overrides</h4>
      {STATES.map(({ key, label }) => {
        const sc = value[`amd_${key}`];
        return (
          <div key={key} className="grid grid-cols-3 gap-2 items-center">
            <span className="text-sm">{label}</span>
            <select
              disabled={disabled}
              value={sc.performance_level ?? ""}
              onChange={(e) =>
                setField(key, { performance_level: e.target.value || null })
              }
              className="rounded border bg-transparent px-2 py-1 text-sm"
            >
              <option value="">(unset)</option>
              {caps?.amd_performance_levels.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
            <select
              disabled={disabled}
              value={sc.profile_mode ?? ""}
              onChange={(e) =>
                setField(key, { profile_mode: (e.target.value || null) as AmdProfileMode | null })
              }
              className="rounded border bg-transparent px-2 py-1 text-sm"
            >
              <option value="">(unset)</option>
              {caps?.amd_profile_modes.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </div>
        );
      })}
    </div>
  );
}

function NvidiaSection({ value, caps, onChange, disabled }: Props) {
  const setField = (state: "active" | "standby" | "deep_idle", patch: Partial<NvidiaStateConfig>) => {
    const key = `nvidia_${state}` as const;
    onChange({ ...value, [key]: { ...value[key], ...patch } });
  };

  return (
    <div className="space-y-3">
      <h4 className="text-sm font-medium">
        NVIDIA per-state clocks (range:&nbsp;
        {caps?.nvidia_min_clock_mhz ?? "?"}–{caps?.nvidia_max_clock_mhz ?? "?"} MHz)
      </h4>
      {STATES.map(({ key, label }) => {
        const sc = value[`nvidia_${key}`];
        return (
          <div key={key} className="grid grid-cols-4 gap-2 items-center">
            <span className="text-sm">{label}</span>
            <input
              type="number"
              placeholder="min MHz"
              disabled={disabled}
              value={sc.min_clock_mhz ?? ""}
              onChange={(e) =>
                setField(key, {
                  min_clock_mhz: e.target.value === "" ? null : Number(e.target.value),
                })
              }
              className="rounded border bg-transparent px-2 py-1 text-sm"
            />
            <input
              type="number"
              placeholder="max MHz"
              disabled={disabled}
              value={sc.max_clock_mhz ?? ""}
              onChange={(e) =>
                setField(key, {
                  max_clock_mhz: e.target.value === "" ? null : Number(e.target.value),
                })
              }
              className="rounded border bg-transparent px-2 py-1 text-sm"
            />
            <input
              type="number"
              placeholder="power W"
              disabled={disabled}
              value={sc.power_limit_watts ?? ""}
              onChange={(e) =>
                setField(key, {
                  power_limit_watts: e.target.value === "" ? null : Number(e.target.value),
                })
              }
              className="rounded border bg-transparent px-2 py-1 text-sm"
            />
          </div>
        );
      })}
    </div>
  );
}
