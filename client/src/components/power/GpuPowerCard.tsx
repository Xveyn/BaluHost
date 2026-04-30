import { useEffect, useMemo, useState } from "react";
import { gpuPowerApi } from "../../api/gpuPower";
import type {
  GpuPowerCapabilities,
  GpuPowerConfig,
  GpuPowerStatus,
} from "../../types/gpuPower";
import { GpuPowerThresholds } from "./GpuPowerThresholds";
import { GpuPowerHardware } from "./GpuPowerHardware";

const STATE_LABELS: Record<GpuPowerStatus["current_state"], string> = {
  active: "Active",
  standby: "Standby",
  deep_idle: "Deep idle",
};

export function GpuPowerCard({ isAdmin }: { isAdmin: boolean }) {
  const [status, setStatus] = useState<GpuPowerStatus | null>(null);
  const [config, setConfig] = useState<GpuPowerConfig | null>(null);
  const [caps, setCaps] = useState<GpuPowerCapabilities | null>(null);
  const [draft, setDraft] = useState<GpuPowerConfig | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const [s, c, k] = await Promise.all([
          gpuPowerApi.getStatus(),
          gpuPowerApi.getConfig(),
          gpuPowerApi.getCapabilities(),
        ]);
        if (cancelled) return;
        setStatus(s);
        setConfig(c);
        setCaps(k);
        setDraft(c);
      } catch (err) {
        if (!cancelled) setError(String(err));
      }
    };
    void load();
    const id = window.setInterval(() => void load(), 5000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const dirty = useMemo(
    () => draft && config && JSON.stringify(draft) !== JSON.stringify(config),
    [draft, config],
  );

  const onSave = async () => {
    if (!draft) return;
    setSaving(true);
    setError(null);
    try {
      const saved = await gpuPowerApi.putConfig(draft);
      setConfig(saved);
      setDraft(saved);
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      setError(axiosErr?.response?.data?.detail || String(err));
    } finally {
      setSaving(false);
    }
  };

  if (status && !status.detected) {
    return (
      <section className="rounded-lg border p-4">
        <h3 className="text-base font-semibold">GPU Power Management</h3>
        <p className="text-sm text-zinc-500">No discrete GPU detected.</p>
      </section>
    );
  }

  return (
    <section className="rounded-lg border p-4 space-y-4">
      <header className="flex items-center justify-between">
        <h3 className="text-base font-semibold">GPU Power Management</h3>
        {status && (
          <span className="text-sm">
            <span className="font-mono">{STATE_LABELS[status.current_state]}</span>
            {status.vendor && <span className="text-zinc-500"> · {status.vendor}</span>}
          </span>
        )}
      </header>

      {status && (
        <ul className="text-sm grid grid-cols-2 gap-x-4 gap-y-1 text-zinc-700 dark:text-zinc-300">
          <li>Displays connected: {status.display_count}</li>
          <li>Usage: {status.usage_percent ?? 0}%</li>
          <li>Active demands: {status.active_demands.length}</li>
          <li>Permission: {status.has_write_permission ? "ok" : "missing"}</li>
        </ul>
      )}

      {draft && (
        <>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              disabled={!isAdmin || saving}
              checked={draft.enabled}
              onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })}
            />
            Enable GPU power management
          </label>

          <details>
            <summary className="cursor-pointer text-sm">Thresholds</summary>
            <div className="pt-2">
              <GpuPowerThresholds
                value={draft}
                onChange={setDraft}
                disabled={!isAdmin || saving}
              />
            </div>
          </details>

          <details>
            <summary className="cursor-pointer text-sm">Hardware overrides</summary>
            <div className="pt-2">
              <GpuPowerHardware
                value={draft}
                caps={caps}
                onChange={setDraft}
                disabled={!isAdmin || saving}
              />
            </div>
          </details>

          {isAdmin && (
            <div className="flex items-center gap-2">
              <button
                onClick={() => void onSave()}
                disabled={!dirty || saving}
                className="rounded bg-blue-600 px-3 py-1 text-sm text-white disabled:opacity-50"
              >
                {saving ? "Saving..." : "Save"}
              </button>
              <button
                onClick={() => setDraft(config)}
                disabled={!dirty || saving}
                className="rounded border px-3 py-1 text-sm disabled:opacity-50"
              >
                Reset
              </button>
              {error && <span className="text-sm text-red-500">{error}</span>}
            </div>
          )}
        </>
      )}
    </section>
  );
}
