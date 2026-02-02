/**
 * Tapo Device Settings Component
 *
 * Admin-only interface for configuring Tapo smart plugs for power monitoring.
 */

import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Zap, Plus, Trash2, Power, AlertCircle, CheckCircle } from 'lucide-react';
import toast from 'react-hot-toast';
import {
  listTapoDevices,
  createTapoDevice,
  deleteTapoDevice,
} from '../api/power';
import type { TapoDevice, TapoDeviceCreate } from '../api/power';

const TapoDeviceSettings: React.FC = () => {
  const { t } = useTranslation('settings');
  const [devices, setDevices] = useState<TapoDevice[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddForm, setShowAddForm] = useState(false);

  // Form state
  const [formData, setFormData] = useState<TapoDeviceCreate>({
    name: '',
    device_type: 'P115',
    ip_address: '',
    email: '',
    password: '',
    is_monitoring: true,
  });

  // Load devices
  const loadDevices = async () => {
    try {
      const data = await listTapoDevices();
      setDevices(data);
    } catch (error: any) {
      console.error('Failed to load devices:', error);
      toast.error('Failed to load devices');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDevices();
  }, []);

  // Handle form submit
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Validation
    if (!formData.name || !formData.ip_address || !formData.email || !formData.password) {
      toast.error('Please fill in all required fields');
      return;
    }

    try {
      await createTapoDevice(formData);
      toast.success('Device added successfully');

      // Reset form
      setFormData({
        name: '',
        device_type: 'P115',
        ip_address: '',
        email: '',
        password: '',
        is_monitoring: true,
      });
      setShowAddForm(false);

      // Reload devices
      loadDevices();
    } catch (error: any) {
      console.error('Failed to create device:', error);
      toast.error(error.response?.data?.detail || 'Failed to add device');
    }
  };

  // Handle delete
  const handleDelete = async (deviceId: number, deviceName: string) => {
    if (!confirm(`Are you sure you want to delete "${deviceName}"?`)) {
      return;
    }

    try {
      await deleteTapoDevice(deviceId);
      toast.success('Device deleted');
      loadDevices();
    } catch (error: any) {
      console.error('Failed to delete device:', error);
      toast.error('Failed to delete device');
    }
  };

  if (loading) {
    return (
      <div className="card">
        <p className="text-sm text-slate-500">{t('tapo.loading')}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white">{t('tapo.title')}</h2>
          <p className="text-sm text-slate-400 mt-1">
            {t('tapo.description')}
          </p>
        </div>
        <button
          onClick={() => setShowAddForm(!showAddForm)}
          className="btn-primary flex items-center gap-2"
        >
          <Plus className="w-4 h-4" />
          {t('tapo.addDevice')}
        </button>
      </div>

      {/* Add Device Form */}
      {showAddForm && (
        <div className="card bg-slate-800/50 border-amber-500/20">
          <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
            <Zap className="w-5 h-5 text-amber-500" />
            {t('tapo.addTapoDevice')}
          </h3>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">
                  {t('tapo.deviceName')} *
                </label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  placeholder={t('tapo.deviceNamePlaceholder')}
                  className="input w-full"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">
                  {t('tapo.deviceType')}
                </label>
                <select
                  value={formData.device_type}
                  onChange={(e) => setFormData({ ...formData, device_type: e.target.value })}
                  className="input w-full"
                >
                  <option value="P115">P115</option>
                  <option value="P110">P110</option>
                  <option value="P125M">P125M</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">
                  {t('tapo.ipAddress')} *
                </label>
                <input
                  type="text"
                  value={formData.ip_address}
                  onChange={(e) => setFormData({ ...formData, ip_address: e.target.value })}
                  placeholder="192.168.1.50"
                  className="input w-full"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">
                  {t('tapo.accountEmail')} *
                </label>
                <input
                  type="email"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  placeholder={t('tapo.emailPlaceholder')}
                  className="input w-full"
                  required
                />
              </div>

              <div className="md:col-span-2">
                <label className="block text-sm font-medium text-slate-300 mb-2">
                  {t('tapo.accountPassword')} *
                </label>
                <input
                  type="password"
                  value={formData.password}
                  onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                  placeholder={t('tapo.passwordPlaceholder')}
                  className="input w-full"
                  required
                />
                <p className="text-xs text-slate-500 mt-1">
                  {t('tapo.credentialsEncrypted')}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="is_monitoring"
                checked={formData.is_monitoring}
                onChange={(e) => setFormData({ ...formData, is_monitoring: e.target.checked })}
                className="rounded border-slate-600 bg-slate-700 text-amber-500 focus:ring-amber-500"
              />
              <label htmlFor="is_monitoring" className="text-sm text-slate-300">
                {t('tapo.enableMonitoring')}
              </label>
            </div>

            <div className="flex gap-3 justify-end">
              <button
                type="button"
                onClick={() => setShowAddForm(false)}
                className="btn-secondary"
              >
                {t('tapo.cancel')}
              </button>
              <button type="submit" className="btn-primary">
                {t('tapo.addDevice')}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Device List */}
      <div className="card">
        <h3 className="text-lg font-semibold text-white mb-4">{t('tapo.configuredDevices')}</h3>

        {devices.length === 0 ? (
          <div className="text-center py-8">
            <Zap className="w-12 h-12 text-slate-600 mx-auto mb-3" />
            <p className="text-slate-400">{t('tapo.noDevices')}</p>
            <p className="text-sm text-slate-500 mt-1">
              {t('tapo.noDevicesHint')}
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {devices.map((device) => {
              const isOnline = device.last_connected && !device.last_error;
              const hasError = !!device.last_error;

              return (
                <div
                  key={device.id}
                  className="flex items-center justify-between p-4 bg-slate-800/50 rounded-lg border border-slate-700/50"
                >
                  <div className="flex items-center gap-4 flex-1">
                    {/* Status Icon */}
                    <div className={`p-2 rounded-lg ${
                      isOnline ? 'bg-emerald-500/10' :
                      hasError ? 'bg-red-500/10' : 'bg-slate-700'
                    }`}>
                      {isOnline ? (
                        <CheckCircle className="w-5 h-5 text-emerald-500" />
                      ) : hasError ? (
                        <AlertCircle className="w-5 h-5 text-red-500" />
                      ) : (
                        <Power className="w-5 h-5 text-slate-500" />
                      )}
                    </div>

                    {/* Device Info */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <h4 className="text-sm font-semibold text-white truncate">
                          {device.name}
                        </h4>
                        <span className="text-xs text-slate-500">
                          {device.device_type}
                        </span>
                      </div>
                      <p className="text-xs text-slate-400 mt-0.5">
                        {device.ip_address}
                      </p>
                      {device.last_error && (
                        <p className="text-xs text-red-400 mt-1 truncate">
                          {device.last_error}
                        </p>
                      )}
                      {device.last_connected && !device.last_error && (
                        <p className="text-xs text-emerald-400 mt-1">
                          {t('tapo.lastSeen')}: {new Date(device.last_connected).toLocaleString()}
                        </p>
                      )}
                    </div>
                  </div>

                  {/* Actions */}
                  <button
                    onClick={() => handleDelete(device.id, device.name)}
                    className="btn-secondary p-2 hover:bg-red-500/10 hover:text-red-500 transition-colors"
                    title="Delete device"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

export default TapoDeviceSettings;
