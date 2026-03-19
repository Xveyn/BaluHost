/**
 * Smart Devices Page
 *
 * Displays all registered IoT/smart devices with real-time state updates
 * via WebSocket. Admin users can add and delete devices.
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { Zap, Plus, RefreshCw, Loader2, Cpu } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { smartDevicesApi } from '../api/smart-devices';
import type { SmartDevice, PowerSummary } from '../api/smart-devices';
import { SmartDeviceCard } from '../components/smart-devices/SmartDeviceCard';
import { AddDeviceModal } from '../components/smart-devices/AddDeviceModal';
import { buildApiUrl } from '../lib/api';
import toast from 'react-hot-toast';

export default function SmartDevicesPage() {
  const { t } = useTranslation('common');
  const { isAdmin, token } = useAuth();

  const [devices, setDevices] = useState<SmartDevice[]>([]);
  const [powerSummary, setPowerSummary] = useState<PowerSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);

  // WebSocket ref for real-time state updates
  const wsRef = useRef<WebSocket | null>(null);

  // --- Data loading ---

  const loadDevices = useCallback(async () => {
    try {
      const res = await smartDevicesApi.list();
      setDevices(res.data.devices);
    } catch {
      toast.error(t('smartDevices.errors.loadFailed', 'Failed to load smart devices'));
    }
  }, [t]);

  const loadPowerSummary = useCallback(async () => {
    try {
      const res = await smartDevicesApi.getPowerSummary();
      setPowerSummary(res.data);
    } catch {
      // Power summary is best-effort; no toast needed
    }
  }, []);

  const loadAll = useCallback(async () => {
    setLoading(true);
    await Promise.all([loadDevices(), loadPowerSummary()]);
    setLoading(false);
  }, [loadDevices, loadPowerSummary]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  // --- WebSocket for real-time device state updates ---

  useEffect(() => {
    if (!token) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    // Reuse the notifications WS endpoint; the backend broadcasts
    // smart_device_update messages on the same channel.
    const wsUrl = `${protocol}//${host}${buildApiUrl('/api/notifications/ws')}?token=${token}`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data as string) as {
          type: string;
          payload?: unknown;
        };

        if (data.type === 'smart_device_update' && Array.isArray(data.payload)) {
          const changes = data.payload as Array<{
            device_id: number;
            name: string;
            state: Record<string, unknown>;
            timestamp: string;
          }>;

          setDevices((prev) =>
            prev.map((d) => {
              const change = changes.find((c) => c.device_id === d.id);
              if (!change) return d;
              return {
                ...d,
                state: change.state,
                is_online: true,
                last_seen: change.timestamp,
              };
            })
          );

          // Refresh power summary silently on state change
          loadPowerSummary();
        }
      } catch {
        // ignore malformed messages
      }
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [token, loadPowerSummary]);

  // --- Actions ---

  const handleStateChange = (id: number, state: Record<string, unknown>) => {
    setDevices((prev) =>
      prev.map((d) => (d.id === id ? { ...d, state } : d))
    );
    loadPowerSummary();
  };

  const handleDelete = async (id: number) => {
    const device = devices.find((d) => d.id === id);
    if (!device) return;
    if (!window.confirm(`Delete "${device.name}"? This cannot be undone.`)) return;

    try {
      await smartDevicesApi.delete(id);
      setDevices((prev) => prev.filter((d) => d.id !== id));
      toast.success(`Deleted "${device.name}"`);
      loadPowerSummary();
    } catch {
      toast.error('Failed to delete device');
    }
  };

  // --- Render helpers ---

  const onlineCount = devices.filter((d) => d.is_online).length;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-sky-400" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-2xl sm:text-3xl font-semibold text-white">
            {t('smartDevices.title', 'Smart Devices')}
          </h1>
          <p className="text-xs sm:text-sm text-slate-400 mt-1">
            {t('smartDevices.description', 'Manage and control IoT devices connected to BaluHost')}
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* Refresh */}
          <button
            onClick={loadAll}
            className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800/40 px-3 py-1.5 text-xs font-medium text-slate-400 hover:border-slate-600 hover:text-slate-300 transition touch-manipulation active:scale-95"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            {t('common.refresh', 'Refresh')}
          </button>

          {/* Add device (admin only) */}
          {isAdmin && (
            <button
              onClick={() => setShowAddModal(true)}
              className="flex items-center gap-1.5 rounded-lg border border-sky-500/40 bg-sky-500/10 px-3 py-1.5 text-xs font-medium text-sky-300 hover:border-sky-500/60 hover:bg-sky-500/20 transition touch-manipulation active:scale-95"
            >
              <Plus className="h-3.5 w-3.5" />
              {t('smartDevices.addDevice', 'Add Device')}
            </button>
          )}
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {/* Total devices */}
        <div className="rounded-xl border border-slate-800/60 bg-slate-900/55 px-4 py-3">
          <p className="text-xs text-slate-500 mb-1">
            {t('smartDevices.stats.total', 'Total Devices')}
          </p>
          <p className="text-2xl font-semibold text-white">{devices.length}</p>
        </div>

        {/* Online */}
        <div className="rounded-xl border border-slate-800/60 bg-slate-900/55 px-4 py-3">
          <p className="text-xs text-slate-500 mb-1">
            {t('smartDevices.stats.online', 'Online')}
          </p>
          <p className="text-2xl font-semibold text-emerald-400">{onlineCount}</p>
        </div>

        {/* Offline */}
        <div className="rounded-xl border border-slate-800/60 bg-slate-900/55 px-4 py-3">
          <p className="text-xs text-slate-500 mb-1">
            {t('smartDevices.stats.offline', 'Offline')}
          </p>
          <p className="text-2xl font-semibold text-rose-400">
            {devices.length - onlineCount}
          </p>
        </div>

        {/* Power */}
        <div className="rounded-xl border border-slate-800/60 bg-slate-900/55 px-4 py-3">
          <div className="flex items-center gap-1 text-xs text-slate-500 mb-1">
            <Zap className="h-3.5 w-3.5 text-amber-400" />
            {t('smartDevices.stats.totalPower', 'Total Power')}
          </div>
          <p className="text-2xl font-semibold text-amber-400">
            {powerSummary != null ? `${powerSummary.total_watts.toFixed(1)} W` : '— W'}
          </p>
        </div>
      </div>

      {/* Device grid or empty state */}
      {devices.length === 0 ? (
        <div className="rounded-xl border border-slate-800/60 bg-slate-900/55 py-16 text-center">
          <Cpu className="h-12 w-12 mx-auto text-slate-600 mb-4" />
          <h3 className="text-lg font-medium text-slate-300 mb-2">
            {t('smartDevices.empty.title', 'No smart devices configured')}
          </h3>
          <p className="text-sm text-slate-500 max-w-xs mx-auto">
            {t(
              'smartDevices.empty.description',
              'Add your first IoT device to control it from here. Make sure the relevant plugin (e.g. Tapo) is enabled.'
            )}
          </p>
          {isAdmin && (
            <button
              onClick={() => setShowAddModal(true)}
              className="mt-6 inline-flex items-center gap-2 rounded-lg border border-sky-500/40 bg-sky-500/10 px-4 py-2 text-sm font-medium text-sky-300 hover:border-sky-500/60 hover:bg-sky-500/20 transition touch-manipulation active:scale-95"
            >
              <Plus className="h-4 w-4" />
              {t('smartDevices.addDevice', 'Add Device')}
            </button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {devices.map((device) => (
            <SmartDeviceCard
              key={device.id}
              device={device}
              isAdmin={isAdmin}
              onDelete={handleDelete}
              onStateChange={handleStateChange}
            />
          ))}
        </div>
      )}

      {/* Add Device Modal */}
      <AddDeviceModal
        isOpen={showAddModal}
        onClose={() => setShowAddModal(false)}
        onCreated={loadAll}
      />
    </div>
  );
}
