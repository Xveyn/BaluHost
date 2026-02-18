import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { handleApiError, getApiErrorMessage } from '../lib/errorHandling';
import {
  Smartphone,
  Monitor,
  Edit2,
  Trash2,
  X,
  Activity,
  CheckCircle,
} from 'lucide-react';
import { getAllDevices, updateMobileDeviceName, updateDesktopDeviceName, deleteMobileDevice, type Device } from '../api/devices';

export default function SyncPrototype() {
  const { t } = useTranslation(['devices', 'common']);
  const [devices, setDevices] = useState<Device[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Modal states
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingDevice, setEditingDevice] = useState<Device | null>(null);
  const [newDeviceName, setNewDeviceName] = useState('');

  // Delete confirmation modal
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deviceToDelete, setDeviceToDelete] = useState<Device | null>(null);

  useEffect(() => {
    loadDevices();
  }, []);

  const loadDevices = async () => {
    setLoading(true);
    setError(null);

    try {
      const data = await getAllDevices();
      setDevices(data);
    } catch (err) {
      const errorMsg = getApiErrorMessage(err, t('common:toast.loadFailed'));
      setError(errorMsg);
      handleApiError(err, t('common:toast.loadFailed'));
    } finally {
      setLoading(false);
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
          {/* Mobile Devices Section */}
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
                          {device.is_active ? t('platforms.active', 'Active') : t('platforms.inactive', 'Inactive')}
                        </span>

                        <button
                          onClick={() => handleEditDevice(device)}
                          className="rounded-lg border border-sky-500/30 bg-sky-500/10 p-2 text-sky-200 transition hover:border-sky-500/50 hover:bg-sky-500/20"
                          title={t('modal.editTitle')}
                        >
                          <Edit2 className="h-4 w-4" />
                        </button>

                        <button
                          onClick={() => handleDeleteDevice(device)}
                          className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-2 text-rose-200 transition hover:border-rose-500/50 hover:bg-rose-500/20"
                          title={t('modal.deleteTitle')}
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

          {/* Desktop Devices Section */}
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
                          title={t('modal.editTitle')}
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
                        <p className="mt-1 font-medium text-emerald-300">{t('stats.active')}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
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
                  placeholder={t('fields.deviceName')}
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
