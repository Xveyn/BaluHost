import { type FormEvent, useEffect, useMemo, useState } from 'react';
import toast from 'react-hot-toast';
import {
  finalizeRaidRebuild,
  getRaidStatus,
  markDeviceFailed,
  startRaidRebuild,
  type RaidArray,
  type RaidDevice,
  type RaidOptionsPayload,
  type RaidSpeedLimits,
  updateRaidOptions,
} from '../api/raid';

const REFRESH_INTERVAL_MS = 8000;

const formatBytes = (bytes: number): string => {
  if (!Number.isFinite(bytes) || bytes <= 0) {
    return '0 B';
  }

  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const size = bytes / 1024 ** exponent;
  return `${size >= 100 ? Math.round(size) : size.toFixed(1)} ${units[exponent]}`;
};

const statusStyles: Record<string, string> = {
  optimal: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200',
  rebuilding: 'border-sky-500/40 bg-sky-500/15 text-sky-100',
  degraded: 'border-amber-500/40 bg-amber-500/15 text-amber-100',
  inactive: 'border-slate-600/50 bg-slate-800/60 text-slate-300',
};

const deviceStyles: Record<string, string> = {
  active: 'border-emerald-400/30 bg-emerald-500/10 text-emerald-200',
  rebuilding: 'border-sky-400/30 bg-sky-500/10 text-sky-100',
  failed: 'border-rose-500/40 bg-rose-500/15 text-rose-200',
  removed: 'border-rose-500/30 bg-rose-500/10 text-rose-200',
  spare: 'border-indigo-400/30 bg-indigo-500/10 text-indigo-100',
  blocked: 'border-amber-500/30 bg-amber-500/10 text-amber-100',
  'write-mostly': 'border-amber-500/30 bg-amber-500/10 text-amber-100',
};

const getStatusStyle = (status: string): string => statusStyles[status] ?? 'border-slate-700/70 bg-slate-900/65 text-slate-200';

const getDeviceStyle = (state: string): string => deviceStyles[state] ?? 'border-slate-700/60 bg-slate-900/60 text-slate-300';

const upcase = (value: string): string => value.charAt(0).toUpperCase() + value.slice(1);

const canStartRebuild = (device: RaidDevice): boolean => device.state === 'failed';

const canSimulateFailure = (device: RaidDevice): boolean => ['active', 'spare', 'write-mostly'].includes(device.state);

const shouldShowFinalize = (array: RaidArray): boolean => ['rebuilding', 'degraded'].includes(array.status.toLowerCase());

