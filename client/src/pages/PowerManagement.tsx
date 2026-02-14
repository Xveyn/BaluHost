/**
 * Power Management Page
 *
 * Provides CPU frequency scaling controls with:
 * - Preset selection (Energy Saver / Balanced / Performance)
 * - Current power property display
 * - Active power demands list
 * - Profile change history
 * - Auto-scaling configuration
 * - Custom preset editor
 */

import { useEffect, useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { AlertTriangle } from 'lucide-react';
import { Spinner } from '../components/ui/Spinner';
import { StatCard } from '../components/ui/StatCard';
import { AdminBadge } from '../components/ui/AdminBadge';
import { PresetSelector } from '../components/power/PresetSelector';
import { PresetEditor } from '../components/power/PresetEditor';
import { PresetClockVisualization } from '../components/power/PresetClockVisualization';
import { ServiceIntensityList } from '../components/power/ServiceIntensityList';
import { DemandList } from '../components/power/DemandList';
import { HistoryTable } from '../components/power/HistoryTable';
import { DynamicModeSection } from '../components/power/DynamicModeSection';
import { getPresetIcon } from '../components/power/utils';
import {
  getPowerStatus,
  getPowerDemands,
  unregisterPowerDemand,
  getPowerMgmtHistory,
  getAutoScalingConfig,
  updateAutoScalingConfig,
  switchPowerBackend,
  getServiceIntensities,
  PROFILE_INFO,
  getDynamicModeConfig,
  listPresets,
  activatePreset,
  createPreset,
  updatePreset,
  deletePreset,
  formatClockSpeed,
  PROPERTY_INFO,
  type PowerStatusResponse,
  type PowerDemandInfo,
  type PowerHistoryEntry,
  type AutoScalingConfig,
  type ServicePowerProperty,
  type ServiceIntensityInfo,
  type PowerPreset,
  type CreatePresetRequest,
  type DynamicModeConfigResponse,
} from '../api/power-management';

const REFRESH_INTERVAL_MS = 5000;

interface PowerManagementProps {
  isAdmin: boolean;
}

// Main component
export default function PowerManagement({ isAdmin }: PowerManagementProps) {
  const { t } = useTranslation(['system', 'common']);
  const [status, setStatus] = useState<PowerStatusResponse | null>(null);
  const [presets, setPresets] = useState<PowerPreset[]>([]);
  const [demands, setDemands] = useState<PowerDemandInfo[]>([]);
  const [intensities, setIntensities] = useState<ServiceIntensityInfo[]>([]);
  const [history, setHistory] = useState<PowerHistoryEntry[]>([]);
  const [autoScaling, setAutoScaling] = useState<AutoScalingConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [dynamicConfig, setDynamicConfig] = useState<DynamicModeConfigResponse | null>(null);
  const [editorPreset, setEditorPreset] = useState<PowerPreset | null | 'new'>(null);
  const [editingAutoScaling, setEditingAutoScaling] = useState(false);
  const [editAutoScaling, setEditAutoScaling] = useState<AutoScalingConfig | null>(null);

  const loadData = useCallback(async (showSuccess = false) => {
    try {
      const [statusRes, presetsRes, demandsRes, intensitiesRes, historyRes, autoScalingRes, dynamicRes] = await Promise.all([
        getPowerStatus(),
        listPresets(),
        getPowerDemands(),
        getServiceIntensities(),
        getPowerMgmtHistory(50),
        getAutoScalingConfig(),
        getDynamicModeConfig(),
      ]);

      setStatus(statusRes);
      setPresets(presetsRes.presets);
      setDemands(demandsRes);
      setIntensities(intensitiesRes.services);
      setHistory(historyRes.entries);
      setAutoScaling(autoScalingRes.config);
      setDynamicConfig(dynamicRes);
      setError(null);
      setLastUpdated(new Date());

      if (showSuccess) {
        toast.success(t('system:power.toasts.statusUpdated'));
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : t('system:power.toasts.loadFailed');
      setError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void loadData();
    const interval = setInterval(() => void loadData(), REFRESH_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [loadData]);

  const handlePresetSelect = async (presetId: number) => {
    if (busy) return;

    setBusy(true);
    try {
      const result = await activatePreset(presetId);
      toast.success(result.message);
      await loadData();
    } catch (err) {
      const message = err instanceof Error ? err.message : t('system:power.toasts.presetActivateFailed');
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  const handleUnregisterDemand = async (source: string) => {
    if (busy) return;

    setBusy(true);
    try {
      await unregisterPowerDemand({ source });
      toast.success(t('system:power.toasts.demandRemoved'));
      await loadData();
    } catch (err) {
      const message = err instanceof Error ? err.message : t('system:power.toasts.demandRemoveFailed');
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  const handleToggleAutoScaling = async () => {
    if (!autoScaling || busy) return;

    setBusy(true);
    try {
      const newConfig = { ...autoScaling, enabled: !autoScaling.enabled };
      await updateAutoScalingConfig(newConfig);
      setAutoScaling(newConfig);
      toast.success(newConfig.enabled ? t('system:power.toasts.autoScalingEnabled') : t('system:power.toasts.autoScalingDisabled'));
    } catch (err) {
      const message = err instanceof Error ? err.message : t('system:power.toasts.settingChangeFailed');
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  const handleStartEditAutoScaling = () => {
    if (autoScaling) {
      setEditAutoScaling({ ...autoScaling });
      setEditingAutoScaling(true);
    }
  };

  const handleCancelEditAutoScaling = () => {
    setEditingAutoScaling(false);
    setEditAutoScaling(null);
  };

  const handleSaveAutoScaling = async () => {
    if (!editAutoScaling || busy) return;

    // Validate: surge > medium > low, all 0-100
    if (
      editAutoScaling.cpu_surge_threshold <= editAutoScaling.cpu_medium_threshold ||
      editAutoScaling.cpu_medium_threshold <= editAutoScaling.cpu_low_threshold ||
      editAutoScaling.cpu_surge_threshold < 0 || editAutoScaling.cpu_surge_threshold > 100 ||
      editAutoScaling.cpu_medium_threshold < 0 || editAutoScaling.cpu_medium_threshold > 100 ||
      editAutoScaling.cpu_low_threshold < 0 || editAutoScaling.cpu_low_threshold > 100 ||
      editAutoScaling.cooldown_seconds < 0
    ) {
      toast.error(t('system:power.autoScaling.validationError'));
      return;
    }

    setBusy(true);
    try {
      await updateAutoScalingConfig(editAutoScaling);
      setAutoScaling(editAutoScaling);
      setEditingAutoScaling(false);
      setEditAutoScaling(null);
      toast.success(t('system:power.autoScaling.thresholdsSaved'));
    } catch (err) {
      const message = err instanceof Error ? err.message : t('system:power.autoScaling.thresholdsSaveFailed');
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  const handleSwitchBackend = async () => {
    if (!status || busy) return;

    const useLinux = !status.is_using_linux_backend;

    setBusy(true);
    try {
      const result = await switchPowerBackend(useLinux);
      toast.success(result.message);
      await loadData();
    } catch (err) {
      const message = err instanceof Error ? err.message : t('system:power.toasts.backendSwitchFailed');
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  const handleSavePreset = async (data: CreatePresetRequest) => {
    setBusy(true);
    try {
      if (editorPreset === 'new') {
        await createPreset(data);
        toast.success(t('system:power.toasts.presetCreated'));
      } else if (editorPreset) {
        await updatePreset(editorPreset.id, data);
        toast.success(t('system:power.toasts.presetUpdated'));
      }
      setEditorPreset(null);
      await loadData();
    } catch (err) {
      const message = err instanceof Error ? err.message : t('system:power.toasts.saveFailed');
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  const handleDeletePreset = async () => {
    if (!editorPreset || editorPreset === 'new') return;

    setBusy(true);
    try {
      await deletePreset(editorPreset.id);
      toast.success(t('system:power.toasts.presetDeleted'));
      setEditorPreset(null);
      await loadData();
    } catch (err) {
      const message = err instanceof Error ? err.message : t('system:power.toasts.deleteFailed');
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-[400px] items-center justify-center">
        <Spinner size="lg" />
      </div>
    );
  }

  if (error && !status) {
    return (
      <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-6 text-center text-red-200">
        <p className="font-medium">{t('system:power.errors.loadingTitle')}</p>
        <p className="mt-1 text-sm">{error}</p>
        <button
          onClick={() => loadData(true)}
          className="mt-4 rounded bg-red-500/20 px-4 py-2 hover:bg-red-500/30"
        >
          {t('system:power.errors.retryButton')}
        </button>
      </div>
    );
  }

  const activePreset = presets.find(p => p.is_active);
  const currentProperty = status?.current_property || status?.current_profile as ServicePowerProperty;

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-semibold text-white">{t('system:power.title')}</h1>
          <p className="mt-1 text-xs sm:text-sm text-slate-400">{t('system:power.subtitle')}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2 sm:gap-3">
          {/* Backend indicator - only show in dev mode */}
          {status?.is_dev_mode && (
            status?.is_using_linux_backend ? (
              <span className="rounded-full bg-emerald-500/20 px-2 sm:px-3 py-1 text-xs sm:text-sm text-emerald-300">
                <span className="hidden sm:inline">{t('system:power.backend.linux')}</span>
                <span className="sm:hidden">{t('system:power.backend.linuxShort')}</span>
              </span>
            ) : (
              <span className="rounded-full bg-amber-500/20 px-2 sm:px-3 py-1 text-xs sm:text-sm text-amber-300">
                <span className="hidden sm:inline">{t('system:power.backend.dev')}</span>
                <span className="sm:hidden">{t('system:power.backend.devShort')}</span>
              </span>
            )
          )}
          {/* Backend switch button - only show in dev mode if can switch */}
          {status?.is_dev_mode && isAdmin && status?.can_switch_backend && (
            <button
              onClick={handleSwitchBackend}
              disabled={busy}
              className={`flex items-center gap-1.5 rounded-lg px-2.5 sm:px-3 py-1.5 text-xs sm:text-sm transition-colors touch-manipulation active:scale-95 min-h-[36px] ${
                status.is_using_linux_backend
                  ? 'bg-amber-500/20 text-amber-300 hover:bg-amber-500/30'
                  : 'bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30'
              }`}
              title={status.is_using_linux_backend ? t('system:power.backend.switchToDev') : t('system:power.backend.switchToLinux')}
            >
              {status.is_using_linux_backend ? '-> Dev' : '-> Linux'}
              <AdminBadge />
            </button>
          )}
          <button
            onClick={() => loadData(true)}
            disabled={busy}
            className="rounded-lg border border-slate-700 bg-slate-800 px-3 sm:px-4 py-2 text-xs sm:text-sm text-white hover:bg-slate-700 touch-manipulation active:scale-95 min-h-[36px]"
          >
            <span className="hidden sm:inline">{t('system:power.buttons.refresh')}</span>
            <span className="sm:hidden">&#x21bb;</span>
          </button>
        </div>
      </div>

      {/* Status Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label={t('system:power.statusCards.activePreset')}
          value={status?.dynamic_mode_enabled ? t('system:power.dynamicMode.title') : (activePreset?.name || '-')}
          subValue={status?.dynamic_mode_enabled ? status.target_frequency_range : activePreset?.description}
          color={status?.dynamic_mode_enabled ? 'teal' : activePreset?.name.includes('Performance') ? 'red' : activePreset?.name.includes('Energy') ? 'emerald' : 'blue'}
          icon={<span className="text-2xl">{status?.dynamic_mode_enabled ? '\u{26A1}' : activePreset ? getPresetIcon(activePreset.name) : '\u{26A1}'}</span>}
        />
        <StatCard
          label={t('system:power.statusCards.currentProperty')}
          value={currentProperty ? PROPERTY_INFO[currentProperty].name : '-'}
          subValue={status?.target_frequency_range}
          color={PROFILE_INFO[currentProperty || 'idle']?.color || 'slate'}
          icon={<span className="text-2xl">{currentProperty ? PROPERTY_INFO[currentProperty].icon : '⚡'}</span>}
        />
        <StatCard
          label={t('system:power.statusCards.cpuFrequency')}
          value={status?.current_frequency_mhz ? formatClockSpeed(status.current_frequency_mhz) : '-'}
          subValue={lastUpdated ? `${t('system:power.statusCards.updated')}: ${lastUpdated.toLocaleTimeString()}` : undefined}
          color="blue"
          icon={
            <svg className="h-6 w-6 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          }
        />
        <StatCard
          label={t('system:power.statusCards.activeDemands')}
          value={demands.length}
          subValue={demands.length > 0 ? `${t('system:power.statusCards.highest')}: ${PROPERTY_INFO[(demands.reduce((a, b) =>
            ['surge', 'medium', 'low', 'idle'].indexOf((a.power_property || a.level) as string) <
            ['surge', 'medium', 'low', 'idle'].indexOf((b.power_property || b.level) as string) ? a : b
          ).power_property || demands[0].level) as ServicePowerProperty].name}` : t('system:power.statusCards.none')}
          color="purple"
          icon={
            <svg className="h-6 w-6 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
          }
        />
      </div>

      {/* Dynamic Mode Section */}
      {dynamicConfig && (
        <DynamicModeSection
          config={dynamicConfig}
          isAdmin={isAdmin}
          busy={busy}
          onBusyChange={setBusy}
          onRefresh={() => void loadData()}
        />
      )}

      {/* Preset Selection */}
      <div className={`card border-slate-700/50 p-4 sm:p-6 ${status?.dynamic_mode_enabled ? 'opacity-50 pointer-events-none' : ''}`}>
        <div className="mb-3 sm:mb-4 flex flex-col sm:flex-row sm:items-center justify-between gap-2 sm:gap-4">
          <h2 className="text-base sm:text-lg font-medium text-white">{t('system:power.presetSection.selectPreset')}</h2>
          {isAdmin && (
            <div className="flex gap-2">
              <button
                onClick={() => setEditorPreset('new')}
                disabled={busy}
                className="rounded-lg px-3 py-2 text-xs sm:text-sm bg-slate-700 text-slate-300 hover:bg-slate-600 flex items-center gap-1"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                </svg>
                {t('system:power.buttons.customPreset')}
              </button>
              <button
                onClick={handleToggleAutoScaling}
                disabled={busy}
                className={`rounded-lg px-3 sm:px-4 py-2 text-xs sm:text-sm transition-colors touch-manipulation active:scale-95 min-h-[40px] ${
                  autoScaling?.enabled
                    ? 'bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30'
                    : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                }`}
              >
                {autoScaling?.enabled ? t('system:power.presetSection.autoScalingActive') : t('system:power.presetSection.autoScalingOff')}
              </button>
            </div>
          )}
        </div>
        <PresetSelector
          presets={presets}
          activePresetId={activePreset?.id}
          onSelect={handlePresetSelect}
          disabled={busy || !isAdmin}
          t={t}
        />
        {!isAdmin && (
          <p className="mt-3 text-sm text-slate-500">
            {t('system:power.presetSection.adminOnlyChange')}
          </p>
        )}
      </div>

      {/* Preset Details */}
      {activePreset && (
        <div className={`card border-slate-700/50 p-4 sm:p-6 ${status?.dynamic_mode_enabled ? 'opacity-50 pointer-events-none' : ''}`}>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-base sm:text-lg font-medium text-white">
              {t('system:power.presetSection.preset')}: {activePreset.name}
            </h2>
            {isAdmin && (
              <button
                onClick={() => setEditorPreset(activePreset)}
                className="text-xs text-slate-400 hover:text-white flex items-center gap-1"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                </svg>
                {t('system:power.buttons.edit')}
              </button>
            )}
          </div>
          <PresetClockVisualization preset={activePreset} currentProperty={currentProperty} t={t} />
        </div>
      )}

      {/* Service Intensity */}
      <div className="card border-slate-700/50 p-4 sm:p-6">
        <div className="mb-3 sm:mb-4 flex items-center justify-between">
          <h2 className="text-base sm:text-lg font-medium text-white">{t('system:power.serviceIntensity.title')}</h2>
          <span className="text-xs text-slate-400">
            {t('system:power.serviceIntensity.services', { count: intensities.length })}
          </span>
        </div>
        <ServiceIntensityList services={intensities} t={t} />
      </div>

      {/* Active Demands */}
      <div className="card border-slate-700/50 p-4 sm:p-6">
        <h2 className="mb-3 sm:mb-4 text-base sm:text-lg font-medium text-white">{t('system:power.demands.title')}</h2>
        <DemandList demands={demands} onUnregister={handleUnregisterDemand} isAdmin={isAdmin} t={t} />
      </div>

      {/* History */}
      <div className="card border-slate-700/50 p-4 sm:p-6">
        <h2 className="mb-3 sm:mb-4 text-base sm:text-lg font-medium text-white">{t('system:power.history.title')}</h2>
        <HistoryTable entries={history} t={t} />
      </div>

      {/* Auto-Scaling Config (Admin only) */}
      {isAdmin && autoScaling && (
        <div className={`card border-slate-700/50 p-4 sm:p-6 ${status?.dynamic_mode_enabled ? 'opacity-50 pointer-events-none' : ''}`}>
          <div className="mb-3 sm:mb-4 flex items-center justify-between">
            <h2 className="text-base sm:text-lg font-medium text-white flex items-center gap-2">
              {t('system:power.autoScaling.title')}
              <AdminBadge />
            </h2>
            {!editingAutoScaling ? (
              <button
                onClick={handleStartEditAutoScaling}
                disabled={busy}
                className="text-xs text-slate-400 hover:text-white flex items-center gap-1"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                </svg>
                {t('system:power.autoScaling.editButton')}
              </button>
            ) : (
              <div className="flex gap-2">
                <button
                  onClick={handleCancelEditAutoScaling}
                  disabled={busy}
                  className="rounded px-3 py-1 text-xs bg-slate-700 text-slate-300 hover:bg-slate-600"
                >
                  {t('system:power.autoScaling.cancelButton')}
                </button>
                <button
                  onClick={handleSaveAutoScaling}
                  disabled={busy}
                  className="rounded px-3 py-1 text-xs bg-blue-500/20 text-blue-300 hover:bg-blue-500/30"
                >
                  {t('system:power.autoScaling.saveButton')}
                </button>
              </div>
            )}
          </div>
          {editingAutoScaling && editAutoScaling ? (
            <>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 sm:gap-4">
                <div className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-2 sm:p-4">
                  <label className="block text-[10px] sm:text-sm text-slate-400 mb-1">{t('system:power.autoScaling.surge')}</label>
                  <div className="flex items-center gap-1">
                    <span className="text-red-300 text-sm">&gt;</span>
                    <input
                      type="number"
                      min={0}
                      max={100}
                      value={editAutoScaling.cpu_surge_threshold}
                      onChange={(e) => setEditAutoScaling({ ...editAutoScaling, cpu_surge_threshold: Number(e.target.value) })}
                      className="w-full rounded bg-slate-900 border border-slate-600 px-2 py-1 text-sm sm:text-xl font-semibold text-red-300 focus:border-red-400 focus:outline-none"
                    />
                    <span className="text-red-300 text-sm">%</span>
                  </div>
                </div>
                <div className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-2 sm:p-4">
                  <label className="block text-[10px] sm:text-sm text-slate-400 mb-1">{t('system:power.autoScaling.medium')}</label>
                  <div className="flex items-center gap-1">
                    <span className="text-yellow-300 text-sm">&gt;</span>
                    <input
                      type="number"
                      min={0}
                      max={100}
                      value={editAutoScaling.cpu_medium_threshold}
                      onChange={(e) => setEditAutoScaling({ ...editAutoScaling, cpu_medium_threshold: Number(e.target.value) })}
                      className="w-full rounded bg-slate-900 border border-slate-600 px-2 py-1 text-sm sm:text-xl font-semibold text-yellow-300 focus:border-yellow-400 focus:outline-none"
                    />
                    <span className="text-yellow-300 text-sm">%</span>
                  </div>
                </div>
                <div className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-2 sm:p-4">
                  <label className="block text-[10px] sm:text-sm text-slate-400 mb-1">{t('system:power.autoScaling.low')}</label>
                  <div className="flex items-center gap-1">
                    <span className="text-blue-300 text-sm">&gt;</span>
                    <input
                      type="number"
                      min={0}
                      max={100}
                      value={editAutoScaling.cpu_low_threshold}
                      onChange={(e) => setEditAutoScaling({ ...editAutoScaling, cpu_low_threshold: Number(e.target.value) })}
                      className="w-full rounded bg-slate-900 border border-slate-600 px-2 py-1 text-sm sm:text-xl font-semibold text-blue-300 focus:border-blue-400 focus:outline-none"
                    />
                    <span className="text-blue-300 text-sm">%</span>
                  </div>
                </div>
              </div>
              <div className="mt-2 sm:mt-3 flex items-center gap-4">
                <div className="flex items-center gap-2">
                  <span className="text-xs sm:text-sm text-slate-500">{t('system:power.autoScaling.cooldown')}:</span>
                  <input
                    type="number"
                    min={0}
                    value={editAutoScaling.cooldown_seconds}
                    onChange={(e) => setEditAutoScaling({ ...editAutoScaling, cooldown_seconds: Number(e.target.value) })}
                    className="w-20 rounded bg-slate-900 border border-slate-600 px-2 py-1 text-xs sm:text-sm text-white focus:border-blue-400 focus:outline-none"
                  />
                  <span className="text-xs sm:text-sm text-slate-500">s</span>
                </div>
              </div>
            </>
          ) : (
            <>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 sm:gap-4">
                <div className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-2 sm:p-4">
                  <p className="text-[10px] sm:text-sm text-slate-400">{t('system:power.autoScaling.surge')}</p>
                  <p className="text-sm sm:text-xl font-semibold text-red-300">&gt;{autoScaling.cpu_surge_threshold}%</p>
                </div>
                <div className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-2 sm:p-4">
                  <p className="text-[10px] sm:text-sm text-slate-400">{t('system:power.autoScaling.medium')}</p>
                  <p className="text-sm sm:text-xl font-semibold text-yellow-300">&gt;{autoScaling.cpu_medium_threshold}%</p>
                </div>
                <div className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-2 sm:p-4">
                  <p className="text-[10px] sm:text-sm text-slate-400">{t('system:power.autoScaling.low')}</p>
                  <p className="text-sm sm:text-xl font-semibold text-blue-300">&gt;{autoScaling.cpu_low_threshold}%</p>
                </div>
              </div>
              <p className="mt-2 sm:mt-3 text-xs sm:text-sm text-slate-500">
                {t('system:power.autoScaling.cooldown')}: {autoScaling.cooldown_seconds}s &bull; {t('system:power.autoScaling.cpuMonitor')}:{' '}
                {autoScaling.use_cpu_monitoring ? t('system:power.autoScaling.active') : t('system:power.autoScaling.inactive')}
              </p>
            </>
          )}
        </div>
      )}

      {/* Permission Warning Banner */}
      {status?.is_using_linux_backend && status.permission_status && !status.permission_status.has_write_access && (
        <div className="mb-4 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-4">
          <div className="flex items-start gap-3">
            <AlertTriangle className="h-5 w-5 text-amber-400 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <h3 className="font-semibold text-amber-200">
                {t('system:power.permissions.warningTitle')}
              </h3>
              <p className="text-sm text-amber-300 mt-1">
                {t('system:power.permissions.warningMessage')}
              </p>
              <div className="mt-3 text-sm text-amber-300/80">
                <p className="font-medium mb-1">{t('system:power.permissions.suggestions')}</p>
                <ul className="list-disc list-inside space-y-1 font-mono text-xs">
                  <li>sudo systemctl start baluhost-backend</li>
                  <li>sudo usermod -aG cpufreq $USER</li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Permission Status (Linux backend only) */}
      {status?.is_using_linux_backend && status.permission_status && (
        <div className="card border-slate-700/50 p-4 sm:p-6">
          <h2 className="mb-3 sm:mb-4 text-base sm:text-lg font-medium text-white">{t('system:power.permissions.title')}</h2>
          <div className="grid grid-cols-2 gap-2 sm:gap-4 lg:grid-cols-4">
            {/* Write Access Status */}
            <div className={`rounded-lg border p-2 sm:p-4 ${
              status.permission_status.has_write_access
                ? 'border-emerald-500/30 bg-emerald-500/10'
                : 'border-red-500/30 bg-red-500/10'
            }`}>
              <p className="text-[10px] sm:text-sm text-slate-400">{t('system:power.permissions.writeAccess')}</p>
              <p className={`text-sm sm:text-xl font-semibold ${
                status.permission_status.has_write_access ? 'text-emerald-300' : 'text-red-300'
              }`}>
                {status.permission_status.has_write_access ? t('system:power.permissions.ok') : t('system:power.permissions.no')}
              </p>
            </div>

            {/* User Info */}
            <div className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-2 sm:p-4">
              <p className="text-[10px] sm:text-sm text-slate-400">{t('system:power.permissions.user')}</p>
              <p className="text-sm sm:text-xl font-semibold text-white truncate">{status.permission_status.user}</p>
            </div>

            {/* cpufreq Group Status */}
            <div className={`rounded-lg border p-2 sm:p-4 ${
              status.permission_status.in_cpufreq_group
                ? 'border-emerald-500/30 bg-emerald-500/10'
                : 'border-amber-500/30 bg-amber-500/10'
            }`}>
              <p className="text-[10px] sm:text-sm text-slate-400">{t('system:power.permissions.cpufreq')}</p>
              <p className={`text-sm sm:text-xl font-semibold ${
                status.permission_status.in_cpufreq_group ? 'text-emerald-300' : 'text-amber-300'
              }`}>
                {status.permission_status.in_cpufreq_group ? t('system:power.permissions.ok') : t('system:power.permissions.no')}
              </p>
            </div>

            {/* Sudo Status */}
            <div className={`rounded-lg border p-2 sm:p-4 ${
              status.permission_status.sudo_available
                ? 'border-emerald-500/30 bg-emerald-500/10'
                : 'border-slate-700/50 bg-slate-800/30'
            }`}>
              <p className="text-[10px] sm:text-sm text-slate-400">{t('system:power.permissions.sudo')}</p>
              <p className={`text-sm sm:text-xl font-semibold ${
                status.permission_status.sudo_available ? 'text-emerald-300' : 'text-slate-400'
              }`}>
                {status.permission_status.sudo_available ? t('system:power.permissions.ok') : t('system:power.permissions.no')}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Preset Editor Modal */}
      {editorPreset && (
        <PresetEditor
          preset={editorPreset === 'new' ? undefined : editorPreset}
          onSave={handleSavePreset}
          onClose={() => setEditorPreset(null)}
          onDelete={editorPreset !== 'new' && !editorPreset.is_system_preset ? handleDeletePreset : undefined}
          t={t}
        />
      )}
    </div>
  );
}
