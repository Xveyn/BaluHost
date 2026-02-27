import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { handleApiError } from '../lib/errorHandling';
import { useAsyncData } from './useAsyncData';
import {
  listSyncSchedules,
  createSyncSchedule,
  updateSyncSchedule,
  disableSyncSchedule,
  getBandwidthLimits,
  saveBandwidthLimits as saveBandwidthApi,
  getSyncDevices,
  getDeviceFolders,
  revokeVpnClient as revokeVpnApi,
  type SyncDevice,
  type SyncSchedule,
  type SyncFolderItem,
} from '../api/sync';

export interface ScheduleFormData {
  scheduleType: string;
  scheduleTime: string;
  dayOfWeek: number;
  dayOfMonth: number;
}

export function useSyncSettings() {
  const { t } = useTranslation('settings');

  const [deviceFolders, setDeviceFolders] = useState<Record<string, SyncFolderItem[]>>({});

  // ── Data fetching ─────────────────────────────────────────────────────
  const {
    data: devices,
    loading: devicesLoading,
    refetch: refetchDevices,
  } = useAsyncData<SyncDevice[]>(getSyncDevices);

  const {
    data: schedules,
    loading: schedulesLoading,
    refetch: refetchSchedules,
  } = useAsyncData<SyncSchedule[]>(listSyncSchedules);

  const {
    data: bandwidth,
    refetch: refetchBandwidth,
  } = useAsyncData(getBandwidthLimits);

  // ── Fetch folders for all devices ─────────────────────────────────────
  useEffect(() => {
    if (!devices || devices.length === 0) return;
    const load = async () => {
      const map: Record<string, SyncFolderItem[]> = {};
      await Promise.all(
        devices.map(async (dev) => {
          map[dev.device_id] = await getDeviceFolders(dev.device_id);
        }),
      );
      setDeviceFolders(map);
    };
    load();
  }, [devices]);

  // ── Handlers ──────────────────────────────────────────────────────────
  const handleCreateSchedule = useCallback(
    async (deviceId: string, form: ScheduleFormData): Promise<boolean> => {
      try {
        const payload: Record<string, unknown> = {
          device_id: deviceId,
          schedule_type: form.scheduleType,
          time_of_day: form.scheduleTime,
          sync_deletions: true,
          resolve_conflicts: 'keep_newest',
        };
        if (form.scheduleType === 'weekly') payload.day_of_week = form.dayOfWeek;
        else if (form.scheduleType === 'monthly') payload.day_of_month = form.dayOfMonth;

        await createSyncSchedule(payload as any);
        toast.success(t('sync.scheduleCreated'));
        refetchSchedules();
        return true;
      } catch (err) {
        handleApiError(err, t('sync.createScheduleFailed'));
        return false;
      }
    },
    [t, refetchSchedules],
  );

  const handleUpdateSchedule = useCallback(
    async (id: number, form: ScheduleFormData): Promise<boolean> => {
      try {
        const payload: Record<string, unknown> = {
          schedule_type: form.scheduleType,
          time_of_day: form.scheduleTime,
        };
        if (form.scheduleType === 'weekly') {
          payload.day_of_week = form.dayOfWeek;
          payload.day_of_month = null;
        } else if (form.scheduleType === 'monthly') {
          payload.day_of_month = form.dayOfMonth;
          payload.day_of_week = null;
        } else {
          payload.day_of_week = null;
          payload.day_of_month = null;
        }

        await updateSyncSchedule(id, payload);
        toast.success(t('sync.scheduleUpdated'));
        refetchSchedules();
        return true;
      } catch (err) {
        handleApiError(err, t('sync.updateScheduleFailed'));
        return false;
      }
    },
    [t, refetchSchedules],
  );

  const handleDisableSchedule = useCallback(
    async (id: number) => {
      try {
        await disableSyncSchedule(id);
        toast.success(t('sync.scheduleDisabled'));
        refetchSchedules();
      } catch (err) {
        handleApiError(err, t('sync.disableScheduleFailed'));
      }
    },
    [t, refetchSchedules],
  );

  const handleSaveBandwidth = useCallback(
    async (upload: number | null, download: number | null): Promise<boolean> => {
      try {
        await saveBandwidthApi(upload, download);
        toast.success(t('sync.bandwidthSaved'));
        refetchBandwidth();
        return true;
      } catch (err) {
        handleApiError(err, t('sync.saveLimitsFailed'));
        return false;
      }
    },
    [t, refetchBandwidth],
  );

  const handleRevokeVpn = useCallback(
    async (clientId: number) => {
      try {
        await revokeVpnApi(clientId);
        toast.success(t('sync.vpnRevoked'));
        refetchDevices();
      } catch (err) {
        handleApiError(err, t('sync.revokeVpnFailed'));
      }
    },
    [t, refetchDevices],
  );

  return {
    devices: devices ?? [],
    schedules: schedules ?? [],
    bandwidth,
    loading: devicesLoading,
    schedulesLoading,
    refetchSchedules,
    refetchDevices,
    deviceFolders,
    handleCreateSchedule,
    handleUpdateSchedule,
    handleDisableSchedule,
    handleSaveBandwidth,
    handleRevokeVpn,
  };
}
