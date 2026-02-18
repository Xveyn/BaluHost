import { type FormEvent, useEffect, useMemo, useState } from 'react';
import toast from 'react-hot-toast';
import { useTranslation } from 'react-i18next';
import { handleApiError, getApiErrorMessage } from '../lib/errorHandling';
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
import { getSystemInfo } from '../api/system';
import RaidSetupWizard from '../components/RaidSetupWizard';
import MockDiskWizard from '../components/MockDiskWizard';
import CacheSetupWizard from '../components/CacheSetupWizard';
import { useConfirmDialog } from '../hooks/useConfirmDialog';
import { RaidArrayCard, DiskTable, FormatDiskDialog } from '../components/raid';

const REFRESH_INTERVAL_MS = 8000;

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
      const message = getApiErrorMessage(err, t('system:raid.messages.loadError'));
      setError(message);
      handleApiError(err, t('system:raid.messages.loadError'));
    } finally {
      setLoading(false);
    }
  };

  const loadAvailableDisks = async () => {
    try {
      const response = await getAvailableDisks();
      setAvailableDisks(response.disks ?? []);
    } catch (err) {
      handleApiError(err, t('system:raid.messages.loadDisksError'));
    }
  };

  useEffect(() => {
    void loadStatus();
    void loadAvailableDisks();

    // Check if Dev-Mode is active
    getSystemInfo()
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
      handleApiError(err, t('system:raid.messages.simulationFailed'));
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
      handleApiError(err, t('system:raid.messages.rebuildFailed'));
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
      handleApiError(err, t('system:raid.messages.finalizeFailed'));
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
      handleApiError(err, t('system:raid.messages.bitmapUpdateFailed'));
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
      handleApiError(err, t('system:raid.messages.scrubFailed'));
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
      handleApiError(err, t('system:raid.messages.writeMostlyFailed'));
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
      handleApiError(err, t('system:raid.messages.removeDeviceFailed'));
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
      handleApiError(err, t('system:raid.messages.addSpareFailed'));
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
      handleApiError(err, t('system:raid.messages.speedLimitFailed'));
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
      handleApiError(err, t('system:raid.messages.formatFailed'));
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
      handleApiError(err, t('system:raid.messages.deleteFailed'));
    } finally {
      setBusy(false);
    }
  };

  const handleRefresh = async () => {
    await loadStatus();
    await loadAvailableDisks();
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

          {arrays.map((array) => (
            <RaidArrayCard
              key={array.name}
              array={array}
              busy={busy}
              speedLimits={speedLimits}
              availableDisks={availableDisks}
              onSimulateFailure={handleSimulateFailure}
              onStartRebuild={handleStartRebuild}
              onFinalize={handleFinalize}
              onToggleBitmap={handleToggleBitmap}
              onTriggerScrub={handleTriggerScrub}
              onWriteMostly={handleWriteMostly}
              onRemoveDevice={handleRemoveDevice}
              onAddSpare={handleAddSpare}
              onUpdateSpeed={handleUpdateSpeed}
              onDeleteArray={handleDeleteArray}
              onSetupCache={(arrayName) => setCacheWizardArray(arrayName)}
              onRefresh={handleRefresh}
            />
          ))}
        </div>
      )}

      {/* Disk Management Section */}
      <DiskTable
        availableDisks={availableDisks}
        arrays={arrays}
        busy={busy}
        isDevMode={isDevMode}
        onRefreshDisks={() => void loadAvailableDisks()}
        onShowMockWizard={() => setShowMockDiskWizard(true)}
        onShowCreateArray={() => setShowCreateArrayDialog(true)}
        onFormatDisk={(disk) => {
          setSelectedDisk(disk);
          setShowFormatDialog(true);
        }}
      />

      {/* Format Dialog */}
      {showFormatDialog && selectedDisk && (
        <FormatDiskDialog
          disk={selectedDisk}
          busy={busy}
          onSubmit={handleFormatDisk}
          onClose={() => {
            setShowFormatDialog(false);
            setSelectedDisk(null);
          }}
        />
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
