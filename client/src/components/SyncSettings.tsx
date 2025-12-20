import { useState, useEffect } from 'react';
import { Clock, Smartphone, HardDrive, Calendar, Settings, Plus, Trash2, CheckCircle, AlertTriangle } from 'lucide-react';

interface SyncDevice {
  device_id: string;
  device_name: string;
  status: string;
  last_sync: string;
  pending_changes: number;
  conflicts: number;
  // VPN related (optional)
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
  next_run_at: string | null;
  last_run_at: string | null;
}

interface SelectiveFolder {
  path: string;
  enabled: boolean;
  include_subfolders: boolean;
}

export default function SyncSettings() {
  const [devices, setDevices] = useState<SyncDevice[]>([]);
  const [schedules, setSchedules] = useState<SyncSchedule[]>([]);
  const [selectedDevice, setSelectedDevice] = useState<string>('');
  const [selectiveFolders, setSelectiveFolders] = useState<SelectiveFolder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // New device registration
  const [newDeviceId, setNewDeviceId] = useState('');
  const [newDeviceName, setNewDeviceName] = useState('');

  // New schedule
  const [scheduleType, setScheduleType] = useState('daily');
  const [scheduleTime, setScheduleTime] = useState('02:00');
  const [syncDeletions, setSyncDeletions] = useState(true);
  const [resolveConflicts, setResolveConflicts] = useState('keep_newest');

  // Bandwidth
  const [uploadLimit, setUploadLimit] = useState<number | null>(null);
  const [downloadLimit, setDownloadLimit] = useState<number | null>(null);

  useEffect(() => {
    loadSyncData();

    // Check for recently generated mobile token that may include VPN config
    try {
      const last = localStorage.getItem('lastMobileToken');
      if (last) {
        const parsed = JSON.parse(last);
        // If token includes VPN config, prefill registration fields
        if (parsed?.vpn_config || parsed?.vpn_config_base64 || parsed?.include_vpn) {
          if (!newDeviceName && parsed.device_name) {
            setNewDeviceName(parsed.device_name);
          }
          if (!newDeviceId && parsed.device_name) {
            // generate a sensible default device id from name
            const slug = String(parsed.device_name).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '').slice(0,30);
            setNewDeviceId(`${slug}-mobile`);
          }
        }
        // remove after use to avoid repeated autofill
        localStorage.removeItem('lastMobileToken');
      }
    } catch (e) {
      console.warn('Failed to read lastMobileToken', e);
    }
  }, []);

  async function loadSyncData() {
    setLoading(true);
    try {
      // Load schedules
      const token = localStorage.getItem('token');
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

      // Load registered devices (including VPN info when available)
      try {
        const devRes = await fetch('/api/sync/devices', { headers: { 'Authorization': `Bearer ${token}` } });
        if (devRes.ok) {
          const devData = await devRes.json();
          // backend may return array or { devices: [...] }
          const list = Array.isArray(devData) ? devData : (devData.devices || []);
          setDevices(list.map((d: any) => ({
            device_id: d.device_id ?? d.id ?? d.name,
            device_name: d.device_name ?? d.name ?? d.device_name,
            status: d.status ?? 'unknown',
            last_sync: d.last_sync ?? d.last_seen ?? null,
            pending_changes: d.pending_changes ?? 0,
            conflicts: d.conflicts ?? 0,
            vpn_client_id: d.vpn_client_id ?? d.vpn?.id ?? d.vpn_client_id ?? null,
            vpn_assigned_ip: d.vpn_assigned_ip ?? d.vpn?.assigned_ip ?? null,
            vpn_last_handshake: d.vpn_last_handshake ?? d.vpn?.last_handshake ?? null,
            vpn_active: d.vpn_active ?? d.vpn?.is_active ?? null,
          })));
        }
      } catch (e) {
        // non-fatal
        console.warn('Failed to load devices', e);
      }
    } catch (err: any) {
      setError('Failed to load sync settings');
    } finally {
      setLoading(false);
    }
  }

  async function registerDevice() {
    if (!newDeviceId || !newDeviceName) return;
    
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/sync/register', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          device_id: newDeviceId,
          device_name: newDeviceName
        })
      });
      
      if (!res.ok) throw new Error('Failed to register device');
      
      setSuccess(`Device "${newDeviceName}" registered successfully`);
      setNewDeviceId('');
      setNewDeviceName('');
    } catch (err: any) {
      setError(err.message);
    }
  }

  async function createSchedule() {
    if (!selectedDevice) {
      setError('Please select a device first');
      return;
    }

    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/sync/schedule/create', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          device_id: selectedDevice,
          schedule_type: scheduleType,
          time_of_day: scheduleTime,
          sync_deletions: syncDeletions,
          resolve_conflicts: resolveConflicts
        })
      });

      if (!res.ok) throw new Error('Failed to create schedule');

      setSuccess('Schedule created successfully');
      await loadSyncData();
    } catch (err: any) {
      setError(err.message);
    }
  }

  async function disableSchedule(scheduleId: number) {
    try {
      const token = localStorage.getItem('token');
      await fetch(`/api/sync/schedule/${scheduleId}/disable`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });

      setSuccess('Schedule disabled');
      await loadSyncData();
    } catch (err: any) {
      setError('Failed to disable schedule');
    }
  }

  async function saveBandwidthLimits() {
    try {
      const token = localStorage.getItem('token');
      await fetch('/api/sync/bandwidth/limit', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          upload_speed_limit: uploadLimit,
          download_speed_limit: downloadLimit
        })
      });

      setSuccess('Bandwidth limits saved');
    } catch (err: any) {
      setError('Failed to save limits');
    }
  }

  async function revokeVpnClient(clientId: number) {
    if (!clientId) return;
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/vpn/clients/${clientId}/revoke`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (!res.ok) throw new Error('Failed to revoke VPN client');
      setSuccess('VPN access revoked');
      // refresh devices
      await loadSyncData();
    } catch (err: any) {
      setError(err?.message || 'Failed to revoke VPN client');
    }
  }

  function formatDate(date: string | null) {
    if (!date) return 'N/A';
    return new Date(date).toLocaleString('de-DE');
  }

  return (
    <div className="space-y-6 w-full">
      <div className="rounded-lg shadow bg-slate-900/55 p-6">
        <h2 className="text-2xl font-bold mb-4 flex items-center gap-2">
          <Settings className="w-6 h-6" />
          Sync Settings
        </h2>

        {error && (
          <div className="mb-4 p-4 bg-red-500/10 border border-red-500/20 rounded-lg flex items-center gap-2 text-red-400">
            <AlertTriangle className="w-5 h-5" />
            <span>{error}</span>
          </div>
        )}

        {success && (
          <div className="mb-4 p-4 bg-emerald-500/10 border border-emerald-500/20 rounded-lg flex items-center gap-2 text-emerald-400">
            <CheckCircle className="w-5 h-5" />
            <span>{success}</span>
          </div>
        )}

        {/* Device Registration */}
        <div className="mb-6">
          <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
            <Smartphone className="w-5 h-5" />
            Register Device
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <input
              type="text"
              placeholder="Device ID (e.g., laptop-123)"
              value={newDeviceId}
              onChange={(e) => setNewDeviceId(e.target.value)}
              className="px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100"
            />
            <input
              type="text"
              placeholder="Device Name (e.g., My Laptop)"
              value={newDeviceName}
              onChange={(e) => setNewDeviceName(e.target.value)}
              className="px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100"
            />
            <button
              onClick={registerDevice}
              className="px-4 py-2 bg-sky-500 hover:bg-sky-600 text-white rounded-lg flex items-center justify-center gap-2"
            >
              <Plus className="w-4 h-4" />
              Register
            </button>
          </div>
        </div>

        {/* Schedule Creation */}
        <div className="mb-6">
          <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
            <Calendar className="w-5 h-5" />
            Create Sync Schedule
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
            <input
              type="text"
              placeholder="Device ID"
              value={selectedDevice}
              onChange={(e) => setSelectedDevice(e.target.value)}
              className="px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100"
            />
            <select
              value={scheduleType}
              onChange={(e) => setScheduleType(e.target.value)}
              className="px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100"
            >
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
              <option value="monthly">Monthly</option>
            </select>
            <input
              type="time"
              value={scheduleTime}
              onChange={(e) => setScheduleTime(e.target.value)}
              className="px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100"
            />
            <button
              onClick={createSchedule}
              className="px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-white rounded-lg"
            >
              Create Schedule
            </button>
          </div>
        </div>

        {/* Bandwidth Limits */}
        <div className="mb-6">
          <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
            <HardDrive className="w-5 h-5" />
            Bandwidth Limits (bytes/sec)
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <input
              type="number"
              placeholder="Upload Limit"
              value={uploadLimit || ''}
              onChange={(e) => setUploadLimit(e.target.value ? parseInt(e.target.value) : null)}
              className="px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100"
            />
            <input
              type="number"
              placeholder="Download Limit"
              value={downloadLimit || ''}
              onChange={(e) => setDownloadLimit(e.target.value ? parseInt(e.target.value) : null)}
              className="px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100"
            />
            <button
              onClick={saveBandwidthLimits}
              className="px-4 py-2 bg-sky-500 hover:bg-sky-600 text-white rounded-lg"
            >
              Save Limits
            </button>
          </div>
        </div>

        {/* Active Schedules */}
        <div>
          <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
            <Clock className="w-5 h-5" />
            Active Schedules
          </h3>
          {schedules.length === 0 ? (
            <div className="text-slate-400 text-center py-8">
              No schedules configured
            </div>
          ) : (
            <div className="space-y-3">
              {schedules.map((schedule) => (
                <div
                  key={schedule.schedule_id}
                  className="p-4 bg-slate-800/50 border border-slate-700 rounded-lg flex items-center justify-between"
                >
                  <div className="flex-1">
                    <div className="flex items-center gap-3">
                      <span className="font-medium text-slate-200">{schedule.device_id}</span>
                      <span className="px-2 py-1 bg-sky-500/20 text-sky-400 text-xs rounded-full border border-sky-500/30">
                        {schedule.schedule_type}
                      </span>
                      <span className="text-sm text-slate-400">{schedule.time_of_day}</span>
                    </div>
                    <div className="text-xs text-slate-500 mt-1">
                      Next run: {formatDate(schedule.next_run_at)} | Last run: {formatDate(schedule.last_run_at)}
                    </div>
                  </div>
                  <button
                    onClick={() => disableSchedule(schedule.schedule_id)}
                    className="p-2 text-red-400 hover:bg-red-500/10 rounded-lg transition-colors"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

        {/* Registered Devices */}
        <div className="mb-6">
          <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
            <Smartphone className="w-5 h-5" />
            Registered Devices
          </h3>
          {devices.length === 0 ? (
            <div className="text-slate-400 text-center py-6">No devices registered</div>
          ) : (
            <div className="space-y-3">
              {devices.map((d) => (
                <div key={d.device_id} className="p-4 bg-slate-800/50 border border-slate-700 rounded-lg">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="font-medium text-slate-200">{d.device_name} <span className="text-xs text-slate-400 ml-2">({d.device_id})</span></div>
                      <div className="text-xs text-slate-500">Status: {d.status} | Last sync: {formatDate(d.last_sync)}</div>
                    </div>
                    <div className="text-right">
                      {d.vpn_client_id ? (
                        <div className="text-xs text-slate-300">
                          <div className="flex items-center gap-3">
                            <div>VPN: <span className="font-medium text-sky-300">{d.vpn_assigned_ip ?? `client ${d.vpn_client_id}`}</span></div>
                            <button
                              onClick={() => revokeVpnClient(d.vpn_client_id!)}
                              className="px-2 py-1 bg-rose-600 hover:bg-rose-700 text-white text-xs rounded"
                            >
                              Revoke VPN
                            </button>
                          </div>
                          <div className="text-xs text-slate-500">Last handshake: {d.vpn_last_handshake ? formatDate(d.vpn_last_handshake) : 'N/A'}</div>
                        </div>
                      ) : (
                        <div className="text-xs text-slate-400">No VPN configured</div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
    </div>
  );
}
