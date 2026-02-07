/**
 * Fan Control Page
 *
 * Manages PWM fan control with manual and automatic modes
 */
import { useState, useMemo, useCallback, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Fan, Settings, AlertTriangle } from 'lucide-react';
import toast from 'react-hot-toast';
import { extractErrorMessage } from '../lib/api';
import { LoadingOverlay } from '../components/ui/Spinner';
import { setFanMode, setFanPWM, updateFanCurve, switchBackend, FanMode } from '../api/fan-control';
import type { FanCurvePoint } from '../api/fan-control';
import { useFanControl } from '../hooks/useFanControl';
import { FanCard, FanDetails } from '../components/fan-control';

export default function FanControl() {
  const { t } = useTranslation(['system', 'common']);
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
      toast.success(t('system:fanControl.messages.modeChanged', { mode }));
      refetch();
    } catch (error: any) {
      const message = error.response?.data?.detail || error.message || t('system:fanControl.messages.modeChangeFailed');
      toast.error(message);
    } finally {
      setOperationLoading(prev => ({ ...prev, [opKey]: false }));
    }
  }, [refetch, t]);

  const handlePWMChange = useCallback(async (fanId: string, pwm: number) => {
    try {
      await setFanPWM(fanId, pwm);
      toast.success(t('system:fanControl.messages.pwmSet', { pwm }));
      refetch();
    } catch (error: any) {
      const message = error.response?.data?.detail || error.message || t('system:fanControl.messages.pwmFailed');
      toast.error(message);
    }
  }, [refetch, t]);

  const handleCurveUpdate = useCallback(async (fanId: string, points: FanCurvePoint[]) => {
    try {
      await updateFanCurve(fanId, points);
      toast.success(t('system:fanControl.messages.curveUpdated'));
      refetch();
    } catch (error: any) {
      toast.error(extractErrorMessage(error.response?.data?.detail, t('system:fanControl.messages.curveFailed')));
    }
  }, [refetch, t]);

  const handleBackendSwitch = useCallback(async (useLinux: boolean) => {
    try {
      const result = await switchBackend(useLinux);
      if (result.success) {
        toast.success(result.message || t('system:fanControl.messages.backendSwitched'));
        refetch();
      } else {
        toast.error(result.message || t('system:fanControl.messages.backendFailed'));
      }
    } catch (error: any) {
      toast.error(extractErrorMessage(error.response?.data?.detail, t('system:fanControl.messages.backendFailed')));
    }
  }, [refetch, t]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <LoadingOverlay label={t('system:fanControl.loading')} />
      </div>
    );
  }

  if (!status || !status.fans) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-red-500">{t('system:fanControl.loadError')}</div>
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
            {t('system:fanControl.title')}
          </h1>
          <p className="mt-1 text-xs sm:text-sm text-slate-400">
            {t('system:fanControl.subtitleLong')}
          </p>
        </div>
        <div className="flex items-center gap-2 rounded-full border border-slate-800 bg-slate-900/60 px-4 py-2 text-xs text-slate-400 shadow-inner">
          <span className="inline-flex h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
          {t('system:fanControl.liveMonitoring')}
        </div>
      </div>

      {/* Status Badges */}
      <div className="mb-6 flex flex-wrap gap-3">
        {status.is_dev_mode && (
          <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-xs sm:text-sm font-medium text-amber-300">
            {t('system:fanControl.badges.devMode')}
          </span>
        )}
        {status.is_using_linux_backend ? (
          <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs sm:text-sm font-medium text-emerald-300">
            {t('system:fanControl.badges.linuxBackend')}
          </span>
        ) : (
          <span className="rounded-full border border-sky-500/30 bg-sky-500/10 px-3 py-1 text-xs sm:text-sm font-medium text-sky-300">
            {t('system:fanControl.badges.simulationBackend')}
          </span>
        )}
        {permissionStatus?.status === 'readonly' && (
          <span className="rounded-full border border-orange-500/30 bg-orange-500/10 px-3 py-1 text-xs sm:text-sm font-medium text-orange-300 flex items-center gap-1">
            <AlertTriangle className="w-4 h-4" />
            {t('system:fanControl.badges.readOnly')}
          </span>
        )}
      </div>

      {/* Permission Warning */}
      {permissionStatus?.status === 'readonly' && (
        <div className="mb-6 rounded-xl border border-orange-500/30 bg-orange-500/10 px-4 py-3 text-sm">
          <h3 className="font-semibold text-orange-200 mb-2">{t('system:fanControl.permissions.limitedTitle')}</h3>
          <p className="text-sm text-orange-300 mb-3">{permissionStatus.message}</p>
          {permissionStatus.suggestions.length > 0 && (
            <div className="text-sm text-orange-300">
              <p className="font-medium mb-1">{t('system:fanControl.permissions.suggestions')}</p>
              <ul className="list-disc list-inside space-y-1">
                {permissionStatus.suggestions.map((s, i) => (
                  <li key={i} className="font-mono text-xs">{s}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Backend Switch (Dev mode only) */}
      {status.is_dev_mode && (
        <div className="card mb-6 border-slate-800/50 bg-slate-900/55">
          <div className="flex items-start gap-3 mb-4">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-950/70 border border-slate-800/40">
              <Settings className="h-5 w-5 text-slate-400" />
            </div>
            <div className="flex-1">
              <h3 className="text-base sm:text-lg font-semibold text-white">{t('system:fanControl.backend.title')}</h3>
              <p className="text-xs sm:text-sm text-slate-400 mt-1">
                {t('system:fanControl.backend.description')}
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
              {t('system:fanControl.backend.useSimulation')}
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
              {t('system:fanControl.backend.useLinux')}
            </button>
          </div>
        </div>
      )}

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
          <p className="text-slate-300">{t('system:fanControl.noFansDetected')}</p>
          <p className="text-sm text-slate-400 mt-2">
            {t('system:fanControl.noFansHint')}
          </p>
        </div>
      )}
    </div>
  );
}