export default function RaidManagement() {
  const [arrays, setArrays] = useState<RaidArray[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<boolean>(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [speedLimits, setSpeedLimits] = useState<RaidSpeedLimits | null>(null);

  const loadStatus = async (notifySuccess = false) => {
    try {
      const status = await getRaidStatus();
      setArrays(status.arrays ?? []);
      setSpeedLimits(status.speed_limits ?? null);
      setError(null);
      setLastUpdated(new Date());
      if (notifySuccess) {
        toast.success('RAID-Status aktualisiert');
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'RAID-Status konnte nicht geladen werden.';
      setError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadStatus();
    const intervalId = window.setInterval(() => {
      void loadStatus();
    }, REFRESH_INTERVAL_MS);

    return () => window.clearInterval(intervalId);
  }, []);

  const refreshDisabled = useMemo(() => busy || loading, [busy, loading]);

  const handleSimulateFailure = async (array: RaidArray, device?: RaidDevice) => {
    setBusy(true);
    try {
      const response = await markDeviceFailed(array.name, device?.name);
      toast.success(response.message);
      await loadStatus();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Simulation fehlgeschlagen.';
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  const handleStartRebuild = async (array: RaidArray, device: RaidDevice) => {
    setBusy(true);
    try {
      const response = await startRaidRebuild(array.name, device.name);
      toast.success(response.message);
      await loadStatus();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Rebuild konnte nicht gestartet werden.';
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  const handleFinalize = async (array: RaidArray) => {
    setBusy(true);
    try {
      const response = await finalizeRaidRebuild(array.name);
      toast.success(response.message);
      await loadStatus();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Finalize fehlgeschlagen.';
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  const handleToggleBitmap = async (array: RaidArray) => {
    setBusy(true);
    try {
      const response = await updateRaidOptions({
        array: array.name,
        enable_bitmap: !array.bitmap,
      });
      toast.success(response.message);
      await loadStatus();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Bitmap konnte nicht aktualisiert werden.';
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  const handleTriggerScrub = async (array: RaidArray) => {
    setBusy(true);
    try {
      const response = await updateRaidOptions({
        array: array.name,
        trigger_scrub: true,
      });
      toast.success(response.message);
      await loadStatus();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Überprüfung konnte nicht gestartet werden.';
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  const handleWriteMostly = async (array: RaidArray, device: RaidDevice) => {
    setBusy(true);
    try {
      const response = await updateRaidOptions({
        array: array.name,
        write_mostly_device: device.name,
        write_mostly: device.state !== 'write-mostly',
      });
      toast.success(response.message);
      await loadStatus();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Write-mostly konnte nicht angepasst werden.';
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  const handleRemoveDevice = async (array: RaidArray, device: RaidDevice) => {
    setBusy(true);
    try {
      const response = await updateRaidOptions({
        array: array.name,
        remove_device: device.name,
      });
      toast.success(response.message);
      await loadStatus();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Gerät konnte nicht entfernt werden.';
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  const handleAddSpare = async (event: FormEvent<HTMLFormElement>, array: RaidArray) => {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const device = formData.get('spare-device');
    event.currentTarget.reset();
    const rawDevice = typeof device === 'string' ? device.trim() : '';
    if (!rawDevice) {
      toast.error('Bitte Gerätenamen angeben.');
      return;
    }

    setBusy(true);
    try {
      const response = await updateRaidOptions({ array: array.name, add_spare: rawDevice });
      toast.success(response.message);
      await loadStatus();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Spare-Gerät konnte nicht hinzugefügt werden.';
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  const handleUpdateSpeed = async (event: FormEvent<HTMLFormElement>, array: RaidArray) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const minRaw = data.get('speed-min');
    const maxRaw = data.get('speed-max');

    const payload: RaidOptionsPayload = { array: array.name };
    if (typeof minRaw === 'string' && minRaw.trim()) {
      payload.set_speed_limit_min = Number(minRaw.trim());
    }
    if (typeof maxRaw === 'string' && maxRaw.trim()) {
      payload.set_speed_limit_max = Number(maxRaw.trim());
    }

    if (payload.set_speed_limit_min === undefined && payload.set_speed_limit_max === undefined) {
      toast.error('Bitte mindestens einen Geschwindigkeitswert setzen.');
      return;
    }

    setBusy(true);
    try {
      const response = await updateRaidOptions(payload);
      toast.success(response.message);
      await loadStatus();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Geschwindigkeitslimit konnte nicht gesetzt werden.';
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold text-white">RAID Control</h1>
          <p className="mt-1 text-sm text-slate-400">
            Überwache Array-Integrität, simuliere Ausfälle und steuere Rebuilds.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {lastUpdated && (
            <span className="text-xs uppercase tracking-[0.24em] text-slate-500">
              Aktualisiert {lastUpdated.toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={() => loadStatus(true)}
            disabled={refreshDisabled}
            className={`rounded-xl border px-4 py-2 text-sm font-medium transition ${
              refreshDisabled
                ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                : 'border-sky-500/30 bg-sky-500/10 text-sky-200 hover:border-sky-500/50 hover:bg-sky-500/15'
            }`}
          >
            Jetzt aktualisieren
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
          {error}
        </div>
      )}

      {loading ? (
        <div className="card border-slate-800/60 bg-slate-900/55 py-12 text-center">
          <p className="text-sm text-slate-500">Lade RAID-Status...</p>
        </div>
      ) : arrays.length === 0 ? (
        <div className="card border-slate-800/60 bg-slate-900/55 py-12 text-center text-sm text-slate-400">
          Es wurden keine RAID-Arrays erkannt. Stelle sicher, dass das System mdadm nutzt und die Arrays aktiv sind.
        </div>
      ) : (
        <div className="space-y-6">
          {speedLimits && (
            <div className="card border-slate-800/60 bg-slate-900/55 px-6 py-5">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <p className="text-xs uppercase tracking-[0.3em] text-slate-500">Synchronisationslimits</p>
                  <p className="mt-2 text-sm text-slate-300">
                    Mindestgeschwindigkeit: {speedLimits.minimum ?? 'Systemdefault'} kB/s · Maximal: {speedLimits.maximum ?? 'Systemdefault'} kB/s
                  </p>
                </div>
                <p className="text-xs text-slate-500">
                  Werte gelten global für alle mdadm-Arrays.
                </p>
              </div>
            </div>
          )}

          {arrays.map((array) => {
            const lowerStatus = array.status.toLowerCase();
            const showFinalize = shouldShowFinalize(array);

            return (
              <div key={array.name} className="card border-slate-800/60 bg-slate-900/55">
                <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800/60 px-6 py-5">
                  <div className="space-y-1">
                    <div className="flex items-center gap-3">
                      <h2 className="text-xl font-semibold text-white">{array.name}</h2>
                      <span className={`rounded-full border px-3 py-1 text-xs font-medium ${getStatusStyle(lowerStatus)}`}>
                        {upcase(lowerStatus)}
                      </span>
                      <span className="rounded-full border border-slate-700/70 bg-slate-900/60 px-3 py-1 text-xs uppercase tracking-[0.26em] text-slate-400">
                        {array.level.toUpperCase()}
                      </span>
                      <span className="rounded-full border border-slate-800/70 bg-slate-900/60 px-3 py-1 text-xs text-slate-400">
                        Bitmap: {array.bitmap ? array.bitmap : 'aus'}
                      </span>
                      {array.sync_action && (
                        <span className="rounded-full border border-slate-800/70 bg-slate-900/60 px-3 py-1 text-xs text-slate-400">
                          Sync: {array.sync_action}
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-slate-400">
                      Kapazität {formatBytes(array.size_bytes)} · {array.devices.length} Laufwerke
                    </p>
                    <div className="flex flex-wrap gap-2 text-xs text-slate-500">
                      <span>Write-mostly Devices: {array.devices.filter((device) => device.state === 'write-mostly').length}</span>
                      <span>Spare Devices: {array.devices.filter((device) => device.state === 'spare').length}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    {array.resync_progress !== null && array.resync_progress !== undefined && (
                      <div className="flex flex-col items-end text-sm text-slate-300">
                        <span>Synchronisierung</span>
                        <span className="text-slate-200">{array.resync_progress.toFixed(1)}%</span>
                      </div>
                    )}
                    <button
                      onClick={() => handleToggleBitmap(array)}
                      disabled={busy}
                      className={`rounded-xl border px-4 py-2 text-sm transition ${
                        busy
                          ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                          : 'border-slate-700/70 bg-slate-900/60 text-slate-200 hover:border-sky-500/40 hover:text-white'
                      }`}
                    >
                      {array.bitmap ? 'Bitmap deaktivieren' : 'Bitmap aktivieren'}
                    </button>
                    <button
                      onClick={() => handleTriggerScrub(array)}
                      disabled={busy}
                      className={`rounded-xl border px-4 py-2 text-sm transition ${
                        busy
                          ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                          : 'border-indigo-500/40 bg-indigo-500/15 text-indigo-100 hover:border-indigo-500/60'
                      }`}
                    >
                      Integritätsprüfung starten
                    </button>
                    <button
                      onClick={() => handleSimulateFailure(array)}
                      disabled={busy}
                      className={`rounded-xl border px-4 py-2 text-sm transition ${
                        busy
                          ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                          : 'border-amber-500/40 bg-amber-500/15 text-amber-100 hover:border-amber-500/60'
                      }`}
                    >
                      Array degradieren
                    </button>
                    {showFinalize && (
                      <button
                        onClick={() => handleFinalize(array)}
                        disabled={busy}
                        className={`rounded-xl border px-4 py-2 text-sm transition ${
                          busy
                            ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                            : 'border-emerald-500/40 bg-emerald-500/15 text-emerald-100 hover:border-emerald-500/60'
                        }`}
                      >
                        Rebuild abschließen
                      </button>
                    )}
                  </div>
                </div>

                {array.resync_progress !== null && array.resync_progress !== undefined && (
                  <div className="border-b border-slate-800/60 px-6 py-4">
                    <div className="h-2 w-full overflow-hidden rounded-full bg-slate-800">
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-sky-500 to-indigo-500"
                        style={{ width: `${Math.min(Math.max(array.resync_progress, 0), 100)}%` }}
                      />
                    </div>
                    <p className="mt-2 text-xs text-slate-500">
                      Aktueller Fortschritt der Wiederherstellung.
                    </p>
                  </div>
                )}

                <div className="px-6 py-5">
                  <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-slate-800/60">
                      <thead>
                        <tr className="text-left text-xs uppercase tracking-[0.24em] text-slate-500">
                          <th className="px-5 py-3">Gerät</th>
                          <th className="px-5 py-3">Status</th>
                          <th className="px-5 py-3">Aktionen</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/60">
                        {array.devices.map((device) => {
                          const lowerState = device.state.toLowerCase();
                          const allowFailure = canSimulateFailure(device);
                          const allowRebuild = canStartRebuild(device);

                          return (
                            <tr key={`${array.name}-${device.name}`} className="group transition hover:bg-slate-900/65">
                              <td className="px-5 py-4 text-sm font-medium text-slate-200">
                                /dev/{device.name}
                              </td>
                              <td className="px-5 py-4">
                                <span className={`rounded-full border px-3 py-1 text-xs font-medium ${getDeviceStyle(lowerState)}`}>
                                  {upcase(lowerState)}
                                </span>
                              </td>
                              <td className="px-5 py-4 text-sm">
                                <div className="flex flex-wrap items-center gap-3">
                                  <button
                                    onClick={() => handleSimulateFailure(array, device)}
                                    disabled={busy || !allowFailure}
                                    className={`rounded-lg border px-3 py-1.5 text-xs transition ${
                                      busy || !allowFailure
                                        ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                                        : 'border-amber-500/40 bg-amber-500/10 text-amber-100 hover:border-amber-500/60'
                                    }`}
                                  >
                                    Gerät degradieren
                                  </button>
                                  <button
                                    onClick={() => handleStartRebuild(array, device)}
                                    disabled={busy || !allowRebuild}
                                    className={`rounded-lg border px-3 py-1.5 text-xs transition ${
                                      busy || !allowRebuild
                                        ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                                        : 'border-sky-500/50 bg-sky-500/10 text-sky-100 hover:border-sky-500/60'
                                    }`}
                                  >
                                    Rebuild starten
                                  </button>
                                  <button
                                    onClick={() => handleWriteMostly(array, device)}
                                    disabled={busy || !['active', 'write-mostly'].includes(lowerState)}
                                    className={`rounded-lg border px-3 py-1.5 text-xs transition ${
                                      busy || !['active', 'write-mostly'].includes(lowerState)
                                        ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                                        : 'border-slate-700/70 bg-slate-900/60 text-slate-200 hover:border-slate-600'
                                    }`}
                                  >
                                    {lowerState === 'write-mostly' ? 'Write-mostly entfernen' : 'Write-mostly setzen'}
                                  </button>
                                  {lowerState === 'spare' && (
                                    <button
                                      onClick={() => handleRemoveDevice(array, device)}
                                      disabled={busy}
                                      className={`rounded-lg border px-3 py-1.5 text-xs transition ${
                                        busy
                                          ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                                          : 'border-rose-500/40 bg-rose-500/10 text-rose-200 hover:border-rose-500/60'
                                      }`}
                                    >
                                      Spare entfernen
                                    </button>
                                  )}
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>

                <div className="border-t border-slate-800/60 px-6 py-5">
                  <div className="grid gap-5 md:grid-cols-2">
                    <form onSubmit={(event) => handleAddSpare(event, array)} className="rounded-xl border border-slate-800 bg-slate-900/60 px-4 py-4 text-sm text-slate-300">
                      <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Spare hinzufügen</p>
                      <div className="mt-3 flex items-center gap-3">
                        <input
                          name="spare-device"
                          placeholder="z.B. sdc1"
                          className="flex-1 rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
                        />
                        <button
                          type="submit"
                          disabled={busy}
                          className={`rounded-lg border px-3 py-2 text-xs font-medium transition ${
                            busy
                              ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                              : 'border-emerald-500/40 bg-emerald-500/15 text-emerald-100 hover:border-emerald-500/60'
                          }`}
                        >
                          Hinzufügen
                        </button>
                      </div>
                    </form>

                    <form onSubmit={(event) => handleUpdateSpeed(event, array)} className="rounded-xl border border-slate-800 bg-slate-900/60 px-4 py-4 text-sm text-slate-300">
                      <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Sync Limits setzen (kB/s)</p>
                      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
                        <input
                          name="speed-min"
                          type="number"
                          min={0}
                          placeholder={speedLimits?.minimum?.toString() ?? 'min'}
                          className="rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
                        />
                        <input
                          name="speed-max"
                          type="number"
                          min={0}
                          placeholder={speedLimits?.maximum?.toString() ?? 'max'}
                          className="rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
                        />
                      </div>
                      <button
                        type="submit"
                        disabled={busy}
                        className={`mt-3 rounded-lg border px-3 py-2 text-xs font-medium transition ${
                          busy
                            ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                            : 'border-slate-700/70 bg-slate-900/60 text-slate-200 hover:border-sky-500/40 hover:text-white'
                        }`}
                      >
                        Anwenden
                      </button>
                    </form>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
