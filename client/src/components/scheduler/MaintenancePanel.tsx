import { useEffect, useState, useRef } from 'react';
import { getRaidStatus, triggerRaidScrub } from '../../api/raid';
import { fetchSmartStatus, getSmartMode, toggleSmartMode, runSmartTest } from '../../api/smart';
import { requestConfirmation, executeConfirmation } from '../../api/raid';
import { HardDrive, Activity, RefreshCw, Trash2 } from 'lucide-react';

function StatusBadge({ status }: { status?: string }) {
  const s = (status || '').toLowerCase();
  const className = s.includes('ok') || s === 'optimal' || s === 'active' || s === 'passed' || s === 'online'
    ? 'bg-emerald-600 text-white'
    : s.includes('degrad') || s.includes('warning') || s === 'idle' || s === 'info'
    ? 'bg-amber-500 text-slate-900'
    : 'bg-red-600 text-white';

  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${className}`}>
      {status ?? 'unknown'}
    </span>
  );
}

function ProgressBar({ value }: { value?: number | null }) {
  const pct = value == null ? 0 : Math.max(0, Math.min(100, Math.round(value * 100)));
  return (
    <div className="mt-2 w-full rounded bg-slate-800/60">
      <div className="h-2 rounded bg-sky-500" style={{ width: `${pct}%` }} />
    </div>
  );
}

interface MaintenancePanelProps {
  addToast: (message: string, type: 'success' | 'error' | 'info') => void;
}

export function MaintenancePanel({ addToast }: MaintenancePanelProps) {
  const [raid, setRaid] = useState<any>(null);
  const [smart, setSmart] = useState<any>(null);
  const [selectedDevice, setSelectedDevice] = useState<string | null>(null);
  const [smartMode, setSmartMode] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [confirmModal, setConfirmModal] = useState<{
    visible: boolean;
    token?: string;
    expires_at?: number;
    action?: string;
    payload?: any;
    loading?: boolean;
  }>({ visible: false });
  const confirmButtonRef = useRef<HTMLButtonElement | null>(null);

  const load = async () => {
    try {
      const [r, s, m] = await Promise.all([getRaidStatus(), fetchSmartStatus(), getSmartMode()]);
      setRaid(r);
      setSmart(s);
      setSelectedDevice(s?.devices?.[0]?.name ?? null);
      setSmartMode(m);
    } catch (err: any) {
      addToast(err?.message || 'Failed to load data', 'error');
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleRaidScrub = async () => {
    setBusy(true);
    try {
      const res = await triggerRaidScrub();
      addToast(res.message || 'Scrub started', 'success');
      await load();
    } catch (err: any) {
      addToast(err?.message || 'Scrub failed', 'error');
    } finally {
      setBusy(false);
    }
  };

  const requestDeleteArray = async (arrayName: string) => {
    setBusy(true);
    try {
      const res = await requestConfirmation('delete_array', { array: arrayName, force: false });
      setConfirmModal({
        visible: true,
        token: res.token,
        expires_at: res.expires_at,
        action: 'delete_array',
        payload: { array: arrayName },
      });
      addToast('Confirmation token created. Confirm to execute.', 'info');
    } catch (err: any) {
      addToast(err?.message || 'Failed to request confirmation', 'error');
    } finally {
      setBusy(false);
    }
  };

  const executeToken = async () => {
    if (!confirmModal.token) return;
    setConfirmModal((s) => ({ ...s, loading: true }));
    try {
      const resp = await executeConfirmation(confirmModal.token!);
      addToast(resp.message || 'Action executed', 'success');
      setConfirmModal({ visible: false });
      await load();
    } catch (err: any) {
      addToast(err?.message || 'Execution failed', 'error');
      setConfirmModal({ visible: false });
    }
  };

  // Accessibility: focus management & keyboard handling for modal
  useEffect(() => {
    if (confirmModal.visible) {
      setTimeout(() => confirmButtonRef.current?.focus(), 0);

      const onKey = (e: KeyboardEvent) => {
        if (e.key === 'Escape') {
          setConfirmModal({ visible: false });
        }
      };

      document.addEventListener('keydown', onKey);
      return () => document.removeEventListener('keydown', onKey);
    }
  }, [confirmModal.visible]);

  const handleSmartTest = async () => {
    setBusy(true);
    try {
      const device = selectedDevice || smart?.devices?.[0]?.name;
      if (!device) throw new Error('No device selected for SMART test');
      const res = await runSmartTest({ device, type: 'short' });
      addToast(res.message || 'SMART test started', 'success');
      await load();
    } catch (err: any) {
      addToast(err?.message || 'SMART test failed', 'error');
    } finally {
      setBusy(false);
    }
  };

  const handleToggleSmart = async () => {
    setBusy(true);
    try {
      const res = await toggleSmartMode();
      setSmartMode(res);
      addToast(res.message || `SMART mode: ${res.mode}`, 'success');
    } catch (err: any) {
      addToast(err?.message || 'Toggle failed', 'error');
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      {/* Action buttons */}
      <div className="flex flex-wrap gap-2 mb-6">
        <button
          onClick={handleRaidScrub}
          disabled={busy}
          className="inline-flex items-center gap-2 min-h-[44px] rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50 transition-colors"
        >
          <HardDrive className="h-4 w-4" />
          Trigger RAID Scrub
        </button>
        <button
          onClick={handleSmartTest}
          disabled={busy}
          className="inline-flex items-center gap-2 min-h-[44px] rounded-md bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-700 disabled:opacity-50 transition-colors"
        >
          <Activity className="h-4 w-4" />
          Run SMART Short
        </button>
        <button
          onClick={handleToggleSmart}
          disabled={busy}
          className="inline-flex items-center gap-2 min-h-[44px] rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-700 disabled:opacity-50 transition-colors"
        >
          <RefreshCw className="h-4 w-4" />
          Toggle SMART Mode
        </button>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* RAID Status */}
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
          <h3 className="text-lg font-medium text-white flex items-center gap-2">
            <HardDrive className="h-5 w-5" />
            RAID Status
          </h3>
          <div className="mt-4 space-y-4">
            {raid?.arrays?.length ? (
              raid.arrays.map((a: any) => (
                <div key={a.name} className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                    <div>
                      <div className="text-sm font-medium text-white">
                        {a.name} <span className="text-xs text-slate-400">({a.level})</span>
                      </div>
                      <div className="text-xs text-slate-400">
                        Size: {a.size_bytes ? Math.round(a.size_bytes / (1024 * 1024 * 1024)) + ' GB' : 'n/a'}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <StatusBadge status={a.status || a.sync_action} />
                      <button
                        onClick={() => requestDeleteArray(a.name)}
                        disabled={busy}
                        className="inline-flex items-center gap-1 rounded-md bg-red-600 px-2 py-1 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-50 transition-colors"
                      >
                        <Trash2 className="h-3 w-3" />
                        Delete
                      </button>
                    </div>
                  </div>

                  {a.resync_progress != null && (
                    <div className="mt-3">
                      <div className="text-xs text-slate-400">Resync Progress</div>
                      <ProgressBar value={a.resync_progress} />
                      <div className="mt-1 text-xs text-slate-400">
                        {Math.round((a.resync_progress || 0) * 100)}%
                      </div>
                    </div>
                  )}

                  <div className="mt-3 text-xs">
                    <div className="text-slate-400 mb-1">Devices</div>
                    <div className="flex flex-wrap gap-2">
                      {a.devices?.map((d: any) => (
                        <div
                          key={d.name}
                          className="rounded-md border border-slate-800 bg-slate-900/60 px-2 py-1 text-xs"
                        >
                          {d.name}{' '}
                          <span className="text-[10px] text-slate-400">{d.state}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div className="text-sm text-slate-400">No arrays detected.</div>
            )}
          </div>
        </div>

        {/* SMART Status */}
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
          <h3 className="text-lg font-medium text-white flex items-center gap-2">
            <Activity className="h-5 w-5" />
            SMART Status
          </h3>
          <div className="mt-4 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <label className="text-xs text-slate-400">Device:</label>
                <select
                  value={selectedDevice ?? ''}
                  onChange={(e) => setSelectedDevice(e.target.value || null)}
                  className="rounded-md border border-slate-700 bg-slate-800 px-2 py-1 text-sm text-white"
                >
                  {(smart?.devices ?? []).map((d: any) => (
                    <option key={d.name} value={d.name}>
                      {d.name}
                      {d.model ? ` - ${d.model}` : ''}
                    </option>
                  ))}
                </select>
              </div>
              <div className="text-xs text-slate-400">
                Mode: <span className="text-slate-100">{smartMode?.mode ?? 'unknown'}</span>
              </div>
            </div>

            {smart?.devices?.length ? (
              smart.devices.map((dev: any) => (
                <div key={dev.name} className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="text-sm font-medium text-white">{dev.model ?? dev.name}</div>
                      <div className="text-xs text-slate-400">
                        {dev.name} {dev.serial ? `- ${dev.serial}` : ''}
                      </div>
                    </div>
                    <div className="flex flex-col items-end gap-2">
                      <div className="text-xs">
                        Temp: <span className="font-medium">{dev.temperature ?? 'n/a'}</span>
                        {dev.temperature ? 'C' : ''}
                      </div>
                      <StatusBadge status={dev.status} />
                    </div>
                  </div>
                  <div className="mt-3 text-xs text-slate-400">
                    Attributes: {dev.attributes?.length ?? 0}
                  </div>
                </div>
              ))
            ) : (
              <div className="text-sm text-slate-400">No SMART devices found.</div>
            )}
          </div>
        </div>
      </div>

      {/* Confirmation Modal */}
      {confirmModal.visible && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div
            className="absolute inset-0 bg-black/60"
            onClick={() => setConfirmModal({ visible: false })}
          />
          <div
            className="relative z-10 w-full max-w-lg rounded-lg bg-slate-900 p-6 shadow-lg"
            role="dialog"
            aria-modal="true"
          >
            <h3 className="text-lg font-medium text-white">Confirm {confirmModal.action}</h3>
            <p className="mt-2 text-sm text-slate-400">
              A one-time confirmation token was created. Click Confirm to execute the action now.
            </p>
            <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/40 p-3">
              <div className="text-xs text-slate-400">Token</div>
              <div className="mt-1 font-mono text-sm break-all text-slate-100">
                {confirmModal.token}
              </div>
              <div className="mt-2 text-xs text-slate-400">
                Expires at:{' '}
                {confirmModal.expires_at
                  ? new Date(confirmModal.expires_at * 1000).toLocaleString()
                  : 'n/a'}
              </div>
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <button
                onClick={() => setConfirmModal({ visible: false })}
                className="rounded-md px-4 py-2 text-sm text-slate-300 hover:bg-slate-800 transition-colors"
              >
                Cancel
              </button>
              <button
                ref={confirmButtonRef}
                onClick={executeToken}
                disabled={confirmModal.loading}
                className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50 transition-colors"
              >
                Confirm Execute
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
