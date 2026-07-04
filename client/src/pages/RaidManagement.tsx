import { type FormEvent, useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { handleApiError } from '../lib/errorHandling';
import {
  deleteArray,
  finalizeRaidRebuild,
  formatDisk,
  markDeviceFailed,
  startRaidRebuild,
  type AvailableDisk,
  type FormatDiskPayload,
  type RaidArray,
  type RaidDevice,
  type RaidOptionsPayload,
  updateRaidOptions,
} from '../api/raid';
import { getSystemInfo } from '../api/system';
import { queryKeys } from '../lib/queryKeys';
import { useRaidStatus } from '../hooks/useRaidStatus';
import { useAvailableDisks } from '../hooks/useAvailableDisks';
import RaidSetupWizard from '../components/RaidSetupWizard';
import MockDiskWizard from '../components/MockDiskWizard';
import { useConfirmDialog } from '../hooks/useConfirmDialog';
import { RaidArrayCard, DiskTable, FormatDiskDialog } from '../components/raid';

const REFRESH_INTERVAL_MS = 8000;

export default function RaidManagement() {
  const { t } = useTranslation(['system', 'common']);
  const navigate = useNavigate();
  const { confirm, dialog } = useConfirmDialog();
  const queryClient = useQueryClient();

  // Reads — TanStack Query. Status polls every REFRESH_INTERVAL_MS (shared cache
  // with the dashboard's useRaidStatus); disks + dev-mode fetch once (no poll).
  const {
    raidData,
    raidLoading: loading,
    error,
    lastUpdated,
    refetch: refetchStatus,
  } = useRaidStatus({ pollInterval: REFRESH_INTERVAL_MS });
  const { disks: availableDisks } = useAvailableDisks();
  const { data: systemInfo } = useQuery({
    queryKey: queryKeys.system.info(),
    queryFn: getSystemInfo,
  });

  const arrays = raidData?.arrays ?? [];
  const speedLimits = raidData?.speed_limits ?? null;
  const isDevMode = systemInfo?.dev_mode === true;

  const [busy, setBusy] = useState<boolean>(false);

  // Disk Management dialog states
  const [showFormatDialog, setShowFormatDialog] = useState<boolean>(false);
  const [showCreateArrayDialog, setShowCreateArrayDialog] = useState<boolean>(false);
  const [showMockDiskWizard, setShowMockDiskWizard] = useState<boolean>(false);
  const [selectedDisk, setSelectedDisk] = useState<AvailableDisk | null>(null);

  // Mutations stay imperative (own the `busy` flag + per-action toast) but route
  // their reload through the query layer — awaited so buttons stay disabled until
  // fresh data lands, preserving the previous busy-until-refresh UX.
  const refreshStatus = () =>
    queryClient.invalidateQueries({ queryKey: queryKeys.raid.status() });
  const refreshDisks = () =>
    queryClient.invalidateQueries({ queryKey: queryKeys.raid.availableDisks() });

  const handleManualRefresh = async () => {
    const ok = await refetchStatus();
    if (ok) {
      toast.success(t('system:raid.messages.statusUpdated'));
    }
  };

  const refreshDisabled = useMemo(() => busy || loading, [busy, loading]);

  const handleSimulateFailure = async (array: RaidArray, device?: RaidDevice) => {
    setBusy(true);
    try {
      const response = await markDeviceFailed(array.name, device?.name);
      toast.success(response.message);
      await refreshStatus();
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
      await refreshStatus();
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
      await refreshStatus();
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
      await refreshStatus();
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
      await refreshStatus();
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
      await refreshStatus();
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
      await refreshStatus();
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
      await refreshStatus();
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
      await refreshStatus();
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
      await refreshDisks();
    } catch (err) {
      handleApiError(err, t('system:raid.messages.formatFailed'));
    } finally {
      setBusy(false);
    }
  };

  const handleNavigateToCache = (_arrayName: string) => {
    navigate('/admin/system-control?tab=ssdcache');
  };

  const handleDeleteArray = async (arrayName: string) => {
    const ok = await confirm(t('system:raid.messages.deleteConfirm', { name: arrayName }), { title: t('system:raid.deleteArray'), variant: 'danger', confirmLabel: t('system:raid.deleteArray') });
    if (!ok) return;

    setBusy(true);
    try {
      const response = await deleteArray({ array: arrayName, force: true });
      toast.success(response.message);
      await refreshStatus();
      await refreshDisks();
    } catch (err) {
      handleApiError(err, t('system:raid.messages.deleteFailed'));
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
            onClick={handleManualRefresh}
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
              onNavigateToCache={handleNavigateToCache}
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
        onRefreshDisks={() => void refreshDisks()}
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
            await refreshStatus();
            await refreshDisks();
          }}
        />
      )}

      {/* Mock Disk Wizard (Dev-Mode only) */}
      {showMockDiskWizard && isDevMode && (
        <MockDiskWizard
          onClose={() => setShowMockDiskWizard(false)}
          onSuccess={async () => {
            await refreshStatus();
            await refreshDisks();
            setShowMockDiskWizard(false);
          }}
        />
      )}
      {dialog}
    </div>
  );
}
