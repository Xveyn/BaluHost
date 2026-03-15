import { useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { handleApiError } from '../lib/errorHandling';
import { useAsyncData } from './useAsyncData';
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
  type CreateScheduleRequest,
} from '../api/sync';
import { generateMobileToken, type MobileRegistrationToken } from '../api/mobile';

export function useDeviceManagement() {
  const { t } = useTranslation(['devices', 'common']);

  const {
    data: devices,
    loading,
    error,
    refetch: refetchDevices,
  } = useAsyncData(getAllDevices);

  const {
    data: schedules,
    loading: schedulesLoading,
    refetch: refetchSchedules,
  } = useAsyncData(listSyncSchedules);

  const { confirm, dialog: confirmDialog } = useConfirmDialog();

  const deviceList = devices ?? [];
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
    mobileDevices,
    desktopDevices,
    stats,
    confirmDialog,
    handleGenerateToken,
    handleCreateSchedule,
    handleDisableSchedule,
    handleEnableSchedule,
    handleSaveDeviceName,
    handleDeleteDevice,
  };
}
