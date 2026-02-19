/**
 * Sleep Mode Panel - Main control panel for sleep mode.
 *
 * Shows current state, activity metrics, idle progress, and manual controls
 * for entering/exiting soft sleep and triggering suspend/WoL.
 */

import { useState, useEffect, useCallback } from 'react';
import toast from 'react-hot-toast';
import { Moon, Sun, Power, Wifi, Activity, Cpu, HardDrive, Upload, Globe } from 'lucide-react';
import { useConfirmDialog } from '../../hooks/useConfirmDialog';
import {
  getSleepStatus,
  enterSoftSleep,
  exitSoftSleep,
  enterSuspend,
  sendWol,
  SLEEP_STATE_INFO,
  type SleepStatusResponse,
} from '../../api/sleep';

interface SleepModePanelProps {
  onRefresh?: () => void;
}

export function SleepModePanel({ onRefresh }: SleepModePanelProps) {
  const [status, setStatus] = useState<SleepStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const { confirm, dialog } = useConfirmDialog();

  const fetchStatus = useCallback(async () => {
    try {
      const data = await getSleepStatus();
      setStatus(data);
    } catch {
      // Silent fail for polling
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    // Poll: 5s when awake, 30s when sleeping (to avoid auto-wake)
    const isSleeping = status?.current_state === 'soft_sleep';
    const interval = setInterval(fetchStatus, isSleeping ? 30000 : 5000);
    return () => clearInterval(interval);
  }, [fetchStatus, status?.current_state]);

  const handleEnterSleep = async () => {
    if (busy) return;
    const ok = await confirm('Enter soft sleep mode? Services will be paused and disks spun down.', {
      title: 'Enter Soft Sleep',
      variant: 'warning',
      confirmLabel: 'Enter Sleep',
    });
    if (!ok) return;

    setBusy(true);
    try {
      await enterSoftSleep();
      toast.success('Entered soft sleep mode');
      await fetchStatus();
      onRefresh?.();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to enter sleep');
    } finally {
      setBusy(false);
    }
  };

  const handleWake = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await exitSoftSleep();
      toast.success('System waking up');
      await fetchStatus();
      onRefresh?.();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to wake');
    } finally {
      setBusy(false);
    }
  };

  const handleSuspend = async () => {
    if (busy) return;
    const ok = await confirm(
      'Suspend the system? The server will become unreachable. Wake via WoL or RTC alarm.',
      {
        title: 'True Suspend',
        variant: 'danger',
        confirmLabel: 'Suspend Now',
      },
    );
    if (!ok) return;

    setBusy(true);
    try {
      await enterSuspend();
      toast.success('System suspending...');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to suspend');
    } finally {
      setBusy(false);
    }
  };

  const handleWol = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await sendWol();
      toast.success('WoL packet sent');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to send WoL');
    } finally {
      setBusy(false);
    }
  };

  if (loading || !status) {
    return (
      <div className="card border-slate-700/50 p-6">
        <div className="animate-pulse space-y-4">
          <div className="h-6 bg-slate-700/50 rounded w-1/3" />
          <div className="h-20 bg-slate-700/50 rounded" />
        </div>
      </div>
    );
  }

  const stateInfo = SLEEP_STATE_INFO[status.current_state];
  const isAwake = status.current_state === 'awake';
  const isSleeping = status.current_state === 'soft_sleep';
  const isTransitioning = ['entering_soft_sleep', 'entering_suspend', 'waking'].includes(status.current_state);
  const idleProgress = status.idle_threshold_seconds > 0
    ? Math.min(100, (status.idle_seconds / status.idle_threshold_seconds) * 100)
    : 0;

  return (
    <>
      {dialog}
      <div className="space-y-4">
        {/* State Card */}
        <div className="card border-slate-700/50 p-4 sm:p-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <div className={`p-2 rounded-lg ${stateInfo.bgColor}`}>
                {isSleeping ? (
                  <Moon className={`h-5 w-5 ${stateInfo.color}`} />
                ) : (
                  <Sun className={`h-5 w-5 ${stateInfo.color}`} />
                )}
              </div>
              <div>
                <h3 className="text-sm font-medium text-white">Sleep Mode</h3>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${stateInfo.bgColor} ${stateInfo.color}`}>
                    {stateInfo.label}
                  </span>
                  {status.state_since && (
                    <span className="text-[10px] text-slate-500">
                      since {new Date(status.state_since).toLocaleTimeString()}
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* Action Buttons */}
            <div className="flex items-center gap-2">
              {isAwake && (
                <button
                  onClick={handleEnterSleep}
                  disabled={busy || isTransitioning}
                  className="flex items-center gap-1.5 rounded-lg bg-blue-500/20 px-3 py-2 text-sm font-medium text-blue-300 hover:bg-blue-500/30 transition-colors disabled:opacity-50"
                >
                  <Moon className="h-4 w-4" />
                  <span className="hidden sm:inline">Sleep</span>
                </button>
              )}
              {isSleeping && (
                <button
                  onClick={handleWake}
                  disabled={busy || isTransitioning}
                  className="flex items-center gap-1.5 rounded-lg bg-emerald-500/20 px-3 py-2 text-sm font-medium text-emerald-300 hover:bg-emerald-500/30 transition-colors disabled:opacity-50"
                >
                  <Sun className="h-4 w-4" />
                  <span className="hidden sm:inline">Wake</span>
                </button>
              )}
              <button
                onClick={handleSuspend}
                disabled={busy || isTransitioning || status.current_state === 'true_suspend'}
                className="flex items-center gap-1.5 rounded-lg bg-purple-500/20 px-3 py-2 text-sm font-medium text-purple-300 hover:bg-purple-500/30 transition-colors disabled:opacity-50"
                title="True Suspend (systemctl suspend)"
              >
                <Power className="h-4 w-4" />
                <span className="hidden sm:inline">Suspend</span>
              </button>
              <button
                onClick={handleWol}
                disabled={busy}
                className="flex items-center gap-1.5 rounded-lg bg-amber-500/20 px-3 py-2 text-sm font-medium text-amber-300 hover:bg-amber-500/30 transition-colors disabled:opacity-50"
                title="Send Wake-on-LAN packet"
              >
                <Wifi className="h-4 w-4" />
                <span className="hidden sm:inline">WoL</span>
              </button>
            </div>
          </div>

          {/* Idle Progress */}
          {isAwake && status.auto_idle_enabled && status.idle_threshold_seconds > 0 && (
            <div className="border-t border-slate-700/50 pt-3 mt-3">
              <div className="flex items-center justify-between text-xs text-slate-400 mb-1.5">
                <span>Idle Progress</span>
                <span>
                  {Math.round(status.idle_seconds)}s / {Math.round(status.idle_threshold_seconds)}s
                </span>
              </div>
              <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-blue-500/60 rounded-full transition-all duration-1000"
                  style={{ width: `${idleProgress}%` }}
                />
              </div>
            </div>
          )}

          {/* Paused services / spun-down disks when sleeping */}
          {isSleeping && (
            <div className="border-t border-slate-700/50 pt-3 mt-3 space-y-2">
              {status.paused_services.length > 0 && (
                <div className="flex items-center gap-2 text-xs text-slate-400">
                  <Activity className="h-3.5 w-3.5" />
                  <span>Paused: {status.paused_services.join(', ')}</span>
                </div>
              )}
              {status.spun_down_disks.length > 0 && (
                <div className="flex items-center gap-2 text-xs text-slate-400">
                  <HardDrive className="h-3.5 w-3.5" />
                  <span>Disks spun down: {status.spun_down_disks.join(', ')}</span>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Activity Metrics */}
        <div className="card border-slate-700/50 p-4 sm:p-6">
          <h4 className="text-sm font-medium text-white mb-3">Activity Metrics</h4>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <MetricCard
              icon={<Cpu className="h-4 w-4 text-blue-400" />}
              label="CPU"
              value={`${status.activity_metrics.cpu_usage_avg.toFixed(1)}%`}
            />
            <MetricCard
              icon={<HardDrive className="h-4 w-4 text-emerald-400" />}
              label="Disk I/O"
              value={`${status.activity_metrics.disk_io_avg_mbps.toFixed(2)} MB/s`}
            />
            <MetricCard
              icon={<Upload className="h-4 w-4 text-amber-400" />}
              label="Uploads"
              value={String(status.activity_metrics.active_uploads)}
            />
            <MetricCard
              icon={<Globe className="h-4 w-4 text-purple-400" />}
              label="HTTP/min"
              value={status.activity_metrics.http_requests_per_minute.toFixed(0)}
            />
          </div>
        </div>
      </div>
    </>
  );
}

function MetricCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="rounded-lg bg-slate-800/30 border border-slate-700/30 p-3">
      <div className="flex items-center gap-2 mb-1">
        {icon}
        <span className="text-[10px] text-slate-500 uppercase tracking-wider">{label}</span>
      </div>
      <div className="text-sm font-medium text-white">{value}</div>
    </div>
  );
}
