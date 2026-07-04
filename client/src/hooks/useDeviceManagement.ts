import { useCallback, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { handleApiError, getApiErrorMessage } from '../lib/errorHandling';
import { queryKeys } from '../lib/queryKeys';
import { useConfirmDialog } from './useConfirmDialog';
import {
  getAllDevices,
  updateMobileDeviceName,
  updateDesktopDeviceName,
  deleteMobileDevice,
  type Device,
} from '../api/devices';
import {
  createSyncSchedule,
  listSyncSchedules,
  disableSyncSchedule,
  enableSyncSchedule,
  deleteSyncSchedule,
  updateSyncSchedule,
  getBandwidthLimits,
  saveBandwidthLimits,
  getSyncPreflight,
  type CreateScheduleRequest,
} from '../api/sync';
import { generateMobileToken, type MobileRegistrationToken } from '../api/mobile';

export function useDeviceManagement() {
  const { t } = useTranslation(['devices', 'common']);

  // Reads — TanStack Query (no polling). refetch* wrappers keep the () => void
  // shape the handlers already call after mutations; refetch is stable in v5.
  const devicesQuery = useQuery({ queryKey: queryKeys.devices.list(), queryFn: getAllDevices });
  const schedulesQuery = useQuery({ queryKey: queryKeys.sync.schedules(), queryFn: listSyncSchedules });
  const bandwidthQuery = useQuery({ queryKey: queryKeys.sync.bandwidth(), queryFn: getBandwidthLimits });
  const preflightQuery = useQuery({ queryKey: queryKeys.sync.preflight(), queryFn: getSyncPreflight });

  const devices = devicesQuery.data ?? null;
  const loading = devicesQuery.isLoading;
  const error = devicesQuery.isError
    ? getApiErrorMessage(devicesQuery.error, 'An error occurred')
    : null;
  const schedules = schedulesQuery.data ?? null;
  const schedulesLoading = schedulesQuery.isLoading;
  const bandwidth = bandwidthQuery.data;
  const preflight = preflightQuery.data;

  // v5 refetch is referentially stable; destructure so the wrappers stay stable
  // (handlers depend on these) without pulling in the whole query object.
  const { refetch: refetchDevicesRaw } = devicesQuery;
  const { refetch: refetchSchedulesRaw } = schedulesQuery;
  const { refetch: refetchBandwidthRaw } = bandwidthQuery;
  const refetchDevices = useCallback(() => {
    void refetchDevicesRaw();
  }, [refetchDevicesRaw]);
  const refetchSchedules = useCallback(() => {
    void refetchSchedulesRaw();
  }, [refetchSchedulesRaw]);
  const refetchBandwidth = useCallback(() => {
    void refetchBandwidthRaw();
  }, [refetchBandwidthRaw]);

  const { confirm, dialog: confirmDialog } = useConfirmDialog();

  const deviceList = useMemo(() => devices ?? [], [devices]);
  const scheduleList = schedules ?? [];

  const mobileDevices = useMemo(() => deviceList.filter((d) => d.type === 'mobile'), [deviceList]);
  const desktopDevices = useMemo(() => deviceList.filter((d) => d.type === 'desktop'), [deviceList]);

  const stats = useMemo(
    () => ({
      total: deviceList.length,
      mobile: mobileDevices.length,
      desktop: desktopDevices.length,
      active: deviceList.filter((d) => d.is_active).length,
    }),
    [deviceList, mobileDevices, desktopDevices],
  );

  const handleGenerateToken = useCallback(
    async (name: string, includeVpn: boolean, validityDays: number, vpnType: string = 'auto'): Promise<MobileRegistrationToken | null> => {
      if (!name.trim()) {
        toast.error(t('common:toast.enterDeviceName'));
        return null;
      }
      try {
        const token = await generateMobileToken(includeVpn, name.trim(), validityDays, vpnType);
        toast.success(t('common:toast.qrGenerated'));
        return token;
      } catch (err) {
        handleApiError(err, 'Failed to generate QR code');
        return null;
      }
    },
    [t],
  );

  const handleCreateSchedule = useCallback(
    async (data: CreateScheduleRequest) => {
      if (!data.device_id) {
        toast.error(t('common:toast.selectDevice'));
        return false;
      }
      try {
        await createSyncSchedule(data);
        toast.success(t('common:toast.scheduleCreated'));
        refetchSchedules();
        return true;
      } catch {
        toast.error(t('common:toast.scheduleFailed'));
        return false;
      }
    },
    [t, refetchSchedules],
  );

  const handleDisableSchedule = useCallback(
    async (scheduleId: number) => {
      try {
        await disableSyncSchedule(scheduleId);
        toast.success(t('toast.scheduleDisabled'));
        refetchSchedules();
      } catch {
        toast.error(t('toast.disableFailed'));
      }
    },
    [t, refetchSchedules],
  );

  const handleEnableSchedule = useCallback(
    async (scheduleId: number) => {
      try {
        await enableSyncSchedule(scheduleId);
        toast.success(t('toast.scheduleEnabled'));
        refetchSchedules();
      } catch {
        toast.error(t('toast.enableFailed'));
      }
    },
    [t, refetchSchedules],
  );

  const handleDeleteSchedule = useCallback(
    async (scheduleId: number) => {
      const confirmed = await confirm(
        t('toast.deleteScheduleConfirm'),
        { title: t('toast.deleteScheduleTitle'), variant: 'danger', confirmLabel: t('buttons.delete'), cancelLabel: t('buttons.cancel') },
      );
      if (!confirmed) return;

      try {
        await deleteSyncSchedule(scheduleId);
        toast.success(t('toast.scheduleDeleted'));
        refetchSchedules();
      } catch {
        toast.error(t('toast.deleteFailed'));
      }
    },
    [t, confirm, refetchSchedules],
  );

  const handleUpdateSchedule = useCallback(
    async (scheduleId: number, data: Record<string, unknown>) => {
      try {
        await updateSyncSchedule(scheduleId, data);
        toast.success(t('toast.scheduleUpdated'));
        refetchSchedules();
        return true;
      } catch {
        toast.error(t('toast.updateFailed'));
        return false;
      }
    },
    [t, refetchSchedules],
  );

  const handleSaveBandwidth = useCallback(
    async (upload: number | null, download: number | null): Promise<boolean> => {
      try {
        await saveBandwidthLimits(upload, download);
        toast.success(t('toast.bandwidthSaved'));
        refetchBandwidth();
        return true;
      } catch {
        toast.error(t('toast.bandwidthSaveFailed'));
        return false;
      }
    },
    [t, refetchBandwidth],
  );

  const handleSaveDeviceName = useCallback(
    async (device: Device, newName: string) => {
      if (!newName.trim()) {
        toast.error(t('common:toast.deviceNameEmpty'));
        return false;
      }
      try {
        if (device.type === 'mobile') {
          await updateMobileDeviceName(device.id, newName);
        } else {
          await updateDesktopDeviceName(device.id, newName);
        }
        toast.success(t('common:toast.deviceUpdated'));
        refetchDevices();
        return true;
      } catch {
        toast.error(t('common:toast.updateFailed'));
        return false;
      }
    },
    [t, refetchDevices],
  );

  const handleDeleteDevice = useCallback(
    async (device: Device) => {
      const confirmed = await confirm(
        t('modal.deleteConfirm', { name: device.name }),
        { title: t('modal.deleteTitle'), variant: 'danger', confirmLabel: t('buttons.delete'), cancelLabel: t('buttons.cancel') },
      );
      if (!confirmed) return;

      try {
        if (device.type === 'mobile') {
          await deleteMobileDevice(device.id);
          toast.success(t('common:toast.deviceDeleted'));
        } else {
          toast.error(t('common:toast.desktopDeleteNotImplemented'));
          return;
        }
        refetchDevices();
      } catch {
        toast.error(t('common:toast.deleteFailed'));
      }
    },
    [t, confirm, refetchDevices],
  );

  return {
    devices: deviceList,
    loading,
    error,
    refetchDevices,
    schedules: scheduleList,
    schedulesLoading,
    refetchSchedules,
    bandwidth: bandwidth ?? null,
    sleepSchedule: preflight?.sleep_schedule ?? null,
    handleSaveBandwidth,
    mobileDevices,
    desktopDevices,
    stats,
    confirmDialog,
    handleGenerateToken,
    handleCreateSchedule,
    handleDisableSchedule,
    handleEnableSchedule,
    handleDeleteSchedule,
    handleUpdateSchedule,
    handleSaveDeviceName,
    handleDeleteDevice,
  };
}
