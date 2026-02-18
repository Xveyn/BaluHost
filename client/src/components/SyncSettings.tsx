import { useState, useEffect } from 'react';
import { Clock, Smartphone, HardDrive, Calendar, Settings, Trash2, CheckCircle, AlertTriangle, Edit2, X, Save } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { apiClient } from '../lib/api';
import { useAuth } from '../contexts/AuthContext';

interface SyncDevice {
  device_id: string;
  device_name: string;
  status: string;
  last_sync: string;
  pending_changes: number;
  conflicts: number;
  vpn_client_id?: number | null;
  vpn_assigned_ip?: string | null;
  vpn_last_handshake?: string | null;
  vpn_active?: boolean | null;
}

interface SyncSchedule {
  schedule_id: number;
  device_id: string;
  schedule_type: string;
  time_of_day: string;
  day_of_week?: number | null;
  day_of_month?: number | null;
  next_run_at: string | null;
  last_run_at: string | null;
  sync_deletions?: boolean;
  resolve_conflicts?: string;
}

interface SyncFolderItem {
  id: string;
  device_id: string;
  local_path: string;
  remote_path: string;
  sync_type: string;
  auto_sync: boolean;
  last_sync?: string | null;
  status?: string | null;
}

const WEEKDAYS = [
  { value: 0, label: 'Mo' },
  { value: 1, label: 'Di' },
  { value: 2, label: 'Mi' },
  { value: 3, label: 'Do' },
  { value: 4, label: 'Fr' },
  { value: 5, label: 'Sa' },
  { value: 6, label: 'So' },
];

