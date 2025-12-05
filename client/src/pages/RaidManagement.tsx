import { type FormEvent, useEffect, useMemo, useState } from 'react';
import toast from 'react-hot-toast';
import {
  deleteArray,
  finalizeRaidRebuild,
  formatDisk,
  getAvailableDisks,
  getRaidStatus,
  markDeviceFailed,
  startRaidRebuild,
  type AvailableDisk,
  type FormatDiskPayload,
  type RaidArray,
  type RaidDevice,
  type RaidOptionsPayload,
  type RaidSpeedLimits,
  updateRaidOptions,
} from '../api/raid';
import RaidSetupWizard from '../components/RaidSetupWizard';
import MockDiskWizard from '../components/MockDiskWizard';

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
  
  // Disk Management States
  const [availableDisks, setAvailableDisks] = useState<AvailableDisk[]>([]);
  const [showFormatDialog, setShowFormatDialog] = useState<boolean>(false);
  const [showCreateArrayDialog, setShowCreateArrayDialog] = useState<boolean>(false);
  const [showMockDiskWizard, setShowMockDiskWizard] = useState<boolean>(false);
  const [selectedDisk, setSelectedDisk] = useState<AvailableDisk | null>(null);
  const [isDevMode, setIsDevMode] = useState<boolean>(false);

  const loadStatus = async (notifySuccess = false) => {
    try {
      const status = await getRaidStatus();
      setArrays(status.arrays ?? []);
      setSpeedLimits(status.speed_limits ?? null);
      setError(null);
      setLastUpdated(new Date());
      if (notifySuccess) {
        toast.success('RAID status updated');
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load RAID status.';
      setError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  const loadAvailableDisks = async () => {
    try {
      const response = await getAvailableDisks();
      setAvailableDisks(response.disks ?? []);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load disks.';
      toast.error(message);
    }
  };

  useEffect(() => {
    void loadStatus();
    void loadAvailableDisks();
    
    // Check if Dev-Mode is active
    fetch('/api/system/info')
      .then(res => res.json())
      .then(data => setIsDevMode(data.dev_mode === true))
      .catch(() => setIsDevMode(false));
    
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
      const message = err instanceof Error ? err.message : 'Simulation failed.';
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
      const message = err instanceof Error ? err.message : 'Failed to start rebuild.';
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
      const message = err instanceof Error ? err.message : 'Finalize failed.';
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
      const message = err instanceof Error ? err.message : 'Failed to update bitmap.';
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
      const message = err instanceof Error ? err.message : 'Failed to start scrub.';
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
      const message = err instanceof Error ? err.message : 'Failed to update write-mostly.';
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
      const message = err instanceof Error ? err.message : 'Failed to remove device.';
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
      toast.error('Please specify device name.');
      return;
    }

    setBusy(true);
    try {
      const response = await updateRaidOptions({ array: array.name, add_spare: rawDevice });
      toast.success(response.message);
      await loadStatus();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to add spare device.';
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
      toast.error('Please set at least one speed value.');
      return;
    }

    setBusy(true);
    try {
      const response = await updateRaidOptions(payload);
      toast.success(response.message);
      await loadStatus();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to set speed limit.';
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  const handleFormatDisk = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedDisk) return;

    const data = new FormData(event.currentTarget);
    const filesystem = data.get('filesystem') as string;
    const label = data.get('label') as string;

    const payload: FormatDiskPayload = {
      disk: selectedDisk.name,
      filesystem: filesystem || 'ext4',
    };
    if (label && label.trim()) {
      payload.label = label.trim();
    }

    setBusy(true);
    try {
      const response = await formatDisk(payload);
      toast.success(response.message);
      setShowFormatDialog(false);
      setSelectedDisk(null);
      await loadAvailableDisks();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Format failed.';
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  const handleDeleteArray = async (arrayName: string) => {
    if (!window.confirm(`Really delete array "${arrayName}"? This action cannot be undone.`)) {
      return;
    }

    setBusy(true);
    try {
      const response = await deleteArray({ array: arrayName, force: true });
      toast.success(response.message);
      await loadStatus();
      await loadAvailableDisks();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Array deletion failed.';
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
            Monitor array integrity, simulate failures, and control rebuilds.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {lastUpdated && (
            <span className="text-xs uppercase tracking-[0.24em] text-slate-500">
              Updated {lastUpdated.toLocaleTimeString()}
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
            Refresh Now
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
          <p className="text-sm text-slate-500">Loading RAID status...</p>
        </div>
      ) : arrays.length === 0 ? (
        <div className="card border-slate-800/60 bg-slate-900/55 py-12 text-center text-sm text-slate-400">
          No RAID arrays detected. Ensure the system uses mdadm and arrays are active.
        </div>
      ) : (
        <div className="space-y-6">
          {speedLimits && (
            <div className="card border-slate-800/60 bg-slate-900/55 px-6 py-5">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <p className="text-xs uppercase tracking-[0.3em] text-slate-500">Sync Limits</p>
                  <p className="mt-2 text-sm text-slate-300">
                    Minimum Speed: {speedLimits.minimum ?? 'System Default'} kB/s · Maximum: {speedLimits.maximum ?? 'System Default'} kB/s
                  </p>
                </div>
                <p className="text-xs text-slate-500">
                  Values apply globally to all mdadm arrays.
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
                      <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-sky-500 to-indigo-600 shadow-lg shadow-sky-500/30">
                        <svg className="h-5 w-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M5.25 14.25h13.5m-13.5 0a3 3 0 01-3-3m3 3a3 3 0 100 6h13.5a3 3 0 100-6m-16.5-3a3 3 0 013-3h13.5a3 3 0 013 3m-19.5 0a4.5 4.5 0 01.9-2.7L5.737 5.1a3.375 3.375 0 012.7-1.35h7.126c1.062 0 2.062.5 2.7 1.35l2.587 3.45a4.5 4.5 0 01.9 2.7m0 0a3 3 0 01-3 3m0 3h.008v.008h-.008v-.008zm0-6h.008v.008h-.008v-.008zm-3 6h.008v.008h-.008v-.008zm0-6h.008v.008h-.008v-.008z" />
                        </svg>
                      </div>
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
                      Capacity {formatBytes(array.size_bytes)} · {array.devices.length} Drives
                    </p>
                    <div className="flex flex-wrap gap-2 text-xs text-slate-500">
                      <span>Write-mostly Devices: {array.devices.filter((device) => device.state === 'write-mostly').length}</span>
                      <span>Spare Devices: {array.devices.filter((device) => device.state === 'spare').length}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    {array.resync_progress !== null && array.resync_progress !== undefined && (
                      <div className="flex flex-col items-end text-sm text-slate-300">
                        <span>Synchronization</span>
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
                      {array.bitmap ? 'Disable Bitmap' : 'Enable Bitmap'}
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
                      Start Integrity Check
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
                      Degrade Array
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
                        Complete Rebuild
                      </button>
                    )}
                    <button
                      onClick={() => handleDeleteArray(array.name)}
                      disabled={busy}
                      className={`rounded-xl border px-4 py-2 text-sm transition ${
                        busy
                          ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                          : 'border-rose-500/40 bg-rose-500/15 text-rose-200 hover:border-rose-500/60'
                      }`}
                    >
                      Delete Array
                    </button>
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
                      Current rebuild progress.
                    </p>
                  </div>
                )}

                <div className="px-6 py-5">
                  <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-slate-800/60">
                      <thead>
                        <tr className="text-left text-xs uppercase tracking-[0.24em] text-slate-500">
                          <th className="px-5 py-3">Device</th>
                          <th className="px-5 py-3">Status</th>
                          <th className="px-5 py-3">Actions</th>
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
                                    Degrade Device
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
                                    Start Rebuild
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
                                    {lowerState === 'write-mostly' ? 'Remove Write-mostly' : 'Set Write-mostly'}
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
                                      Remove Spare
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
                      <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Add Spare</p>
                      <div className="mt-3 flex items-center gap-3">
                        <input
                          name="spare-device"
                          placeholder="e.g. sdc1"
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
                          Add
                        </button>
                      </div>
                    </form>

                    <form onSubmit={(event) => handleUpdateSpeed(event, array)} className="rounded-xl border border-slate-800 bg-slate-900/60 px-4 py-4 text-sm text-slate-300">
                      <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Set Sync Limits (kB/s)</p>
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
                        Apply
                      </button>
                    </form>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Disk Management Section */}
      <div className="card border-slate-800/60 bg-slate-900/55">
        <div className="border-b border-slate-800/60 px-6 py-5">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-xl font-semibold text-white">Disk Management</h2>
              <p className="mt-1 text-sm text-slate-400">Format available disks and create new arrays</p>
            </div>
            <div className="flex gap-3">
              <button
                onClick={() => void loadAvailableDisks()}
                disabled={busy}
                className={`rounded-xl border px-4 py-2 text-sm transition ${
                  busy
                    ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                    : 'border-sky-500/30 bg-sky-500/10 text-sky-200 hover:border-sky-500/50 hover:bg-sky-500/15'
                }`}
              >
                Refresh
              </button>
              {isDevMode && (
                <button
                  onClick={() => setShowMockDiskWizard(true)}
                  disabled={busy}
                  className={`rounded-xl border px-4 py-2 text-sm transition ${
                    busy
                      ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                      : 'border-violet-500/40 bg-violet-500/15 text-violet-100 hover:border-violet-500/60'
                  }`}
                  title="Dev-Mode: Add Mock Disk"
                >
                  🧪 Add Mock Disk
                </button>
              )}
              <button
                onClick={() => setShowCreateArrayDialog(true)}
                disabled={busy || availableDisks.filter(d => !d.in_raid).length < 2}
                className={`rounded-xl border px-4 py-2 text-sm transition ${
                  busy || availableDisks.filter(d => !d.in_raid).length < 2
                    ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                    : 'border-emerald-500/40 bg-emerald-500/15 text-emerald-100 hover:border-emerald-500/60'
                }`}
                title={availableDisks.filter(d => !d.in_raid).length < 2 ? 'At least 2 free disks required' : ''}
              >
                Create New Array
              </button>
            </div>
          </div>
        </div>

        <div className="px-6 py-5">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-800/60">
              <thead>
                <tr className="text-left text-xs uppercase tracking-[0.24em] text-slate-500">
                  <th className="px-5 py-3">Name</th>
                  <th className="px-5 py-3">Size</th>
                  <th className="px-5 py-3">Model</th>
                  <th className="px-5 py-3">Status</th>
                  <th className="px-5 py-3">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {availableDisks.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-5 py-8 text-center text-sm text-slate-400">
                      No disks available
                    </td>
                  </tr>
                ) : (
                  availableDisks.map((disk) => (
                    <tr key={disk.name} className="group transition hover:bg-slate-900/65">
                      <td className="px-5 py-4 text-sm font-medium text-slate-200">/dev/{disk.name}</td>
                      <td className="px-5 py-4 text-sm text-slate-300">{formatBytes(disk.size_bytes)}</td>
                      <td className="px-5 py-4 text-sm text-slate-300">{disk.model || 'N/A'}</td>
                      <td className="px-5 py-4">
                        <div className="flex flex-wrap items-center gap-2">
                          {disk.in_raid ? (
                            (() => {
                              // Finde das Array, in dem diese Disk ist
                              const diskArray = arrays.find(arr => 
                                arr.devices.some(dev => dev.name === `${disk.name}1` || dev.name === disk.name)
                              );
                              return diskArray ? (
                                <div className="flex items-center gap-2 rounded-full border border-sky-400/30 bg-sky-500/10 px-3 py-1">
                                  <svg className="h-3.5 w-3.5 text-sky-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M5.25 14.25h13.5m-13.5 0a3 3 0 01-3-3m3 3a3 3 0 100 6h13.5a3 3 0 100-6m-16.5-3a3 3 0 013-3h13.5a3 3 0 013 3m-19.5 0a4.5 4.5 0 01.9-2.7L5.737 5.1a3.375 3.375 0 012.7-1.35h7.126c1.062 0 2.062.5 2.7 1.35l2.587 3.45a4.5 4.5 0 01.9 2.7m0 0a3 3 0 01-3 3m0 3h.008v.008h-.008v-.008zm0-6h.008v.008h-.008v-.008zm-3 6h.008v.008h-.008v-.008zm0-6h.008v.008h-.008v-.008z" />
                                  </svg>
                                  <span className="text-xs font-medium text-sky-100">{diskArray.name}</span>
                                  <span className="text-[0.65rem] uppercase tracking-wider text-sky-300/70">{diskArray.level}</span>
                                </div>
                              ) : (
                                <span className="rounded-full border border-sky-400/30 bg-sky-500/10 px-2 py-0.5 text-xs text-sky-100">
                                  In RAID
                                </span>
                              );
                            })()
                          ) : (
                            <span className="rounded-full border border-slate-700/50 bg-slate-800/40 px-2 py-0.5 text-xs text-slate-400">
                              Free
                            </span>
                          )}
                          {disk.is_partitioned && (
                            <span className="rounded-full border border-amber-400/30 bg-amber-500/10 px-2 py-0.5 text-xs text-amber-100">
                              Partitioned
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-5 py-4">
                        <button
                          onClick={() => {
                            setSelectedDisk(disk);
                            setShowFormatDialog(true);
                          }}
                          disabled={busy || disk.in_raid}
                          className={`rounded-lg border px-3 py-1.5 text-xs transition ${
                            busy || disk.in_raid
                              ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                              : 'border-rose-500/40 bg-rose-500/10 text-rose-200 hover:border-rose-500/60'
                          }`}
                        >
                          Format
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Format Dialog */}
      {showFormatDialog && selectedDisk && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 backdrop-blur-xl" onClick={() => setShowFormatDialog(false)}>
          <div className="card w-full max-w-md border-rose-500/40 bg-slate-900/80 backdrop-blur-2xl shadow-[0_20px_70px_rgba(220,38,38,0.3)]" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-xl font-semibold text-white">Format Disk</h3>
            <p className="mt-2 text-sm text-slate-400">
              Format disk <span className="font-medium text-slate-200">/dev/{selectedDisk.name}</span>
            </p>
            <form onSubmit={handleFormatDisk} className="mt-4 space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-300">Filesystem</label>
                <select
                  name="filesystem"
                  defaultValue="ext4"
                  className="mt-1 w-full rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
                >
                  <option value="ext4">ext4</option>
                  <option value="ext3">ext3</option>
                  <option value="xfs">xfs</option>
                  <option value="btrfs">btrfs</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-300">Label (optional)</label>
                <input
                  name="label"
                  type="text"
                  placeholder="e.g. MyDisk"
                  className="mt-1 w-full rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
                />
              </div>
              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => {
                    setShowFormatDialog(false);
                    setSelectedDisk(null);
                  }}
                  className="rounded-lg border border-slate-700/70 bg-slate-900/60 px-4 py-2 text-sm text-slate-200 transition hover:border-slate-600"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={busy}
                  className={`rounded-lg border px-4 py-2 text-sm transition ${
                    busy
                      ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                      : 'border-rose-500/40 bg-rose-500/15 text-rose-200 hover:border-rose-500/60'
                  }`}
                >
                  Format
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* RAID Setup Wizard */}
      {showCreateArrayDialog && (
        <RaidSetupWizard
          availableDisks={availableDisks}
          onClose={() => setShowCreateArrayDialog(false)}
          onSuccess={async () => {
            await loadStatus();
            await loadAvailableDisks();
          }}
        />
      )}

      {/* Mock Disk Wizard (Dev-Mode only) */}
      {showMockDiskWizard && isDevMode && (
        <MockDiskWizard
          onClose={() => setShowMockDiskWizard(false)}
          onSuccess={async () => {
            await loadStatus();
            await loadAvailableDisks();
            setShowMockDiskWizard(false);
          }}
        />
      )}
    </div>
  );
}
