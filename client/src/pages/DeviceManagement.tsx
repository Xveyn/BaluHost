import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import {
  Smartphone,
  Monitor,
  Edit2,
  Trash2,
  X,
  Activity,
  CheckCircle,
  QrCode as QrCodeIcon,
  Calendar,
  Clock,
  Plus,
  RefreshCw,
} from 'lucide-react';
import { getAllDevices, updateMobileDeviceName, updateDesktopDeviceName, deleteMobileDevice, type Device } from '../api/devices';
import { createSyncSchedule, listSyncSchedules, disableSyncSchedule, type SyncSchedule, type CreateScheduleRequest } from '../api/sync-schedules';
import { generateMobileToken, type MobileRegistrationToken } from '../lib/api';

type Tab = 'devices' | 'register' | 'schedules';

export default function DeviceManagement() {
  const { t } = useTranslation(['devices', 'common']);
  const [activeTab, setActiveTab] = useState<Tab>('devices');

  // Devices
  const [devices, setDevices] = useState<Device[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Mobile App Registration
  const [qrData, setQrData] = useState<MobileRegistrationToken | null>(null);
  const [showQrDialog, setShowQrDialog] = useState(false);
  const [includeVpn, setIncludeVpn] = useState(false);
  const [newMobileDeviceName, setNewMobileDeviceName] = useState('');
  const [tokenValidityDays, setTokenValidityDays] = useState(90);
  const [generating, setGenerating] = useState(false);

  // Schedules
  const [schedules, setSchedules] = useState<SyncSchedule[]>([]);
  const [schedulesLoading, setSchedulesLoading] = useState(false);
  const [selectedDeviceId, setSelectedDeviceId] = useState('');
  const [scheduleType, setScheduleType] = useState<'daily' | 'weekly' | 'monthly'>('daily');
  const [timeOfDay, setTimeOfDay] = useState('02:00');
  const [dayOfWeek, setDayOfWeek] = useState<number | null>(null);
  const [dayOfMonth, setDayOfMonth] = useState<number | null>(null);

  // Device Edit Modal
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingDevice, setEditingDevice] = useState<Device | null>(null);
  const [newDeviceName, setNewDeviceName] = useState('');

  // Delete Confirmation
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deviceToDelete, setDeviceToDelete] = useState<Device | null>(null);

  useEffect(() => {
    loadDevices();
    loadSchedules();
  }, []);

  const loadDevices = async () => {
    setLoading(true);
    setError(null);

    try {
      const data = await getAllDevices();
      setDevices(data);
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : t('common:toast.loadFailed');
      console.error('Failed to load devices:', err);
      setError(errorMsg);
      toast.error(errorMsg);
    } finally {
      setLoading(false);
    }
  };

  const loadSchedules = async () => {
    setSchedulesLoading(true);

    try {
      const data = await listSyncSchedules();
      setSchedules(data);
    } catch (err) {
      console.error('Failed to load schedules:', err);
    } finally {
      setSchedulesLoading(false);
    }
  };

  const handleGenerateMobileToken = async () => {
    if (!newMobileDeviceName.trim()) {
      toast.error(t('common:toast.enterDeviceName'));
      return;
    }

    try {
      setGenerating(true);
      const token = await generateMobileToken(includeVpn, newMobileDeviceName.trim(), tokenValidityDays);
      setQrData(token);
      setShowQrDialog(true);
      toast.success(t('common:toast.qrGenerated'));
    } catch (error: any) {
      console.error('Failed to generate token:', error);
      const errorMsg = error?.response?.data?.detail || 'Failed to generate QR code';
      toast.error(errorMsg);
    } finally {
      setGenerating(false);
    }
  };

  const handleCreateSchedule = async () => {
    if (!selectedDeviceId) {
      toast.error(t('common:toast.selectDevice'));
      return;
    }

    try {
      const scheduleData: CreateScheduleRequest = {
        device_id: selectedDeviceId,
        schedule_type: scheduleType,
        time_of_day: timeOfDay,
        day_of_week: scheduleType === 'weekly' ? dayOfWeek : null,
        day_of_month: scheduleType === 'monthly' ? dayOfMonth : null,
        sync_deletions: true,
        resolve_conflicts: 'ask'
      };

      await createSyncSchedule(scheduleData);
      toast.success(t('common:toast.scheduleCreated'));
      loadSchedules();

      setSelectedDeviceId('');
      setScheduleType('daily');
      setTimeOfDay('02:00');
      setDayOfWeek(null);
      setDayOfMonth(null);
    } catch (err) {
      toast.error(t('common:toast.scheduleFailed'));
      console.error(err);
    }
  };

  const handleDisableSchedule = async (scheduleId: number) => {
    try {
      await disableSyncSchedule(scheduleId);
      toast.success(t('common:toast.scheduleDisabled'));
      loadSchedules();
    } catch (err) {
      toast.error(t('common:toast.disableFailed'));
      console.error(err);
    }
  };

  const handleEditDevice = (device: Device) => {
    setEditingDevice(device);
    setNewDeviceName(device.name);
    setShowEditModal(true);
  };

  const handleSaveDeviceName = async () => {
    if (!editingDevice || !newDeviceName.trim()) {
      toast.error(t('common:toast.deviceNameEmpty'));
      return;
    }

    try {
      if (editingDevice.type === 'mobile') {
        await updateMobileDeviceName(editingDevice.id, newDeviceName);
      } else {
        await updateDesktopDeviceName(editingDevice.id, newDeviceName);
      }

      toast.success(t('common:toast.deviceUpdated'));
      setShowEditModal(false);
      setEditingDevice(null);
      setNewDeviceName('');
      loadDevices();
    } catch (err) {
      toast.error(t('common:toast.updateFailed'));
      console.error(err);
    }
  };

  const handleDeleteDevice = (device: Device) => {
    setDeviceToDelete(device);
    setShowDeleteConfirm(true);
  };

  const confirmDeleteDevice = async () => {
    if (!deviceToDelete) return;

    try {
      if (deviceToDelete.type === 'mobile') {
        await deleteMobileDevice(deviceToDelete.id);
        toast.success(t('common:toast.deviceDeleted'));
      } else {
        toast.error(t('common:toast.desktopDeleteNotImplemented'));
        setShowDeleteConfirm(false);
        setDeviceToDelete(null);
        return;
      }

      setShowDeleteConfirm(false);
      setDeviceToDelete(null);
      loadDevices();
    } catch (err) {
      toast.error(t('common:toast.deleteFailed'));
      console.error(err);
    }
  };

  const formatDate = (dateStr: string | null | undefined): string => {
    if (!dateStr) return 'Never';
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    const diffDays = Math.floor(diffHours / 24);
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
  };

  const getPlatformIcon = (device: Device) => {
    if (device.type === 'mobile') {
      return <Smartphone className="h-5 w-5" />;
    }
    return <Monitor className="h-5 w-5" />;
  };

  const getPlatformLabel = (platform: string): string => {
    const labels: Record<string, string> = {
      ios: 'iOS',
      android: 'Android',
      windows: 'Windows',
      mac: 'macOS',
      linux: 'Linux',
      unknown: 'Desktop',
    };
    return labels[platform] || platform;
  };

  const mobileDevices = devices.filter((d) => d.type === 'mobile');
  const desktopDevices = devices.filter((d) => d.type === 'desktop');

  const stats = {
    total: devices.length,
    mobile: mobileDevices.length,
    desktop: desktopDevices.length,
    active: devices.filter((d) => d.is_active).length,
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-semibold text-white">{t('title')}</h1>
          <p className="mt-1 text-xs sm:text-sm text-slate-400">
            {t('description')}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={loadDevices}
            className="btn btn-secondary flex items-center gap-2 flex-1 sm:flex-initial justify-center touch-manipulation active:scale-95"
          >
            <Activity className="h-4 w-4" />
            <span>{t('buttons.refresh')}</span>
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="card border-slate-800/60 bg-slate-900/55 p-1">
        <div className="flex gap-2">
          <button
            onClick={() => setActiveTab('devices')}
            className={`flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition ${
              activeTab === 'devices'
                ? 'bg-sky-500/20 text-sky-300 border border-sky-500/30'
                : 'text-slate-400 hover:text-white hover:bg-slate-800/50'
            }`}
          >
            <Activity className="h-4 w-4" />
            <span className="hidden sm:inline">{t('tabs.devices')}</span>
          </button>
          <button
            onClick={() => setActiveTab('register')}
            className={`flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition ${
              activeTab === 'register'
                ? 'bg-sky-500/20 text-sky-300 border border-sky-500/30'
                : 'text-slate-400 hover:text-white hover:bg-slate-800/50'
            }`}
          >
            <QrCodeIcon className="h-4 w-4" />
            <span className="hidden sm:inline">{t('tabs.register')}</span>
            <span className="sm:hidden">{t('tabs.registerShort')}</span>
          </button>
          <button
            onClick={() => setActiveTab('schedules')}
            className={`flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition ${
              activeTab === 'schedules'
                ? 'bg-sky-500/20 text-sky-300 border border-sky-500/30'
                : 'text-slate-400 hover:text-white hover:bg-slate-800/50'
            }`}
          >
            <Calendar className="h-4 w-4" />
            <span className="hidden sm:inline">{t('tabs.schedules')}</span>
            <span className="sm:hidden">{t('tabs.schedulesShort')}</span>
          </button>
        </div>
      </div>

      {/* Tab Content: Devices */}
      {activeTab === 'devices' && (
        <>
          {/* Statistics Cards */}
          <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
            <div className="card border-slate-800/60 bg-slate-900/55 p-3 sm:p-4">
              <div className="flex items-center justify-between">
                <div className="min-w-0 flex-1">
                  <p className="text-xs sm:text-sm text-slate-400 truncate">{t('stats.totalDevices')}</p>
                  <p className="mt-1 text-xl sm:text-2xl font-semibold text-white">{stats.total}</p>
                </div>
                <Activity className="h-6 w-6 sm:h-8 sm:w-8 text-sky-500 flex-shrink-0 ml-2" />
              </div>
            </div>

            <div className="card border-slate-800/60 bg-slate-900/55 p-3 sm:p-4">
              <div className="flex items-center justify-between">
                <div className="min-w-0 flex-1">
                  <p className="text-xs sm:text-sm text-slate-400 truncate">{t('stats.mobile')}</p>
                  <p className="mt-1 text-xl sm:text-2xl font-semibold text-sky-400">{stats.mobile}</p>
                </div>
                <Smartphone className="h-6 w-6 sm:h-8 sm:w-8 text-sky-500 flex-shrink-0 ml-2" />
              </div>
            </div>

            <div className="card border-slate-800/60 bg-slate-900/55 p-3 sm:p-4">
              <div className="flex items-center justify-between">
                <div className="min-w-0 flex-1">
                  <p className="text-xs sm:text-sm text-slate-400 truncate">{t('stats.desktop')}</p>
                  <p className="mt-1 text-xl sm:text-2xl font-semibold text-emerald-400">
                    {stats.desktop}
                  </p>
                </div>
                <Monitor className="h-6 w-6 sm:h-8 sm:w-8 text-emerald-500 flex-shrink-0 ml-2" />
              </div>
            </div>

            <div className="card border-slate-800/60 bg-slate-900/55 p-3 sm:p-4">
              <div className="flex items-center justify-between">
                <div className="min-w-0 flex-1">
                  <p className="text-xs sm:text-sm text-slate-400 truncate">{t('stats.active')}</p>
                  <p className="mt-1 text-xl sm:text-2xl font-semibold text-green-400">{stats.active}</p>
                </div>
                <CheckCircle className="h-6 w-6 sm:h-8 sm:w-8 text-green-500 flex-shrink-0 ml-2" />
              </div>
            </div>
          </div>

          {error && (
            <div className="card border-red-900/60 bg-red-950/30 p-4">
              <p className="text-sm text-red-400">
                <strong>{t('error')}:</strong> {error}
              </p>
            </div>
          )}

          {/* Devices List */}
          {loading ? (
            <div className="card border-slate-800/60 bg-slate-900/55 py-12 text-center">
              <p className="text-sm text-slate-500">{t('loading')}</p>
            </div>
          ) : (
            <div className="space-y-6">
              {/* Mobile Devices */}
              <div className="card border-slate-800/60 bg-slate-900/55">
                <div className="mb-4 flex items-center justify-between">
                  <div>
                    <p className="text-xs uppercase tracking-[0.25em] text-slate-500">{t('sections.mobileDevices')}</p>
                    <h2 className="mt-2 text-xl font-semibold text-white">
                      {t('sections.smartphonesTablets', { count: mobileDevices.length })}
                    </h2>
                  </div>
                </div>

                {mobileDevices.length === 0 ? (
                  <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-8 text-center text-sm text-slate-500">
                    {t('empty.noMobileDevices')}
                  </div>
                ) : (
                  <div className="space-y-3">
                    {mobileDevices.map((device) => (
                      <div
                        key={device.id}
                        className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4 transition hover:border-sky-500/30"
                      >
                        <div className="flex items-start justify-between gap-4">
                          <div className="flex items-center gap-3 min-w-0 flex-1">
                            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-950/70 text-sky-400 flex-shrink-0">
                              {getPlatformIcon(device)}
                            </div>
                            <div className="min-w-0 flex-1">
                              <p className="text-sm font-medium text-slate-100 truncate">{device.name}</p>
                              <p className="text-xs text-slate-500">
                                {getPlatformLabel(device.platform)}
                                {device.model && ` • ${device.model}`}
                                {device.username && ` • ${device.username}`}
                              </p>
                            </div>
                          </div>

                          <div className="flex items-center gap-2 flex-shrink-0">
                            <span
                              className={`rounded-full px-3 py-1 text-xs font-medium ${
                                device.is_active
                                  ? 'border border-green-500/40 bg-green-500/15 text-green-200'
                                  : 'border border-slate-700/70 bg-slate-900/70 text-slate-400'
                              }`}
                            >
                              {device.is_active ? t('common:active') : t('common:inactive')}
                            </span>

                            <button
                              onClick={() => handleEditDevice(device)}
                              className="rounded-lg border border-sky-500/30 bg-sky-500/10 p-2 text-sky-200 transition hover:border-sky-500/50 hover:bg-sky-500/20"
                              title="Edit device name"
                            >
                              <Edit2 className="h-4 w-4" />
                            </button>

                            <button
                              onClick={() => handleDeleteDevice(device)}
                              className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-2 text-rose-200 transition hover:border-rose-500/50 hover:bg-rose-500/20"
                              title="Delete device"
                            >
                              <Trash2 className="h-4 w-4" />
                            </button>
                          </div>
                        </div>

                        <div className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                          <div>
                            <p className="text-slate-500">{t('fields.lastSeen')}</p>
                            <p className="mt-1 font-medium text-slate-200">
                              {formatDate(device.last_seen)}
                            </p>
                          </div>
                          <div>
                            <p className="text-slate-500">{t('fields.lastSync')}</p>
                            <p className="mt-1 font-medium text-slate-200">
                              {formatDate(device.last_sync)}
                            </p>
                          </div>
                          <div>
                            <p className="text-slate-500">{t('fields.registered')}</p>
                            <p className="mt-1 font-medium text-slate-200">
                              {formatDate(device.created_at)}
                            </p>
                          </div>
                          {device.expires_at && (
                            <div>
                              <p className="text-slate-500">{t('fields.expires')}</p>
                              <p className="mt-1 font-medium text-slate-200">
                                {formatDate(device.expires_at)}
                              </p>
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Desktop Devices */}
              <div className="card border-slate-800/60 bg-slate-900/55">
                <div className="mb-4 flex items-center justify-between">
                  <div>
                    <p className="text-xs uppercase tracking-[0.25em] text-slate-500">{t('sections.desktopDevices')}</p>
                    <h2 className="mt-2 text-xl font-semibold text-white">
                      {t('sections.baluDeskClients', { count: desktopDevices.length })}
                    </h2>
                  </div>
                </div>

                {desktopDevices.length === 0 ? (
                  <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-8 text-center text-sm text-slate-500">
                    {t('empty.noDesktopClients')}
                  </div>
                ) : (
                  <div className="space-y-3">
                    {desktopDevices.map((device) => (
                      <div
                        key={device.id}
                        className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4 transition hover:border-emerald-500/30"
                      >
                        <div className="flex items-start justify-between gap-4">
                          <div className="flex items-center gap-3 min-w-0 flex-1">
                            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-950/70 text-emerald-400 flex-shrink-0">
                              {getPlatformIcon(device)}
                            </div>
                            <div className="min-w-0 flex-1">
                              <p className="text-sm font-medium text-slate-100 truncate">{device.name}</p>
                              <p className="text-xs text-slate-500">
                                {getPlatformLabel(device.platform)}
                                {device.username && ` • ${device.username}`}
                              </p>
                            </div>
                          </div>

                          <div className="flex items-center gap-2 flex-shrink-0">
                            <button
                              onClick={() => handleEditDevice(device)}
                              className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-2 text-emerald-200 transition hover:border-emerald-500/50 hover:bg-emerald-500/20"
                              title="Edit device name"
                            >
                              <Edit2 className="h-4 w-4" />
                            </button>
                          </div>
                        </div>

                        <div className="mt-3 grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
                          <div>
                            <p className="text-slate-500">{t('fields.lastSync')}</p>
                            <p className="mt-1 font-medium text-slate-200">
                              {formatDate(device.last_sync)}
                            </p>
                          </div>
                          <div>
                            <p className="text-slate-500">{t('fields.registered')}</p>
                            <p className="mt-1 font-medium text-slate-200">
                              {formatDate(device.created_at)}
                            </p>
                          </div>
                          <div>
                            <p className="text-slate-500">{t('fields.status')}</p>
                            <p className="mt-1 font-medium text-emerald-300">{t('common:active')}</p>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </>
      )}

      {/* Tab Content: Register Mobile App */}
      {activeTab === 'register' && (
        <div className="card border-slate-800/60 bg-slate-900/55">
          <h3 className="text-lg font-semibold mb-4 flex items-center text-white">
            <QrCodeIcon className="w-5 h-5 mr-2 text-sky-400" />
            {t('register.title')}
          </h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-2">
                {t('register.deviceName')}
              </label>
              <input
                type="text"
                value={newMobileDeviceName}
                onChange={(e) => setNewMobileDeviceName(e.target.value)}
                placeholder={t('register.deviceNamePlaceholder')}
                className="input w-full"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-300 mb-2">
                {t('register.validity')}
              </label>
              <div className="space-y-2">
                <input
                  type="range"
                  min="30"
                  max="180"
                  step="1"
                  value={tokenValidityDays}
                  onChange={(e) => setTokenValidityDays(Number(e.target.value))}
                  className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer"
                  style={{
                    background: `linear-gradient(to right, #38bdf8 0%, #38bdf8 ${((tokenValidityDays - 30) / 150) * 100}%, #334155 ${((tokenValidityDays - 30) / 150) * 100}%, #334155 100%)`
                  }}
                />
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-400">{t('register.validityMin')}</span>
                  <span className="text-sky-400 font-semibold text-base">
                    {t('register.validityDisplay', { days: tokenValidityDays, months: Math.round(tokenValidityDays / 30) })}
                  </span>
                  <span className="text-slate-400">{t('register.validityMax')}</span>
                </div>
                <div className="bg-slate-800/50 border border-slate-700/50 rounded-lg p-3">
                  <p className="text-xs text-slate-400">
                    🔔 <strong>{t('register.notifications')}:</strong> {t('register.notificationsDesc')}
                  </p>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="includeVpn"
                checked={includeVpn}
                onChange={(e) => setIncludeVpn(e.target.checked)}
                className="w-4 h-4 rounded border-slate-700 bg-slate-800 text-sky-500 focus:ring-sky-500"
              />
              <label htmlFor="includeVpn" className="text-sm text-slate-300">
                {t('register.includeVpn')}
              </label>
            </div>
            <button
              onClick={handleGenerateMobileToken}
              disabled={generating || !newMobileDeviceName.trim()}
              className="w-full sm:w-auto px-6 py-2.5 bg-sky-500 hover:bg-sky-600 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {generating ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  {t('register.generating')}
                </>
              ) : (
                <>
                  <Plus className="w-4 h-4" />
                  {t('register.generateQr')}
                </>
              )}
            </button>
          </div>
        </div>
      )}

      {/* Tab Content: Sync Schedules */}
      {activeTab === 'schedules' && (
        <div className="card border-slate-800/60 bg-slate-900/55">
          <div className="mb-4">
            <p className="text-xs uppercase tracking-[0.25em] text-slate-500">{t('schedules.title')}</p>
            <h2 className="mt-2 text-xl font-semibold text-white">
              {t('schedules.automatedSync', { count: schedules.length })}
            </h2>
          </div>

          {/* Create Schedule Form */}
          <div className="mb-6 rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
            <h3 className="mb-3 text-sm font-medium text-slate-300 flex items-center gap-2">
              <Plus className="h-4 w-4" />
              {t('schedules.createNew')}
            </h3>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
              <div>
                <label className="block text-xs text-slate-400 mb-1">{t('schedules.device')}</label>
                <select
                  value={selectedDeviceId}
                  onChange={(e) => setSelectedDeviceId(e.target.value)}
                  className="w-full rounded-lg border border-slate-700 bg-slate-900/70 px-3 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
                >
                  <option value="">{t('schedules.selectDevice')}</option>
                  {devices.map((device) => (
                    <option key={device.id} value={device.id}>
                      {device.name} ({device.type})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs text-slate-400 mb-1">{t('schedules.frequency')}</label>
                <select
                  value={scheduleType}
                  onChange={(e) => setScheduleType(e.target.value as 'daily' | 'weekly' | 'monthly')}
                  className="w-full rounded-lg border border-slate-700 bg-slate-900/70 px-3 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
                >
                  <option value="daily">{t('schedules.daily')}</option>
                  <option value="weekly">{t('schedules.weekly')}</option>
                  <option value="monthly">{t('schedules.monthly')}</option>
                </select>
              </div>

              <div>
                <label className="block text-xs text-slate-400 mb-1">{t('schedules.time')}</label>
                <input
                  type="time"
                  value={timeOfDay}
                  onChange={(e) => setTimeOfDay(e.target.value)}
                  className="w-full rounded-lg border border-slate-700 bg-slate-900/70 px-3 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
                />
              </div>

              {scheduleType === 'weekly' && (
                <div>
                  <label className="block text-xs text-slate-400 mb-1">{t('schedules.dayOfWeek')}</label>
                  <select
                    value={dayOfWeek ?? ''}
                    onChange={(e) => setDayOfWeek(e.target.value ? parseInt(e.target.value) : null)}
                    className="w-full rounded-lg border border-slate-700 bg-slate-900/70 px-3 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
                  >
                    <option value="">{t('schedules.selectDay')}</option>
                    <option value="0">{t('days.sunday')}</option>
                    <option value="1">{t('days.monday')}</option>
                    <option value="2">{t('days.tuesday')}</option>
                    <option value="3">{t('days.wednesday')}</option>
                    <option value="4">{t('days.thursday')}</option>
                    <option value="5">{t('days.friday')}</option>
                    <option value="6">{t('days.saturday')}</option>
                  </select>
                </div>
              )}

              {scheduleType === 'monthly' && (
                <div>
                  <label className="block text-xs text-slate-400 mb-1">{t('schedules.dayOfMonth')}</label>
                  <input
                    type="number"
                    min="1"
                    max="31"
                    value={dayOfMonth ?? ''}
                    onChange={(e) => setDayOfMonth(e.target.value ? parseInt(e.target.value) : null)}
                    placeholder="1-31"
                    className="w-full rounded-lg border border-slate-700 bg-slate-900/70 px-3 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
                  />
                </div>
              )}

              <div className="flex items-end">
                <button
                  onClick={handleCreateSchedule}
                  className="w-full rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-2 text-sm font-medium text-emerald-200 hover:border-emerald-500/50 hover:bg-emerald-500/20 touch-manipulation active:scale-95 flex items-center justify-center gap-2"
                >
                  <Plus className="h-4 w-4" />
                  {t('buttons.create')}
                </button>
              </div>
            </div>
          </div>

          {/* Schedules List */}
          {schedulesLoading ? (
            <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-8 text-center text-sm text-slate-500">
              {t('schedules.loadingSchedules')}
            </div>
          ) : schedules.length === 0 ? (
            <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-8 text-center text-sm text-slate-500">
              {t('schedules.noSchedules')}
            </div>
          ) : (
            <div className="space-y-3">
              {schedules.map((schedule) => {
                const device = devices.find((d) => d.id === schedule.device_id);
                const deviceName = device?.name || schedule.device_id;

                return (
                  <div
                    key={schedule.schedule_id}
                    className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4 transition hover:border-amber-500/30"
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex items-center gap-3 min-w-0 flex-1">
                        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-950/70 text-amber-400 flex-shrink-0">
                          <Calendar className="h-5 w-5" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-medium text-slate-100 truncate">
                            {deviceName}
                          </p>
                          <p className="text-xs text-slate-500">
                            {schedule.schedule_type.charAt(0).toUpperCase() + schedule.schedule_type.slice(1)} at {schedule.time_of_day}
                            {schedule.day_of_week !== null && schedule.day_of_week !== undefined && ` • ${['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][schedule.day_of_week]}`}
                            {schedule.day_of_month !== null && schedule.day_of_month !== undefined && ` • Day ${schedule.day_of_month}`}
                          </p>
                        </div>
                      </div>

                      <div className="flex items-center gap-2 flex-shrink-0">
                        <span
                          className={`rounded-full px-3 py-1 text-xs font-medium ${
                            schedule.is_enabled
                              ? 'border border-emerald-500/40 bg-emerald-500/15 text-emerald-200'
                              : 'border border-slate-700/70 bg-slate-900/70 text-slate-400'
                          }`}
                        >
                          {schedule.is_enabled ? t('common:enabled') : t('common:disabled')}
                        </span>

                        {schedule.is_enabled && (
                          <button
                            onClick={() => handleDisableSchedule(schedule.schedule_id)}
                            className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-2 text-rose-200 transition hover:border-rose-500/50 hover:bg-rose-500/20"
                            title="Disable schedule"
                          >
                            <X className="h-4 w-4" />
                          </button>
                        )}
                      </div>
                    </div>

                    {schedule.next_run_at && (
                      <div className="mt-3 flex items-center gap-2 text-xs text-slate-400">
                        <Clock className="h-3 w-3" />
                        <span>{t('schedules.nextRun')} {formatDate(schedule.next_run_at)}</span>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* QR Code Dialog */}
      {showQrDialog && qrData && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-xl max-w-md w-full p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xl font-semibold text-white">{t('qrDialog.title')}</h3>
              <button
                onClick={() => {
                  setShowQrDialog(false);
                  setQrData(null);
                  setNewMobileDeviceName('');
                  setIncludeVpn(false);
                  loadDevices();
                }}
                className="text-slate-400 hover:text-white transition-colors"
              >
                ✕
              </button>
            </div>

            <div className="bg-white p-4 rounded-lg mb-4">
              <img
                src={`data:image/png;base64,${qrData.qr_code}`}
                alt="QR Code"
                className="w-full h-auto"
              />
            </div>

            <div className="space-y-2 text-sm text-slate-300 mb-4">
              <p>✓ {t('qrDialog.scanInfo')}</p>
              <p>✓ {t('qrDialog.tokenValidity')}</p>
              <p>✓ {t('qrDialog.deviceValidity', { days: qrData.device_token_validity_days, months: Math.round(qrData.device_token_validity_days / 30) })}</p>
              {qrData.vpn_config && (
                <p className="text-green-400">✓ {t('qrDialog.vpnIncluded')}</p>
              )}
            </div>

            <div className="bg-sky-500/10 border border-sky-500/30 rounded-lg p-3 mb-4">
              <p className="text-xs text-sky-300 font-semibold mb-1.5 flex items-center gap-1.5">
                🔔 {t('qrDialog.reminders')}
              </p>
              <p className="text-xs text-slate-300">
                {t('qrDialog.remindersDesc')}
              </p>
            </div>

            <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-3">
              <p className="text-xs text-slate-400 mb-1">{t('qrDialog.expiresAt')}</p>
              <p className="text-sm text-white font-mono">
                {new Date(qrData.expires_at).toLocaleString()}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Edit Device Name Modal */}
      {showEditModal && editingDevice && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-md rounded-lg border border-slate-800 bg-slate-900 p-4 sm:p-6 shadow-xl">
            <div className="mb-3 sm:mb-4 flex items-center justify-between">
              <h2 className="text-lg sm:text-xl font-semibold text-white">{t('modal.editTitle')}</h2>
              <button
                onClick={() => {
                  setShowEditModal(false);
                  setEditingDevice(null);
                  setNewDeviceName('');
                }}
                className="rounded-lg p-2 hover:bg-slate-800 touch-manipulation active:scale-95"
              >
                <X className="h-5 w-5 text-slate-400" />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">
                  {t('fields.deviceName')}
                </label>
                <input
                  type="text"
                  value={newDeviceName}
                  onChange={(e) => setNewDeviceName(e.target.value)}
                  className="w-full rounded-lg border border-slate-700 bg-slate-900/70 px-4 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
                  placeholder={t('register.deviceNamePlaceholder')}
                />
              </div>

              <div className="text-xs text-slate-500">
                <p>{t('fields.type')}: {editingDevice.type === 'mobile' ? t('stats.mobile') : t('stats.desktop')}</p>
                <p>{t('fields.platform')}: {getPlatformLabel(editingDevice.platform)}</p>
              </div>
            </div>

            <div className="mt-6 flex gap-2">
              <button
                onClick={() => {
                  setShowEditModal(false);
                  setEditingDevice(null);
                  setNewDeviceName('');
                }}
                className="flex-1 rounded-lg border border-slate-700 bg-slate-900/70 px-4 py-2 text-sm font-medium text-slate-300 hover:bg-slate-800 touch-manipulation active:scale-95"
              >
                {t('buttons.cancel')}
              </button>
              <button
                onClick={handleSaveDeviceName}
                className="flex-1 rounded-lg border border-sky-500/30 bg-sky-500/10 px-4 py-2 text-sm font-medium text-sky-200 hover:border-sky-500/50 hover:bg-sky-500/20 touch-manipulation active:scale-95"
              >
                {t('buttons.save')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {showDeleteConfirm && deviceToDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-sm rounded-lg border border-slate-800 bg-slate-900 p-4 sm:p-6 shadow-xl">
            <div className="mb-3 sm:mb-4 flex items-center gap-3">
              <div className="rounded-full bg-rose-500/20 p-2 sm:p-3">
                <Trash2 className="h-5 w-5 sm:h-6 sm:w-6 text-rose-500" />
              </div>
              <h2 className="text-lg sm:text-xl font-semibold text-white">{t('modal.deleteTitle')}</h2>
            </div>

            <p className="mb-4 sm:mb-6 text-sm text-slate-400">
              {t('modal.deleteConfirm', { name: deviceToDelete.name })}
            </p>

            <div className="flex gap-2">
              <button
                onClick={() => {
                  setShowDeleteConfirm(false);
                  setDeviceToDelete(null);
                }}
                className="flex-1 rounded-lg border border-slate-700 bg-slate-900/70 px-4 py-2 text-sm font-medium text-slate-300 hover:bg-slate-800 touch-manipulation active:scale-95"
              >
                {t('buttons.cancel')}
              </button>
              <button
                onClick={confirmDeleteDevice}
                className="flex-1 rounded-lg border border-rose-500/30 bg-rose-500/10 px-4 py-2 text-sm font-medium text-rose-200 hover:border-rose-500/50 hover:bg-rose-500/20 touch-manipulation active:scale-95"
              >
                {t('buttons.delete')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