export default function SyncSettings() {
  const { t } = useTranslation('settings');
  const { token } = useAuth();
  const [devices, setDevices] = useState<SyncDevice[]>([]);
  const [schedules, setSchedules] = useState<SyncSchedule[]>([]);
  const [selectedDevice, setSelectedDevice] = useState<string>('');
  const [deviceFolders, setDeviceFolders] = useState<Record<string, SyncFolderItem[]>>({});
  const [, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // New schedule form
  const [scheduleType, setScheduleType] = useState('daily');
  const [scheduleTime, setScheduleTime] = useState('02:00');
  const [dayOfWeek, setDayOfWeek] = useState<number>(0);
  const [dayOfMonth, setDayOfMonth] = useState<number>(1);
  const [syncDeletions] = useState(true);
  const [resolveConflicts] = useState('keep_newest');

  // Edit modal state
  const [editingSchedule, setEditingSchedule] = useState<SyncSchedule | null>(null);
  const [editScheduleType, setEditScheduleType] = useState('daily');
  const [editScheduleTime, setEditScheduleTime] = useState('02:00');
  const [editDayOfWeek, setEditDayOfWeek] = useState<number>(0);
  const [editDayOfMonth, setEditDayOfMonth] = useState<number>(1);
  const [isSaving, setIsSaving] = useState(false);

  // Bandwidth
  const [uploadLimit, setUploadLimit] = useState<number | null>(null);
  const [downloadLimit, setDownloadLimit] = useState<number | null>(null);

  useEffect(() => {
    loadSyncData();
  }, []);

  // Clear messages after timeout
  useEffect(() => {
    if (error || success) {
      const timer = setTimeout(() => {
        setError(null);
        setSuccess(null);
      }, 5000);
      return () => clearTimeout(timer);
    }
  }, [error, success]);

  async function loadSyncData() {
    setLoading(true);
    try {

      // Load schedules
      const schedulesRes = await fetch('/api/sync/schedule/list', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const schedulesData = await schedulesRes.json();
      setSchedules(schedulesData.schedules || []);

      // Load bandwidth limits
      const bandwidthRes = await fetch('/api/sync/bandwidth/limit', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const bandwidthData = await bandwidthRes.json();
      setUploadLimit(bandwidthData.upload_speed_limit);
      setDownloadLimit(bandwidthData.download_speed_limit);

      // Load registered devices
      let mapped: SyncDevice[] = [];

      // First try sync devices (desktop clients)
      try {
        const devRes = await fetch('/api/sync/devices', { headers: { 'Authorization': `Bearer ${token}` } });
        if (devRes.ok) {
          const devData = await devRes.json();
          const list = Array.isArray(devData) ? devData : (devData.devices || []);
          mapped = list.map((d: Record<string, unknown>) => ({
            device_id: (d.device_id ?? d.id ?? d.name) as string,
            device_name: (d.device_name ?? d.name) as string,
            status: (d.status as string) ?? 'unknown',
            last_sync: (d.last_sync ?? d.last_seen ?? null) as string | null,
            pending_changes: (d.pending_changes as number) ?? 0,
            conflicts: (d.conflicts as number) ?? 0,
            vpn_client_id: (d.vpn_client_id ?? (d.vpn as Record<string, unknown> | undefined)?.id ?? null) as number | null,
            vpn_assigned_ip: (d.vpn_assigned_ip ?? (d.vpn as Record<string, unknown> | undefined)?.assigned_ip ?? null) as string | null,
            vpn_last_handshake: (d.vpn_last_handshake ?? (d.vpn as Record<string, unknown> | undefined)?.last_handshake ?? null) as string | null,
            vpn_active: (d.vpn_active ?? (d.vpn as Record<string, unknown> | undefined)?.is_active ?? null) as boolean | null,
          }));
        }
      } catch {
        // Non-critical: sync devices endpoint may not be available
      }

      // If no devices from sync API, try mobile devices endpoint
      if (!mapped || mapped.length === 0) {
        try {
          const mobRes = await fetch('/api/mobile/devices', { headers: { 'Authorization': `Bearer ${token}` } });
          if (mobRes.ok) {
            const mobData = await mobRes.json();
            const list = Array.isArray(mobData) ? mobData : (mobData.devices || mobData);
            mapped = list.map((d: Record<string, unknown>) => ({
              device_id: (d.id ?? d.device_id ?? d.deviceId) as string,
              device_name: (d.device_name ?? d.name ?? d.deviceName) as string,
              status: (d.is_active === false) ? 'inactive' : 'active',
              last_sync: (d.last_sync ?? d.last_seen ?? null) as string | null,
              pending_changes: (d.pending_uploads ?? d.pending_changes ?? 0) as number,
              conflicts: 0,
              vpn_client_id: (d.vpn_client_id ?? null) as number | null,
              vpn_assigned_ip: (d.vpn_assigned_ip ?? null) as string | null,
              vpn_last_handshake: (d.vpn_last_handshake ?? null) as string | null,
              vpn_active: (d.vpn_active ?? null) as boolean | null,
            }));
          }
        } catch {
          // Non-critical: mobile devices endpoint may not be available
        }
      }

      setDevices(mapped);

      // Auto-select first device if available
      if (mapped.length > 0 && !selectedDevice) {
        setSelectedDevice(mapped[0].device_id);
      }

      // Fetch per-device sync folders
      try {
        const foldersMap: Record<string, SyncFolderItem[]> = {};
        await Promise.all(mapped.map(async (dev) => {
          try {
            const fRes = await fetch(`/api/mobile/sync/folders/${encodeURIComponent(dev.device_id)}`, {
              headers: { 'Authorization': `Bearer ${token}` }
            });
            if (fRes.ok) {
              const fData = await fRes.json();
              const list = Array.isArray(fData) ? fData : (fData.folders || fData);
              foldersMap[dev.device_id] = list.map((f: Record<string, unknown>) => ({
                id: f.id as string,
                device_id: f.device_id as string,
                local_path: f.local_path as string,
                remote_path: f.remote_path as string,
                sync_type: f.sync_type as string,
                auto_sync: f.auto_sync as boolean,
                last_sync: (f.last_sync ?? null) as string | null,
                status: (f.status ?? null) as string | null,
              }));
            } else {
              foldersMap[dev.device_id] = [];
            }
          } catch {
            foldersMap[dev.device_id] = [];
          }
        }));
        setDeviceFolders(foldersMap);
      } catch {
        // Non-critical: per-device folders will remain empty
      }

    } catch {
      setError('Failed to load sync settings');
    } finally {
      setLoading(false);
    }
  }

  async function createSchedule() {
    if (!selectedDevice) {
      setError(t('sync.selectDeviceFirst'));
      return;
    }

    try {
      const payload: Record<string, unknown> = {
        device_id: selectedDevice,
        schedule_type: scheduleType,
        time_of_day: scheduleTime,
        sync_deletions: syncDeletions,
        resolve_conflicts: resolveConflicts
      };

      if (scheduleType === 'weekly') {
        payload.day_of_week = dayOfWeek;
      } else if (scheduleType === 'monthly') {
        payload.day_of_month = dayOfMonth;
      }

      await apiClient.post('/api/sync/schedule/create', payload);
      setSuccess(t('sync.scheduleCreated'));
      await loadSyncData();
    } catch (err: unknown) {
      const msg = err != null && typeof err === 'object' && 'response' in err
        ? ((err as { response?: { data?: { detail?: string } } }).response?.data?.detail)
        : (err instanceof Error ? err.message : undefined);
      setError(msg || t('sync.createScheduleFailed'));
    }
  }

  async function disableSchedule(scheduleId: number) {
    try {
      await apiClient.post(`/api/sync/schedule/${scheduleId}/disable`);
      setSuccess(t('sync.scheduleDisabled'));
      await loadSyncData();
    } catch {
      setError(t('sync.disableScheduleFailed'));
    }
  }

  async function updateSchedule() {
    if (!editingSchedule) return;

    setIsSaving(true);
    try {
      const payload: Record<string, unknown> = {
        schedule_type: editScheduleType,
        time_of_day: editScheduleTime,
      };

      if (editScheduleType === 'weekly') {
        payload.day_of_week = editDayOfWeek;
        payload.day_of_month = null;
      } else if (editScheduleType === 'monthly') {
        payload.day_of_month = editDayOfMonth;
        payload.day_of_week = null;
      } else {
        payload.day_of_week = null;
        payload.day_of_month = null;
      }

      await apiClient.put(`/api/sync/schedule/${editingSchedule.schedule_id}`, payload);
      setSuccess(t('sync.scheduleUpdated'));
      setEditingSchedule(null);
      await loadSyncData();
    } catch (err: unknown) {
      const msg = err != null && typeof err === 'object' && 'response' in err
        ? ((err as { response?: { data?: { detail?: string } } }).response?.data?.detail)
        : (err instanceof Error ? err.message : undefined);
      setError(msg || t('sync.updateScheduleFailed'));
    } finally {
      setIsSaving(false);
    }
  }

  function openEditModal(schedule: SyncSchedule) {
    setEditingSchedule(schedule);
    setEditScheduleType(schedule.schedule_type);
    setEditScheduleTime(schedule.time_of_day);
    setEditDayOfWeek(schedule.day_of_week ?? 0);
    setEditDayOfMonth(schedule.day_of_month ?? 1);
  }

  async function saveBandwidthLimits() {
    try {
      await apiClient.post('/api/sync/bandwidth/limit', {
        upload_speed_limit: uploadLimit,
        download_speed_limit: downloadLimit
      });
      setSuccess(t('sync.bandwidthSaved'));
    } catch {
      setError(t('sync.saveLimitsFailed'));
    }
  }

  async function revokeVpnClient(clientId: number) {
    if (!clientId) return;
    try {
      await apiClient.post(`/api/vpn/clients/${clientId}/revoke`);
      setSuccess(t('sync.vpnRevoked'));
      await loadSyncData();
    } catch (err: unknown) {
      const msg = err != null && typeof err === 'object' && 'response' in err
        ? ((err as { response?: { data?: { detail?: string } } }).response?.data?.detail)
        : (err instanceof Error ? err.message : undefined);
      setError(msg || t('sync.revokeVpnFailed'));
    }
  }

  function formatDate(date: string | null) {
    if (!date) return 'N/A';
    return new Date(date).toLocaleString('de-DE');
  }

  function getDeviceName(deviceId: string): string {
    const device = devices.find(d => d.device_id === deviceId);
    return device?.device_name || deviceId;
  }

  function getScheduleDescription(schedule: SyncSchedule): string {
    let desc = schedule.time_of_day;
    if (schedule.schedule_type === 'weekly' && schedule.day_of_week !== null) {
      const day = WEEKDAYS.find(d => d.value === schedule.day_of_week);
      desc = `${day?.label || 'Mo'}, ${schedule.time_of_day}`;
    } else if (schedule.schedule_type === 'monthly' && schedule.day_of_month !== null) {
      desc = `${schedule.day_of_month}., ${schedule.time_of_day}`;
    }
    return desc;
  }

  return (
    <div className="space-y-6 w-full">
      <div className="rounded-lg shadow bg-slate-900/55 p-6">
        <h2 className="text-2xl font-bold mb-4 flex items-center gap-2">
          <Settings className="w-6 h-6" />
          {t('sync.title')}
        </h2>

        {error && (
          <div className="mb-4 p-4 bg-red-500/10 border border-red-500/20 rounded-lg flex items-center gap-2 text-red-400">
            <AlertTriangle className="w-5 h-5 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {success && (
          <div className="mb-4 p-4 bg-emerald-500/10 border border-emerald-500/20 rounded-lg flex items-center gap-2 text-emerald-400">
            <CheckCircle className="w-5 h-5 flex-shrink-0" />
            <span>{success}</span>
          </div>
        )}

        {/* Device Registration Info */}
        <div className="mb-6">
          <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
            <Smartphone className="w-5 h-5" />
            {t('sync.deviceRegistration')}
          </h3>
          <div className="text-slate-400 text-sm">
            {t('sync.deviceRegistrationInfo')}
            <div className="mt-2">
              {t('sync.manageDevicesFrom')} <a href="/mobile-devices" className="text-sky-400 underline">{t('sync.mobileAppsPage')}</a>
            </div>
          </div>
        </div>

        {/* Schedule Creation */}
        <div className="mb-6">
          <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
            <Calendar className="w-5 h-5" />
            {t('sync.createSchedule')}
          </h3>

          <div className="space-y-4">
            {/* Row 1: Device & Schedule Type */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {/* Device Dropdown */}
              <div>
                <label className="block text-sm text-slate-400 mb-1">{t('sync.device')}</label>
                <select
                  value={selectedDevice}
                  onChange={(e) => setSelectedDevice(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100"
                >
                  <option value="">{t('sync.selectDevice')}</option>
                  {devices.map((device) => (
                    <option key={device.device_id} value={device.device_id}>
                      {device.device_name} ({device.device_id.substring(0, 8)}...)
                    </option>
                  ))}
                </select>
              </div>

              {/* Schedule Type */}
              <div>
                <label className="block text-sm text-slate-400 mb-1">{t('sync.scheduleType')}</label>
                <select
                  value={scheduleType}
                  onChange={(e) => setScheduleType(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100"
                >
                  <option value="daily">{t('sync.daily')}</option>
                  <option value="weekly">{t('sync.weekly')}</option>
                  <option value="monthly">{t('sync.monthly')}</option>
                </select>
              </div>
            </div>

            {/* Row 2: Time & Day Selection */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {/* Time */}
              <div>
                <label className="block text-sm text-slate-400 mb-1">{t('sync.time')}</label>
                <input
                  type="time"
                  value={scheduleTime}
                  onChange={(e) => setScheduleTime(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100"
                />
              </div>

              {/* Day of Week (for weekly) */}
              {scheduleType === 'weekly' && (
                <div>
                  <label className="block text-sm text-slate-400 mb-1">{t('sync.dayOfWeek')}</label>
                  <div className="flex gap-1">
                    {WEEKDAYS.map((day) => (
                      <button
                        key={day.value}
                        type="button"
                        onClick={() => setDayOfWeek(day.value)}
                        className={`flex-1 px-2 py-2 rounded-lg text-sm font-medium transition-colors ${
                          dayOfWeek === day.value
                            ? 'bg-sky-500 text-white'
                            : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
                        }`}
                      >
                        {day.label}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Day of Month (for monthly) */}
              {scheduleType === 'monthly' && (
                <div>
                  <label className="block text-sm text-slate-400 mb-1">{t('sync.dayOfMonth')}</label>
                  <select
                    value={dayOfMonth}
                    onChange={(e) => setDayOfMonth(parseInt(e.target.value))}
                    className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100"
                  >
                    {Array.from({ length: 31 }, (_, i) => i + 1).map((day) => (
                      <option key={day} value={day}>{day}.</option>
                    ))}
                  </select>
                </div>
              )}
            </div>

            {/* Create Button */}
            <button
              onClick={createSchedule}
              disabled={!selectedDevice}
              className="px-4 py-2 bg-emerald-500 hover:bg-emerald-600 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg transition-colors"
            >
              {t('sync.createScheduleBtn')}
            </button>
          </div>
        </div>

        {/* Bandwidth Limits */}
        <div className="mb-6">
          <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
            <HardDrive className="w-5 h-5" />
            {t('sync.bandwidthLimits')}
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <input
              type="number"
              placeholder={t('sync.uploadLimit')}
              value={uploadLimit || ''}
              onChange={(e) => setUploadLimit(e.target.value ? parseInt(e.target.value) : null)}
              className="px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100"
            />
            <input
              type="number"
              placeholder={t('sync.downloadLimit')}
              value={downloadLimit || ''}
              onChange={(e) => setDownloadLimit(e.target.value ? parseInt(e.target.value) : null)}
              className="px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100"
            />
            <button
              onClick={saveBandwidthLimits}
              className="px-4 py-2 bg-sky-500 hover:bg-sky-600 text-white rounded-lg transition-colors"
            >
              {t('sync.saveLimits')}
            </button>
          </div>
        </div>

        {/* Active Schedules */}
        <div>
          <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
            <Clock className="w-5 h-5" />
            {t('sync.activeSchedules')}
          </h3>
          {schedules.length === 0 ? (
            <div className="text-slate-400 text-center py-8">
              {t('sync.noSchedules')}
            </div>
          ) : (
            <div className="space-y-3">
              {schedules.map((schedule) => (
                <div
                  key={schedule.schedule_id}
                  className="p-4 bg-slate-800/50 border border-slate-700 rounded-lg flex items-center justify-between"
                >
                  <div className="flex-1">
                    <div className="flex items-center gap-3 flex-wrap">
                      <span className="font-medium text-slate-200">{getDeviceName(schedule.device_id)}</span>
                      <span className="px-2 py-1 bg-sky-500/20 text-sky-400 text-xs rounded-full border border-sky-500/30">
                        {schedule.schedule_type}
                      </span>
                      <span className="text-sm text-slate-400">{getScheduleDescription(schedule)}</span>
                    </div>
                    <div className="text-xs text-slate-500 mt-1">
                      {t('sync.nextRun')}: {formatDate(schedule.next_run_at)} | {t('sync.lastRun')}: {formatDate(schedule.last_run_at)}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => openEditModal(schedule)}
                      className="p-2 text-sky-400 hover:bg-sky-500/10 rounded-lg transition-colors"
                      title="Edit schedule"
                    >
                      <Edit2 className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => disableSchedule(schedule.schedule_id)}
                      className="p-2 text-red-400 hover:bg-red-500/10 rounded-lg transition-colors"
                      title="Delete schedule"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Registered Devices */}
      <div className="rounded-lg shadow bg-slate-900/55 p-6">
        <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
          <Smartphone className="w-5 h-5" />
          {t('sync.registeredDevices')}
        </h3>
        {devices.length === 0 ? (
          <div className="text-slate-400 text-center py-6">{t('sync.noDevices')}</div>
        ) : (
          <div className="space-y-3">
            {devices.map((d) => (
              <div key={d.device_id} className="p-4 bg-slate-800/50 border border-slate-700 rounded-lg">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-medium text-slate-200">
                      {d.device_name}
                      <span className="text-xs text-slate-400 ml-2">({d.device_id.substring(0, 8)}...)</span>
                    </div>
                    <div className="text-xs text-slate-500">
                      {t('sync.status')}: {d.status} | {t('sync.lastSync')}: {formatDate(d.last_sync)}
                    </div>
                  </div>
                  <div className="text-right">
                    {d.vpn_client_id ? (
                      <div className="text-xs text-slate-300">
                        <div className="flex items-center gap-3">
                          <div>{t('sync.vpn')}: <span className="font-medium text-sky-300">{d.vpn_assigned_ip ?? `client ${d.vpn_client_id}`}</span></div>
                          <button
                            onClick={() => revokeVpnClient(d.vpn_client_id!)}
                            className="px-2 py-1 bg-rose-600 hover:bg-rose-700 text-white text-xs rounded transition-colors"
                          >
                            {t('sync.revokeVpn')}
                          </button>
                        </div>
                        <div className="text-xs text-slate-500">
                          {t('sync.lastHandshake')}: {d.vpn_last_handshake ? formatDate(d.vpn_last_handshake) : 'N/A'}
                        </div>
                      </div>
                    ) : (
                      <div className="text-xs text-slate-400">{t('sync.noVpnConfigured')}</div>
                    )}
                  </div>
                </div>
                {/* Per-device sync folders */}
                <div className="mt-3 border-t border-slate-700 pt-3">
                  <div className="text-sm text-slate-400 mb-2">{t('sync.syncFolders')}</div>
                  {deviceFolders[d.device_id] && deviceFolders[d.device_id].length > 0 ? (
                    <div className="space-y-2">
                      {deviceFolders[d.device_id].map((f) => (
                        <div key={f.id} className="p-2 bg-slate-800/40 border border-slate-700 rounded-lg text-xs">
                          <div className="font-medium text-slate-200">{f.local_path} → {f.remote_path}</div>
                          <div className="text-slate-400 text-xs mt-1">
                            Type: {f.sync_type} | Auto: {f.auto_sync ? 'yes' : 'no'} | Status: {f.status ?? 'N/A'}
                          </div>
                          <div className="text-slate-500 text-xs">Last sync: {formatDate(f.last_sync ?? null)}</div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-xs text-slate-500">No sync folders configured for this device</div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Edit Modal */}
      {editingSchedule && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div
            className="absolute inset-0 bg-black/60"
            onClick={() => setEditingSchedule(null)}
          />
          <div className="relative z-10 w-full max-w-md rounded-lg bg-slate-900 shadow-xl">
            {/* Header */}
            <div className="flex items-center justify-between border-b border-slate-800 px-6 py-4">
              <h3 className="text-lg font-medium text-white">{t('sync.editSchedule')}</h3>
              <button
                onClick={() => setEditingSchedule(null)}
                className="rounded-md p-1 text-slate-400 hover:bg-slate-800 hover:text-white transition-colors"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Content */}
            <div className="px-6 py-4 space-y-4">
              <div className="text-sm text-slate-400">
                {t('sync.device')}: <span className="text-slate-200">{getDeviceName(editingSchedule.device_id)}</span>
              </div>

              {/* Schedule Type */}
              <div>
                <label className="block text-sm text-slate-400 mb-1">{t('sync.scheduleType')}</label>
                <select
                  value={editScheduleType}
                  onChange={(e) => setEditScheduleType(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100"
                >
                  <option value="daily">{t('sync.daily')}</option>
                  <option value="weekly">{t('sync.weekly')}</option>
                  <option value="monthly">{t('sync.monthly')}</option>
                </select>
              </div>

              {/* Time */}
              <div>
                <label className="block text-sm text-slate-400 mb-1">{t('sync.time')}</label>
                <input
                  type="time"
                  value={editScheduleTime}
                  onChange={(e) => setEditScheduleTime(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100"
                />
              </div>

              {/* Day of Week (for weekly) */}
              {editScheduleType === 'weekly' && (
                <div>
                  <label className="block text-sm text-slate-400 mb-1">{t('sync.dayOfWeek')}</label>
                  <div className="flex gap-1">
                    {WEEKDAYS.map((day) => (
                      <button
                        key={day.value}
                        type="button"
                        onClick={() => setEditDayOfWeek(day.value)}
                        className={`flex-1 px-2 py-2 rounded-lg text-sm font-medium transition-colors ${
                          editDayOfWeek === day.value
                            ? 'bg-sky-500 text-white'
                            : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
                        }`}
                      >
                        {day.label}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Day of Month (for monthly) */}
              {editScheduleType === 'monthly' && (
                <div>
                  <label className="block text-sm text-slate-400 mb-1">{t('sync.dayOfMonth')}</label>
                  <select
                    value={editDayOfMonth}
                    onChange={(e) => setEditDayOfMonth(parseInt(e.target.value))}
                    className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100"
                  >
                    {Array.from({ length: 31 }, (_, i) => i + 1).map((day) => (
                      <option key={day} value={day}>{day}.</option>
                    ))}
                  </select>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="flex justify-end gap-2 border-t border-slate-800 px-6 py-4">
              <button
                onClick={() => setEditingSchedule(null)}
                className="px-4 py-2 text-sm text-slate-300 hover:bg-slate-800 rounded-lg transition-colors"
              >
                {t('sync.cancel')}
              </button>
              <button
                onClick={updateSchedule}
                disabled={isSaving}
                className="inline-flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white text-sm rounded-lg transition-colors"
              >
                <Save className="w-4 h-4" />
                {isSaving ? t('sync.saving') : t('sync.saveChanges')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
