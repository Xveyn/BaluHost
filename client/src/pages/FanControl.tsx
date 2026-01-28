/**
 * Fan Control Page
 *
 * Manages PWM fan control with manual and automatic modes
 */
import { useState, useMemo, useCallback, useEffect } from 'react';
import { Fan, Settings, AlertTriangle } from 'lucide-react';
import toast from 'react-hot-toast';
import { setFanMode, setFanPWM, updateFanCurve, switchBackend, FanMode } from '../api/fan-control';
import type { FanCurvePoint } from '../api/fan-control';
import { useFanControl } from '../hooks/useFanControl';
import { FanCard, FanDetails } from '../components/fan-control';

export default function FanControl() {
  const [isEditingCurve, setIsEditingCurve] = useState(false);
  const { status, permissionStatus, loading, refetch, isReadOnly } = useFanControl({
    pauseRefresh: isEditingCurve, // Pause auto-refresh while editing curve
  });
  const [selectedFan, setSelectedFan] = useState<string | null>(null);
  const [operationLoading, setOperationLoading] = useState<Record<string, boolean>>({});

  // IMPORTANT: All hooks must be called before any conditional returns
  // Memoize selected fan data
  const selectedFanData = useMemo(() => {
    return status?.fans.find(f => f.fan_id === selectedFan);
  }, [status?.fans, selectedFan]);

  // Auto-select first fan if none selected
  useEffect(() => {
    if (!selectedFan && status?.fans && status.fans.length > 0) {
      setSelectedFan(status.fans[0].fan_id);
    }
  }, [status?.fans, selectedFan]);

  const handleModeChange = useCallback(async (fanId: string, mode: FanMode) => {
    const opKey = `mode-${fanId}`;
    try {
      setOperationLoading(prev => ({ ...prev, [opKey]: true }));
      await setFanMode(fanId, mode);
      toast.success(`Fan mode changed to ${mode}`);
      refetch();
    } catch (error: any) {
      const message = error.response?.data?.detail || error.message || 'Failed to change fan mode';
      toast.error(message);
    } finally {
      setOperationLoading(prev => ({ ...prev, [opKey]: false }));
    }
  }, [refetch]);

  const handlePWMChange = useCallback(async (fanId: string, pwm: number) => {
    try {
      await setFanPWM(fanId, pwm);
      toast.success(`PWM set to ${pwm}%`);
      refetch();
    } catch (error: any) {
      const message = error.response?.data?.detail || error.message || 'Failed to set PWM';
      toast.error(message);
    }
  }, [refetch]);

  const handleCurveUpdate = useCallback(async (fanId: string, points: FanCurvePoint[]) => {
    try {
      await updateFanCurve(fanId, points);
      toast.success('Fan curve updated');
      refetch();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to update curve');
    }
  }, [refetch]);

  const handleBackendSwitch = useCallback(async (useLinux: boolean) => {
    try {
      const result = await switchBackend(useLinux);
      if (result.success) {
        toast.success(result.message || 'Backend switched');
        refetch();
      } else {
        toast.error(result.message || 'Failed to switch backend');
      }
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to switch backend');
    }
  }, [refetch]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-center">
          <div className="inline-block h-12 w-12 sm:h-16 sm:w-16 animate-spin rounded-full border-4 border-slate-600 border-t-sky-500" />
          <p className="mt-4 text-sm sm:text-base text-slate-400">Loading fan control...</p>
        </div>
      </div>
    );
  }

  if (!status || !status.fans) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-red-500">Failed to load fan control - check console for details</div>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="mb-6 flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3 sm:gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-semibold text-white flex items-center gap-2">
            <Fan className="h-7 w-7 sm:h-8 sm:w-8" />
            Fan Control
          </h1>
          <p className="mt-1 text-xs sm:text-sm text-slate-400">
            PWM fan management with automatic temperature curves
          </p>
        </div>
        <div className="flex items-center gap-2 rounded-full border border-slate-800 bg-slate-900/60 px-4 py-2 text-xs text-slate-400 shadow-inner">
          <span className="inline-flex h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
          Live Monitoring
        </div>
      </div>

      {/* Status Badges */}
      <div className="mb-6 flex flex-wrap gap-3">
        {status.is_dev_mode && (
          <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-xs sm:text-sm font-medium text-amber-300">
            Dev Mode (Simulated)
          </span>
        )}
        {status.is_using_linux_backend ? (
          <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs sm:text-sm font-medium text-emerald-300">
            Linux Hardware Backend
          </span>
        ) : (
          <span className="rounded-full border border-sky-500/30 bg-sky-500/10 px-3 py-1 text-xs sm:text-sm font-medium text-sky-300">
            Simulation Backend
          </span>
        )}
        {permissionStatus?.status === 'readonly' && (
          <span className="rounded-full border border-orange-500/30 bg-orange-500/10 px-3 py-1 text-xs sm:text-sm font-medium text-orange-300 flex items-center gap-1">
            <AlertTriangle className="w-4 h-4" />
            Read-Only Mode
          </span>
        )}
      </div>

      {/* Permission Warning */}
      {permissionStatus?.status === 'readonly' && (
        <div className="mb-6 rounded-xl border border-orange-500/30 bg-orange-500/10 px-4 py-3 text-sm">
          <h3 className="font-semibold text-orange-200 mb-2">Limited Permissions</h3>
          <p className="text-sm text-orange-300 mb-3">{permissionStatus.message}</p>
          {permissionStatus.suggestions.length > 0 && (
            <div className="text-sm text-orange-300">
              <p className="font-medium mb-1">Suggestions:</p>
              <ul className="list-disc list-inside space-y-1">
                {permissionStatus.suggestions.map((s, i) => (
                  <li key={i} className="font-mono text-xs">{s}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Backend Switch (Always visible) */}
      <div className="card mb-6 border-slate-800/50 bg-slate-900/55">
        <div className="flex items-start gap-3 mb-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-950/70 border border-slate-800/40">
            <Settings className="h-5 w-5 text-slate-400" />
          </div>
          <div className="flex-1">
            <h3 className="text-base sm:text-lg font-semibold text-white">Backend Configuration</h3>
            <p className="text-xs sm:text-sm text-slate-400 mt-1">
              Switch between simulated fans and real hardware control
            </p>
          </div>
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => handleBackendSwitch(false)}
            disabled={!status.is_using_linux_backend}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              !status.is_using_linux_backend
                ? 'bg-sky-500 text-white shadow-lg shadow-sky-500/30'
                : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
            } disabled:opacity-50 disabled:cursor-not-allowed`}
          >
            Use Simulation
          </button>
          <button
            onClick={() => handleBackendSwitch(true)}
            disabled={status.is_using_linux_backend}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              status.is_using_linux_backend
                ? 'bg-emerald-500 text-white shadow-lg shadow-emerald-500/30'
                : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
            } disabled:opacity-50 disabled:cursor-not-allowed`}
          >
            Use Linux Hardware
          </button>
        </div>
      </div>

      {/* Fan Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
        {status.fans.map((fan) => (
          <FanCard
            key={fan.fan_id}
            fan={fan}
            isSelected={fan.fan_id === selectedFan}
            onSelect={() => setSelectedFan(fan.fan_id)}
            onModeChange={handleModeChange}
            onPWMChange={handlePWMChange}
            isReadOnly={isReadOnly}
            isLoading={operationLoading[`mode-${fan.fan_id}`] || false}
          />
        ))}
      </div>

      {/* Fan Details (if fan selected) */}
      {selectedFanData && (
        <div className="mt-6">
          <FanDetails
            fan={selectedFanData}
            onCurveUpdate={handleCurveUpdate}
            isReadOnly={isReadOnly}
            onEditingChange={setIsEditingCurve}
            onConfigUpdate={refetch}
          />
        </div>
      )}

      {/* No Fans Available */}
      {status.fans.length === 0 && (
        <div className="card text-center py-12">
          <Fan className="w-16 h-16 mx-auto text-slate-500 mb-4" />
          <p className="text-slate-300">No PWM fans detected</p>
          <p className="text-sm text-slate-400 mt-2">
            Ensure lm-sensors is installed and PWM fans are connected
          </p>
        </div>
      )}
    </div>
  );
}
