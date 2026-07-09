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

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { handleApiError } from '../lib/errorHandling';
import { Spinner } from '../components/ui/Spinner';
import { AdminBadge } from '../components/ui/AdminBadge';
import { PresetSelector } from '../components/power/PresetSelector';
import { PresetEditor } from '../components/power/PresetEditor';
import { PresetClockVisualization } from '../components/power/PresetClockVisualization';
import { ServiceIntensityList } from '../components/power/ServiceIntensityList';
import { DemandList } from '../components/power/DemandList';
import { HistoryTable } from '../components/power/HistoryTable';
import { DynamicModeSection } from '../components/power/DynamicModeSection';
import { GpuPowerCard } from '../components/power/GpuPowerCard';
import { AuthorityPanel } from '../components/power/AuthorityPanel';
import { BoostRulesEditor } from '../components/power/BoostRulesEditor';
import { PowerStatusCards } from '../components/power/PowerStatusCards';
import { PermissionStatusCard } from '../components/power/PermissionStatusCard';
import { AutoScalingSection } from '../components/power/AutoScalingSection';
import { usePowerManagementData } from '../hooks/usePowerManagementData';
import {
  unregisterPowerDemand,
  updateAutoScalingConfig,
  switchPowerBackend,
  activatePreset,
  createPreset,
  updatePreset,
  deletePreset,
  type ServicePowerProperty,
  type PowerPreset,
  type CreatePresetRequest,
} from '../api/power-management';

interface PowerManagementProps {
  isAdmin: boolean;
}

// Main component
export default function PowerManagement({ isAdmin }: PowerManagementProps) {
  const { t } = useTranslation(['system', 'common']);
  // Query-backed (#299): one combined 5s poll (Promise.all over 7 endpoints)
  // replaces the hand-rolled setInterval. Mutations below call refetch().
  const {
    status,
    presets,
    demands,
    intensities,
    history,
    autoScaling,
    dynamicConfig,
    loading,
    error,
    lastUpdated,
    refetch,
  } = usePowerManagementData();
  const [busy, setBusy] = useState(false);
  const [editorPreset, setEditorPreset] = useState<PowerPreset | null | 'new'>(null);

  const handleRefresh = async () => {
    if (await refetch()) {
      toast.success(t('system:power.toasts.statusUpdated'));
    }
  };

  const handlePresetSelect = async (presetId: number) => {
    if (busy) return;

    setBusy(true);
    try {
      const result = await activatePreset(presetId);
      toast.success(result.message);
      await refetch();
    } catch (err) {
      handleApiError(err, t('system:power.toasts.presetActivateFailed'));
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
      await refetch();
    } catch (err) {
      handleApiError(err, t('system:power.toasts.demandRemoveFailed'));
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
      await refetch();
      toast.success(newConfig.enabled ? t('system:power.toasts.autoScalingEnabled') : t('system:power.toasts.autoScalingDisabled'));
    } catch (err) {
      handleApiError(err, t('system:power.toasts.settingChangeFailed'));
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
      await refetch();
    } catch (err) {
      handleApiError(err, t('system:power.toasts.backendSwitchFailed'));
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
      await refetch();
    } catch (err) {
      handleApiError(err, t('system:power.toasts.saveFailed'));
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
      await refetch();
    } catch (err) {
      handleApiError(err, t('system:power.toasts.deleteFailed'));
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
          onClick={handleRefresh}
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
            onClick={handleRefresh}
            disabled={busy}
            className="rounded-lg border border-slate-700 bg-slate-800 px-3 sm:px-4 py-2 text-xs sm:text-sm text-white hover:bg-slate-700 touch-manipulation active:scale-95 min-h-[36px]"
          >
            <span className="hidden sm:inline">{t('system:power.buttons.refresh')}</span>
            <span className="sm:hidden">&#x21bb;</span>
          </button>
        </div>
      </div>

      {/* Status Cards */}
      <PowerStatusCards
        status={status}
        activePreset={activePreset}
        currentProperty={currentProperty}
        demands={demands}
        lastUpdated={lastUpdated}
      />

      {/* Dynamic Mode Section */}
      {dynamicConfig && (
        <DynamicModeSection
          config={dynamicConfig}
          isAdmin={isAdmin}
          busy={busy}
          onBusyChange={setBusy}
          onRefresh={() => void refetch()}
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

      {/* GPU Power Management */}
      <GpuPowerCard isAdmin={isAdmin} />

      {/* CPU Authority */}
      <AuthorityPanel isAdmin={isAdmin} />

      {/* Boost Rules & Boost Now */}
      <BoostRulesEditor isAdmin={isAdmin} />

      {/* Auto-Scaling Config (Admin only) */}
      {isAdmin && autoScaling && (
        <AutoScalingSection
          autoScaling={autoScaling}
          dimmed={!!status?.dynamic_mode_enabled}
          busy={busy}
          onBusyChange={setBusy}
          onRefresh={() => void refetch()}
        />
      )}

      {/* Permission panels (Linux backend only) */}
      <PermissionStatusCard status={status} />

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
