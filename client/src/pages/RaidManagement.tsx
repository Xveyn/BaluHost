import { type FormEvent, useEffect, useMemo, useState } from 'react';
import toast from 'react-hot-toast';
import { useTranslation } from 'react-i18next';
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
import SsdCachePanel from '../components/SsdCachePanel';
import CacheSetupWizard from '../components/CacheSetupWizard';
import { formatBytes, formatNumber } from '../lib/formatters';
import { useConfirmDialog } from '../hooks/useConfirmDialog';
import { Monitor, Zap } from 'lucide-react';

const REFRESH_INTERVAL_MS = 8000;

const statusStyles: Record<string, string> = {
  optimal: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200',
  checking: 'border-indigo-500/40 bg-indigo-500/15 text-indigo-100',
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
  const { t } = useTranslation(['system', 'common']);
  const { confirm, dialog } = useConfirmDialog();
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
  const [cacheWizardArray, setCacheWizardArray] = useState<string | null>(null);

  const loadStatus = async (notifySuccess = false) => {
    try {
      const status = await getRaidStatus();
      setArrays(status.arrays ?? []);
      setSpeedLimits(status.speed_limits ?? null);
      setError(null);
      setLastUpdated(new Date());
      if (notifySuccess) {
        toast.success(t('system:raid.messages.statusUpdated'));
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : t('system:raid.messages.loadError');
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
      const message = err instanceof Error ? err.message : t('system:raid.messages.loadDisksError');
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
      const message = err instanceof Error ? err.message : t('system:raid.messages.simulationFailed');
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
      const message = err instanceof Error ? err.message : t('system:raid.messages.rebuildFailed');
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
      const message = err instanceof Error ? err.message : t('system:raid.messages.finalizeFailed');
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
      const message = err instanceof Error ? err.message : t('system:raid.messages.bitmapUpdateFailed');
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
      const message = err instanceof Error ? err.message : t('system:raid.messages.scrubFailed');
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
      const message = err instanceof Error ? err.message : t('system:raid.messages.writeMostlyFailed');
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
      const message = err instanceof Error ? err.message : t('system:raid.messages.removeDeviceFailed');
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
      toast.error(t('system:raid.messages.specifyDeviceName'));
      return;
    }

    setBusy(true);
    try {
      const response = await updateRaidOptions({ array: array.name, add_spare: rawDevice });
      toast.success(response.message);
      await loadStatus();
    } catch (err) {
      const message = err instanceof Error ? err.message : t('system:raid.messages.addSpareFailed');
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
      toast.error(t('system:raid.messages.setSpeedValue'));
      return;
    }

    setBusy(true);
    try {
      const response = await updateRaidOptions(payload);
      toast.success(response.message);
      await loadStatus();
    } catch (err) {
      const message = err instanceof Error ? err.message : t('system:raid.messages.speedLimitFailed');
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
      const message = err instanceof Error ? err.message : t('system:raid.messages.formatFailed');
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  const handleDeleteArray = async (arrayName: string) => {
    const ok = await confirm(t('system:raid.messages.deleteConfirm', { name: arrayName }), { title: t('system:raid.deleteArray'), variant: 'danger', confirmLabel: t('system:raid.deleteArray') });
    if (!ok) return;

    setBusy(true);
    try {
      const response = await deleteArray({ array: arrayName, force: true });
      toast.success(response.message);
      await loadStatus();
      await loadAvailableDisks();
    } catch (err) {
      const message = err instanceof Error ? err.message : t('system:raid.messages.deleteFailed');
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4 sm:space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-semibold text-white">{t('system:raid.title')}</h1>
          <p className="mt-1 text-xs sm:text-sm text-slate-400">
            {t('system:raid.subtitle')}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {lastUpdated && (
            <span className="text-[10px] sm:text-xs uppercase tracking-[0.24em] text-slate-500">
              {t('system:raid.labels.updated')} {lastUpdated.toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={() => loadStatus(true)}
            disabled={refreshDisabled}
            className={`rounded-xl border px-3 sm:px-4 py-2 text-xs sm:text-sm font-medium transition touch-manipulation active:scale-95 ${
              refreshDisabled
                ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                : 'border-sky-500/30 bg-sky-500/10 text-sky-200 hover:border-sky-500/50 hover:bg-sky-500/15'
            }`}
          >
            {t('system:raid.actions.refresh')}
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
          <p className="text-sm text-slate-500">{t('system:raid.labels.loading')}</p>
        </div>
      ) : arrays.length === 0 ? (
        <div className="card border-slate-800/60 bg-slate-900/55 py-12 text-center text-sm text-slate-400">
          {t('system:raid.labels.noArrays')}
        </div>
      ) : (
        <div className="space-y-6">
          {speedLimits && (
            <div className="card border-slate-800/60 bg-slate-900/55 px-4 sm:px-6 py-4 sm:py-5">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 sm:gap-4">
                <div className="flex-1 min-w-0">
                  <p className="text-[10px] sm:text-xs uppercase tracking-[0.3em] text-slate-500">{t('system:raid.labels.syncLimits')}</p>
                  <p className="mt-2 text-xs sm:text-sm text-slate-300">
                    Min: {speedLimits.minimum ?? t('system:raid.labels.systemDefault')} kB/s · Max: {speedLimits.maximum ?? t('system:raid.labels.systemDefault')} kB/s
                  </p>
                </div>
                <p className="text-[10px] sm:text-xs text-slate-500">
                  {t('system:raid.labels.appliesGlobally')}
                </p>
              </div>
            </div>
          )}

          {arrays.map((array) => {
            const lowerStatus = array.status.toLowerCase();
            const showFinalize = shouldShowFinalize(array);

            return (
              <div key={array.name} className="card border-slate-800/60 bg-slate-900/55">
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4 border-b border-slate-800/60 px-4 sm:px-6 py-4 sm:py-5">
                  <div className="space-y-1 flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <div className="flex h-8 w-8 sm:h-10 sm:w-10 items-center justify-center rounded-xl bg-gradient-to-br from-sky-500 to-indigo-600 shadow-lg shadow-sky-500/30 flex-shrink-0">
                        <svg className="h-4 w-4 sm:h-5 sm:w-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M5.25 14.25h13.5m-13.5 0a3 3 0 01-3-3m3 3a3 3 0 100 6h13.5a3 3 0 100-6m-16.5-3a3 3 0 013-3h13.5a3 3 0 013 3m-19.5 0a4.5 4.5 0 01.9-2.7L5.737 5.1a3.375 3.375 0 012.7-1.35h7.126c1.062 0 2.062.5 2.7 1.35l2.587 3.45a4.5 4.5 0 01.9 2.7m0 0a3 3 0 01-3 3m0 3h.008v.008h-.008v-.008zm0-6h.008v.008h-.008v-.008zm-3 6h.008v.008h-.008v-.008zm0-6h.008v.008h-.008v-.008z" />
                        </svg>
                      </div>
                      <h2 className="text-base sm:text-xl font-semibold text-white truncate">{array.name}</h2>
                      <span className={`rounded-full border px-2 sm:px-3 py-0.5 sm:py-1 text-[10px] sm:text-xs font-medium ${getStatusStyle(lowerStatus)}`}>
                        {upcase(lowerStatus)}
                      </span>
                      <span className="rounded-full border border-slate-700/70 bg-slate-900/60 px-2 sm:px-3 py-0.5 sm:py-1 text-[10px] sm:text-xs uppercase tracking-[0.26em] text-slate-400">
                        {array.level.replace(/^raid/i, 'RAID ')}
                      </span>
                      <span className="hidden sm:inline rounded-full border border-slate-800/70 bg-slate-900/60 px-3 py-1 text-xs text-slate-400">
                        {t('system:raid.labels.bitmap')}: {array.bitmap ? array.bitmap : t('system:raid.labels.bitmapOff')}
                      </span>
                      {array.sync_action && (
                        <span className="hidden sm:inline rounded-full border border-slate-800/70 bg-slate-900/60 px-3 py-1 text-xs text-slate-400">
                          {t('system:raid.labels.sync')}: {array.sync_action}
                        </span>
                      )}
                    </div>
                    <p className="text-xs sm:text-sm text-slate-400">
                      {formatBytes(array.size_bytes)} · {array.devices.length} {t('system:raid.labels.drives')} · {array.devices.filter(d => ['active', 'write-mostly', 'rebuilding'].includes(d.state.toLowerCase())).length} {t('system:raid.labels.active')}
                    </p>
                    <div className="flex flex-wrap gap-2 text-[10px] sm:text-xs text-slate-500">
                      <span>{t('system:raid.labels.writeMostly')}: {array.devices.filter((device) => device.state === 'write-mostly').length}</span>
                      <span>{t('system:raid.labels.spares')}: {array.devices.filter((device) => device.state === 'spare').length}</span>
                    </div>
                  </div>
                  <div className="w-full sm:w-auto space-y-2">
                    {array.resync_progress !== null && array.resync_progress !== undefined && (
                      <div className="flex flex-row sm:flex-col items-center sm:items-end text-xs sm:text-sm text-slate-300">
                        <span className="mr-2 sm:mr-0">{t('system:raid.labels.sync')}:</span>
                        <span className="text-slate-200 font-medium">{formatNumber(array.resync_progress, 1)}%</span>
                      </div>
                    )}
                    <div className="flex gap-2 overflow-x-auto pb-2 sm:pb-0">
                      <button
                        onClick={() => handleToggleBitmap(array)}
                        disabled={busy}
                        className={`whitespace-nowrap rounded-xl border px-3 sm:px-4 py-1.5 sm:py-2 text-xs sm:text-sm transition touch-manipulation active:scale-95 ${
                          busy
                            ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                            : 'border-slate-700/70 bg-slate-900/60 text-slate-200 hover:border-sky-500/40 hover:text-white'
                        }`}
                      >
                        {array.bitmap ? t('system:raid.actions.disableBitmap') : t('system:raid.actions.enableBitmap')}
                      </button>
                      <button
                        onClick={() => handleTriggerScrub(array)}
                        disabled={busy}
                        className={`whitespace-nowrap rounded-xl border px-3 sm:px-4 py-1.5 sm:py-2 text-xs sm:text-sm transition touch-manipulation active:scale-95 ${
                          busy
                            ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                            : 'border-indigo-500/40 bg-indigo-500/15 text-indigo-100 hover:border-indigo-500/60'
                        }`}
                      >
                        <span className="hidden sm:inline">{t('system:raid.actions.integrityCheck')}</span>
                        <span className="sm:hidden">{t('system:raid.actions.check')}</span>
                      </button>
                      <button
                        onClick={() => handleSimulateFailure(array)}
                        disabled={busy}
                        className={`whitespace-nowrap rounded-xl border px-3 sm:px-4 py-1.5 sm:py-2 text-xs sm:text-sm transition touch-manipulation active:scale-95 ${
                          busy
                            ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                            : 'border-amber-500/40 bg-amber-500/15 text-amber-100 hover:border-amber-500/60'
                        }`}
                      >
                        <span className="hidden sm:inline">{t('system:raid.actions.degradeArray')}</span>
                        <span className="sm:hidden">Degrade</span>
                      </button>
                      {showFinalize && (
                        <button
                          onClick={() => handleFinalize(array)}
                          disabled={busy}
                          className={`whitespace-nowrap rounded-xl border px-3 sm:px-4 py-1.5 sm:py-2 text-xs sm:text-sm transition touch-manipulation active:scale-95 ${
                            busy
                              ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                              : 'border-emerald-500/40 bg-emerald-500/15 text-emerald-100 hover:border-emerald-500/60'
                          }`}
                        >
                          <span className="hidden sm:inline">{t('system:raid.actions.completeRebuild')}</span>
                          <span className="sm:hidden">Rebuild</span>
                        </button>
                      )}
                      <button
                        onClick={() => handleDeleteArray(array.name)}
                        disabled={busy}
                        className={`whitespace-nowrap rounded-xl border px-3 sm:px-4 py-1.5 sm:py-2 text-xs sm:text-sm transition touch-manipulation active:scale-95 ${
                          busy
                            ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                            : 'border-rose-500/40 bg-rose-500/15 text-rose-200 hover:border-rose-500/60'
                        }`}
                      >
                        <span className="hidden sm:inline">{t('system:raid.deleteArray')}</span>
                        <span className="sm:hidden">Delete</span>
                      </button>
                    </div>
                  </div>
                </div>

                {array.resync_progress !== null && array.resync_progress !== undefined && (
                  <div className="border-b border-slate-800/60 px-4 sm:px-6 py-4">
                    <div className="h-2 w-full overflow-hidden rounded-full bg-slate-800">
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-sky-500 to-indigo-500"
                        style={{ width: `${Math.min(Math.max(array.resync_progress, 0), 100)}%` }}
                      />
                    </div>
                    <p className="mt-2 text-xs text-slate-500">
                      {array.status.toLowerCase() === 'checking'
                        ? t('system:raid.labels.checkProgress')
                        : t('system:raid.labels.rebuildProgress')}
                    </p>
                  </div>
                )}

                <div className="px-4 sm:px-6 py-4 sm:py-5">
                  {/* Desktop device table */}
                  <div className="hidden lg:block overflow-x-auto">
                    <table className="min-w-full divide-y divide-slate-800/60">
                      <thead>
                        <tr className="text-left text-xs uppercase tracking-[0.24em] text-slate-500">
                          <th className="px-5 py-3">{t('system:raid.tableHeaders.device')}</th>
                          <th className="px-5 py-3">{t('system:raid.tableHeaders.status')}</th>
                          <th className="px-5 py-3">{t('system:raid.tableHeaders.actions')}</th>
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
                                <div className="flex gap-2">
                                  <button
                                    onClick={() => handleSimulateFailure(array, device)}
                                    disabled={busy || !allowFailure}
                                    className={`whitespace-nowrap rounded-lg border px-3 py-1.5 text-xs transition touch-manipulation active:scale-95 ${
                                      busy || !allowFailure
                                        ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                                        : 'border-amber-500/40 bg-amber-500/10 text-amber-100 hover:border-amber-500/60'
                                    }`}
                                  >
                                    {t('system:raid.actions.degradeDevice')}
                                  </button>
                                  <button
                                    onClick={() => handleStartRebuild(array, device)}
                                    disabled={busy || !allowRebuild}
                                    className={`whitespace-nowrap rounded-lg border px-3 py-1.5 text-xs transition touch-manipulation active:scale-95 ${
                                      busy || !allowRebuild
                                        ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                                        : 'border-sky-500/50 bg-sky-500/10 text-sky-100 hover:border-sky-500/60'
                                    }`}
                                  >
                                    {t('system:raid.actions.startRebuild')}
                                  </button>
                                  <button
                                    onClick={() => handleWriteMostly(array, device)}
                                    disabled={busy || !['active', 'write-mostly'].includes(lowerState)}
                                    className={`whitespace-nowrap rounded-lg border px-3 py-1.5 text-xs transition touch-manipulation active:scale-95 ${
                                      busy || !['active', 'write-mostly'].includes(lowerState)
                                        ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                                        : 'border-slate-700/70 bg-slate-900/60 text-slate-200 hover:border-slate-600'
                                    }`}
                                  >
                                    {lowerState === 'write-mostly' ? t('system:raid.actions.removeWriteMostly') : t('system:raid.actions.writeMostly')}
                                  </button>
                                  {lowerState === 'spare' && (
                                    <button
                                      onClick={() => handleRemoveDevice(array, device)}
                                      disabled={busy}
                                      className={`whitespace-nowrap rounded-lg border px-3 py-1.5 text-xs transition touch-manipulation active:scale-95 ${
                                        busy
                                          ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                                          : 'border-rose-500/40 bg-rose-500/10 text-rose-200 hover:border-rose-500/60'
                                      }`}
                                    >
                                      {t('system:raid.actions.removeSpare')}
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

                  {/* Mobile device cards */}
                  <div className="lg:hidden space-y-3">
                    {array.devices.map((device) => {
                      const lowerState = device.state.toLowerCase();
                      const allowFailure = canSimulateFailure(device);
                      const allowRebuild = canStartRebuild(device);

                      return (
                        <div key={`${array.name}-${device.name}-mobile`} className="rounded-xl border border-slate-800/60 bg-slate-900/60 p-3">
                          <div className="flex items-center justify-between">
                            <span className="text-sm font-medium text-slate-200">/dev/{device.name}</span>
                            <span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${getDeviceStyle(lowerState)}`}>
                              {upcase(lowerState)}
                            </span>
                          </div>
                          <div className="mt-2 flex flex-wrap gap-1.5">
                            <button
                              onClick={() => handleSimulateFailure(array, device)}
                              disabled={busy || !allowFailure}
                              className={`rounded-lg border px-2 py-1 text-[10px] transition touch-manipulation active:scale-95 ${
                                busy || !allowFailure
                                  ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                                  : 'border-amber-500/40 bg-amber-500/10 text-amber-100'
                              }`}
                            >
                              Degrade
                            </button>
                            <button
                              onClick={() => handleStartRebuild(array, device)}
                              disabled={busy || !allowRebuild}
                              className={`rounded-lg border px-2 py-1 text-[10px] transition touch-manipulation active:scale-95 ${
                                busy || !allowRebuild
                                  ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                                  : 'border-sky-500/50 bg-sky-500/10 text-sky-100'
                              }`}
                            >
                              Rebuild
                            </button>
                            <button
                              onClick={() => handleWriteMostly(array, device)}
                              disabled={busy || !['active', 'write-mostly'].includes(lowerState)}
                              className={`rounded-lg border px-2 py-1 text-[10px] transition touch-manipulation active:scale-95 ${
                                busy || !['active', 'write-mostly'].includes(lowerState)
                                  ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                                  : 'border-slate-700/70 bg-slate-900/60 text-slate-200'
                              }`}
                            >
                              {lowerState === 'write-mostly' ? 'RW' : 'WM'}
                            </button>
                            {lowerState === 'spare' && (
                              <button
                                onClick={() => handleRemoveDevice(array, device)}
                                disabled={busy}
                                className={`rounded-lg border px-2 py-1 text-[10px] transition touch-manipulation active:scale-95 ${
                                  busy
                                    ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                                    : 'border-rose-500/40 bg-rose-500/10 text-rose-200'
                                }`}
                              >
                                {t('system:raid.actions.remove')}
                              </button>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* SSD Cache Panel */}
                {array.cache ? (
                  <SsdCachePanel
                    cache={array.cache}
                    onRefresh={async () => {
                      await loadStatus();
                      await loadAvailableDisks();
                    }}
                  />
                ) : (
                  <div className="border-t border-slate-800/60 px-4 sm:px-6 py-3 sm:py-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2 text-xs text-slate-500">
                        <Zap className="h-3.5 w-3.5" />
                        <span>{t('system:raid.cache.noCache')}</span>
                      </div>
                      <button
                        onClick={() => setCacheWizardArray(array.name)}
                        disabled={busy || availableDisks.filter(d => d.is_ssd && !d.is_os_disk && !d.in_raid && !d.is_cache_device).length === 0}
                        className={`rounded-lg border px-3 py-1.5 text-xs transition touch-manipulation active:scale-95 ${
                          busy || availableDisks.filter(d => d.is_ssd && !d.is_os_disk && !d.in_raid && !d.is_cache_device).length === 0
                            ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                            : 'border-cyan-500/30 bg-cyan-500/10 text-cyan-200 hover:border-cyan-500/50'
                        }`}
                      >
                        {t('system:raid.cache.actions.setup')}
                      </button>
                    </div>
                  </div>
                )}

                <div className="border-t border-slate-800/60 px-4 sm:px-6 py-4 sm:py-5">
                  <div className="grid gap-3 sm:gap-5 md:grid-cols-2">
                    <form onSubmit={(event) => handleAddSpare(event, array)} className="rounded-xl border border-slate-800 bg-slate-900/60 px-3 sm:px-4 py-3 sm:py-4 text-xs sm:text-sm text-slate-300">
                      <p className="text-[10px] sm:text-xs uppercase tracking-[0.24em] text-slate-500">{t('system:raid.labels.addSpare')}</p>
                      <div className="mt-2 sm:mt-3 flex items-center gap-2 sm:gap-3">
                        <input
                          name="spare-device"
                          placeholder={t('system:raid.labels.sparePlaceholder')}
                          className="flex-1 rounded-lg border border-slate-800 bg-slate-950/70 px-2 sm:px-3 py-1.5 sm:py-2 text-xs sm:text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
                        />
                        <button
                          type="submit"
                          disabled={busy}
                          className={`rounded-lg border px-3 py-1.5 sm:py-2 text-[10px] sm:text-xs font-medium transition touch-manipulation active:scale-95 ${
                            busy
                              ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                              : 'border-emerald-500/40 bg-emerald-500/15 text-emerald-100 hover:border-emerald-500/60'
                          }`}
                        >
                          {t('system:raid.actions.add')}
                        </button>
                      </div>
                    </form>

                    <form onSubmit={(event) => handleUpdateSpeed(event, array)} className="rounded-xl border border-slate-800 bg-slate-900/60 px-3 sm:px-4 py-3 sm:py-4 text-xs sm:text-sm text-slate-300">
                      <p className="text-[10px] sm:text-xs uppercase tracking-[0.24em] text-slate-500">{t('system:raid.labels.syncLimitsKbs')}</p>
                      <div className="mt-2 sm:mt-3 grid grid-cols-2 gap-2 sm:gap-3">
                        <input
                          name="speed-min"
                          type="number"
                          min={0}
                          placeholder={speedLimits?.minimum?.toString() ?? t('system:raid.labels.min')}
                          className="rounded-lg border border-slate-800 bg-slate-950/70 px-2 sm:px-3 py-1.5 sm:py-2 text-xs sm:text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
                        />
                        <input
                          name="speed-max"
                          type="number"
                          min={0}
                          placeholder={speedLimits?.maximum?.toString() ?? t('system:raid.labels.max')}
                          className="rounded-lg border border-slate-800 bg-slate-950/70 px-2 sm:px-3 py-1.5 sm:py-2 text-xs sm:text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
                        />
                      </div>
                      <button
                        type="submit"
                        disabled={busy}
                        className={`mt-2 sm:mt-3 w-full sm:w-auto rounded-lg border px-3 py-1.5 sm:py-2 text-[10px] sm:text-xs font-medium transition touch-manipulation active:scale-95 ${
                          busy
                            ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                            : 'border-slate-700/70 bg-slate-900/60 text-slate-200 hover:border-sky-500/40 hover:text-white'
                        }`}
                      >
                        {t('system:raid.actions.apply')}
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
        <div className="border-b border-slate-800/60 px-4 sm:px-6 py-4 sm:py-5">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4">
            <div>
              <h2 className="text-lg sm:text-xl font-semibold text-white">{t('system:raid.diskManagement.title')}</h2>
              <p className="mt-1 text-xs sm:text-sm text-slate-400">{t('system:raid.diskManagement.subtitle')}</p>
            </div>
            <div className="flex gap-2 overflow-x-auto pb-2 sm:pb-0">
              <button
                onClick={() => void loadAvailableDisks()}
                disabled={busy}
                className={`whitespace-nowrap rounded-xl border px-3 sm:px-4 py-1.5 sm:py-2 text-xs sm:text-sm transition touch-manipulation active:scale-95 ${
                  busy
                    ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                    : 'border-sky-500/30 bg-sky-500/10 text-sky-200 hover:border-sky-500/50 hover:bg-sky-500/15'
                }`}
              >
                {t('system:raid.actions.refresh')}
              </button>
              {isDevMode && (
                <button
                  onClick={() => setShowMockDiskWizard(true)}
                  disabled={busy}
                  className={`whitespace-nowrap rounded-xl border px-3 sm:px-4 py-1.5 sm:py-2 text-xs sm:text-sm transition touch-manipulation active:scale-95 ${
                    busy
                      ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                      : 'border-violet-500/40 bg-violet-500/15 text-violet-100 hover:border-violet-500/60'
                  }`}
                  title={t('system:raid.diskManagement.devModeAddMock')}
                >
                  🧪 <span className="hidden sm:inline">{t('system:raid.actions.addMock')}</span>
                </button>
              )}
              <button
                onClick={() => setShowCreateArrayDialog(true)}
                disabled={busy || availableDisks.filter(d => !d.in_raid && !d.is_os_disk).length < 2}
                className={`whitespace-nowrap rounded-xl border px-3 sm:px-4 py-1.5 sm:py-2 text-xs sm:text-sm transition touch-manipulation active:scale-95 ${
                  busy || availableDisks.filter(d => !d.in_raid && !d.is_os_disk).length < 2
                    ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                    : 'border-emerald-500/40 bg-emerald-500/15 text-emerald-100 hover:border-emerald-500/60'
                }`}
                title={availableDisks.filter(d => !d.in_raid && !d.is_os_disk).length < 2 ? t('system:raid.diskManagement.minDisksRequired') : ''}
              >
                {t('system:raid.actions.createNewArray')}
              </button>
            </div>
          </div>
        </div>

        <div className="px-4 sm:px-6 py-4 sm:py-5">
          {/* Desktop disk table */}
          <div className="hidden lg:block overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-800/60">
              <thead>
                <tr className="text-left text-xs uppercase tracking-[0.24em] text-slate-500">
                  <th className="px-5 py-3">{t('system:raid.tableHeaders.name')}</th>
                  <th className="px-5 py-3">{t('system:raid.tableHeaders.size')}</th>
                  <th className="px-5 py-3">{t('system:raid.tableHeaders.model')}</th>
                  <th className="px-5 py-3">{t('system:raid.tableHeaders.status')}</th>
                  <th className="px-5 py-3">{t('system:raid.tableHeaders.actions')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {availableDisks.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-5 py-8 text-center text-sm text-slate-400">
                      {t('system:raid.diskManagement.noDisks')}
                    </td>
                  </tr>
                ) : (
                  availableDisks.map((disk) => (
                    <tr key={disk.name} className="group transition hover:bg-slate-900/65">
                      <td className="px-5 py-4 text-sm font-medium text-slate-200">/dev/{disk.name}</td>
                      <td className="px-5 py-4 text-sm text-slate-300">{formatBytes(disk.size_bytes)}</td>
                      <td className="px-5 py-4 text-sm text-slate-300">{disk.model || t('system:raid.diskManagement.na')}</td>
                      <td className="px-5 py-4">
                        <div className="flex flex-wrap items-center gap-2">
                          {disk.in_raid ? (
                            (() => {
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
                                  {t('system:raid.diskManagement.inRaid')}
                                </span>
                              );
                            })()
                          ) : (
                            <span className="rounded-full border border-slate-700/50 bg-slate-800/40 px-2 py-0.5 text-xs text-slate-400">
                              {t('system:raid.diskManagement.free')}
                            </span>
                          )}
                          {disk.is_partitioned && (
                            <span className="rounded-full border border-amber-400/30 bg-amber-500/10 px-2 py-0.5 text-xs text-amber-100">
                              {t('system:raid.diskManagement.partitioned')}
                            </span>
                          )}
                          {disk.is_os_disk && (
                            <div className="flex items-center gap-1.5 rounded-full border border-violet-400/30 bg-violet-500/10 px-2.5 py-0.5">
                              <Monitor className="h-3 w-3 text-violet-400" />
                              <span className="text-xs font-medium text-violet-100">
                                {t('system:raid.diskManagement.osDisk')}
                              </span>
                            </div>
                          )}
                          {disk.is_ssd && !disk.is_os_disk && (
                            <div className="flex items-center gap-1 rounded-full border border-cyan-400/30 bg-cyan-500/10 px-2 py-0.5">
                              <Zap className="h-3 w-3 text-cyan-400" />
                              <span className="text-xs font-medium text-cyan-100">SSD</span>
                            </div>
                          )}
                          {disk.is_cache_device && (
                            <span className="rounded-full border border-teal-400/30 bg-teal-500/10 px-2 py-0.5 text-xs text-teal-100">
                              {t('system:raid.diskManagement.cacheDevice')}
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
                          disabled={busy || disk.in_raid || disk.is_os_disk || !!disk.is_cache_device}
                          className={`rounded-lg border px-3 py-1.5 text-xs transition ${
                            busy || disk.in_raid || disk.is_os_disk || disk.is_cache_device
                              ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                              : 'border-rose-500/40 bg-rose-500/10 text-rose-200 hover:border-rose-500/60'
                          }`}
                        >
                          {t('system:raid.actions.format')}
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Mobile disk cards */}
          <div className="lg:hidden space-y-3">
            {availableDisks.length === 0 ? (
              <p className="py-6 text-center text-sm text-slate-400">
                {t('system:raid.diskManagement.noDisks')}
              </p>
            ) : (
              availableDisks.map((disk) => {
                const diskArray = disk.in_raid
                  ? arrays.find(arr => arr.devices.some(dev => dev.name === `${disk.name}1` || dev.name === disk.name))
                  : null;

                return (
                  <div key={`${disk.name}-mobile`} className="rounded-xl border border-slate-800/60 bg-slate-900/60 p-3">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-slate-200">/dev/{disk.name}</span>
                      <span className="text-xs text-slate-400">{formatBytes(disk.size_bytes)}</span>
                    </div>
                    {disk.model && (
                      <p className="mt-1 text-xs text-slate-500 truncate">{disk.model}</p>
                    )}
                    <div className="mt-2 flex flex-wrap items-center gap-1.5">
                      {disk.in_raid ? (
                        diskArray ? (
                          <div className="flex items-center gap-1.5 rounded-full border border-sky-400/30 bg-sky-500/10 px-2 py-0.5">
                            <span className="text-[10px] font-medium text-sky-100">{diskArray.name}</span>
                            <span className="text-[10px] uppercase text-sky-300/70">{diskArray.level}</span>
                          </div>
                        ) : (
                          <span className="rounded-full border border-sky-400/30 bg-sky-500/10 px-2 py-0.5 text-[10px] text-sky-100">
                            {t('system:raid.diskManagement.inRaid')}
                          </span>
                        )
                      ) : (
                        <span className="rounded-full border border-slate-700/50 bg-slate-800/40 px-2 py-0.5 text-[10px] text-slate-400">
                          {t('system:raid.diskManagement.free')}
                        </span>
                      )}
                      {disk.is_partitioned && (
                        <span className="rounded-full border border-amber-400/30 bg-amber-500/10 px-2 py-0.5 text-[10px] text-amber-100">
                          {t('system:raid.diskManagement.partitioned')}
                        </span>
                      )}
                      {disk.is_os_disk && (
                        <div className="flex items-center gap-1 rounded-full border border-violet-400/30 bg-violet-500/10 px-2 py-0.5">
                          <Monitor className="h-2.5 w-2.5 text-violet-400" />
                          <span className="text-[10px] font-medium text-violet-100">
                            {t('system:raid.diskManagement.osDisk')}
                          </span>
                        </div>
                      )}
                      {disk.is_ssd && !disk.is_os_disk && (
                        <div className="flex items-center gap-1 rounded-full border border-cyan-400/30 bg-cyan-500/10 px-2 py-0.5">
                          <Zap className="h-2.5 w-2.5 text-cyan-400" />
                          <span className="text-[10px] font-medium text-cyan-100">SSD</span>
                        </div>
                      )}
                      {disk.is_cache_device && (
                        <span className="rounded-full border border-teal-400/30 bg-teal-500/10 px-2 py-0.5 text-[10px] text-teal-100">
                          {t('system:raid.diskManagement.cacheDevice')}
                        </span>
                      )}
                      {!disk.in_raid && !disk.is_os_disk && (
                        <button
                          onClick={() => {
                            setSelectedDisk(disk);
                            setShowFormatDialog(true);
                          }}
                          disabled={busy}
                          className={`ml-auto rounded-lg border px-2 py-1 text-[10px] transition touch-manipulation active:scale-95 ${
                            busy
                              ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                              : 'border-rose-500/40 bg-rose-500/10 text-rose-200'
                          }`}
                        >
                          {t('system:raid.actions.format')}
                        </button>
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>

      {/* Format Dialog */}
      {showFormatDialog && selectedDisk && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 backdrop-blur-xl" onClick={() => setShowFormatDialog(false)}>
          <div className="card w-full max-w-[95vw] sm:max-w-md border-rose-500/40 bg-slate-900/80 backdrop-blur-2xl shadow-[0_20px_70px_rgba(220,38,38,0.3)]" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-xl font-semibold text-white">{t('system:raid.formatDialog.title')}</h3>
            <p className="mt-2 text-sm text-slate-400">
              {t('system:raid.formatDialog.formatDisk')} <span className="font-medium text-slate-200">/dev/{selectedDisk.name}</span>
            </p>
            <form onSubmit={handleFormatDisk} className="mt-4 space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-300">{t('system:raid.formatDialog.filesystem')}</label>
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
                <label className="block text-sm font-medium text-slate-300">{t('system:raid.formatDialog.label')}</label>
                <input
                  name="label"
                  type="text"
                  placeholder={t('system:raid.formatDialog.labelPlaceholder')}
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
                  {t('system:raid.actions.cancel')}
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
                  {t('system:raid.actions.format')}
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

      {/* Cache Setup Wizard */}
      {cacheWizardArray && (
        <CacheSetupWizard
          arrayName={cacheWizardArray}
          availableDisks={availableDisks}
          onClose={() => setCacheWizardArray(null)}
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
      {dialog}
    </div>
  );
}
