/**
 * Dynamic Mode Section for Power Management
 *
 * Allows enabling kernel-governor-based CPU frequency scaling
 * that bypasses the discrete profile system.
 */

import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { AdminBadge } from '../ui/AdminBadge';
import {
  updateDynamicMode,
  formatClockSpeed,
  GOVERNOR_INFO,
  type DynamicModeConfigResponse,
} from '../../api/power-management';

interface DynamicModeSectionProps {
  config: DynamicModeConfigResponse;
  isAdmin: boolean;
  busy: boolean;
  onBusyChange: (busy: boolean) => void;
  onRefresh: () => void;
}

export function DynamicModeSection({
  config,
  isAdmin,
  busy,
  onBusyChange,
  onRefresh,
}: DynamicModeSectionProps) {
  const { t } = useTranslation(['system']);
  const [enabled, setEnabled] = useState(config.config.enabled);
  const [governor, setGovernor] = useState(config.config.governor);
  const [minFreq, setMinFreq] = useState(config.config.min_freq_mhz);
  const [maxFreq, setMaxFreq] = useState(config.config.max_freq_mhz);
  const [dirty, setDirty] = useState(false);

  // Sync from props when config changes externally
  useEffect(() => {
    setEnabled(config.config.enabled);
    setGovernor(config.config.governor);
    setMinFreq(config.config.min_freq_mhz);
    setMaxFreq(config.config.max_freq_mhz);
    setDirty(false);
  }, [config]);

  const hasChanges = (
    enabled !== config.config.enabled ||
    governor !== config.config.governor ||
    minFreq !== config.config.min_freq_mhz ||
    maxFreq !== config.config.max_freq_mhz
  );

  const validationError = minFreq > maxFreq
    ? t('system:power.dynamicMode.validationError')
    : null;

  const handleToggle = () => {
    setEnabled(!enabled);
    setDirty(true);
  };

  const handleSave = async () => {
    if (busy || validationError) return;

    onBusyChange(true);
    try {
      await updateDynamicMode({
        enabled,
        governor,
        min_freq_mhz: minFreq,
        max_freq_mhz: maxFreq,
      });
      toast.success(
        enabled
          ? t('system:power.dynamicMode.enabled')
          : t('system:power.dynamicMode.disabled')
      );
      setDirty(false);
      onRefresh();
    } catch (err) {
      const message = err instanceof Error ? err.message : t('system:power.toasts.saveFailed');
      toast.error(message);
    } finally {
      onBusyChange(false);
    }
  };

  // Show all governors available on the system (with graceful fallback for unknown ones)
  const availableGovernors = config.available_governors;

  return (
    <div className={`card border-slate-700/50 p-4 sm:p-6 ${
      config.config.enabled ? 'ring-1 ring-teal-500/40' : ''
    }`}>
      <div className="mb-3 sm:mb-4 flex flex-col sm:flex-row sm:items-center justify-between gap-2 sm:gap-4">
        <div className="flex items-center gap-3">
          <h2 className="text-base sm:text-lg font-medium text-white">
            {t('system:power.dynamicMode.title')}
          </h2>
          {config.config.enabled && (
            <span className="rounded-full bg-teal-500/20 px-2.5 py-0.5 text-xs font-medium text-teal-300">
              {t('system:power.dynamicMode.active')}
            </span>
          )}
        </div>
        {isAdmin && (
          <div className="flex items-center gap-3">
            <button
              onClick={handleToggle}
              disabled={busy}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-teal-500 focus:ring-offset-2 focus:ring-offset-slate-900 ${
                enabled ? 'bg-teal-500' : 'bg-slate-600'
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  enabled ? 'translate-x-6' : 'translate-x-1'
                }`}
              />
            </button>
            <AdminBadge />
          </div>
        )}
      </div>

      <p className="text-xs sm:text-sm text-slate-400 mb-4">
        {t('system:power.dynamicMode.description')}
      </p>

      {/* Governor Selection */}
      <div className="space-y-4">
        <div>
          <label className="block text-xs sm:text-sm text-slate-400 mb-2">
            {t('system:power.dynamicMode.governor')}
          </label>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            {availableGovernors.map(gov => {
              const info = GOVERNOR_INFO[gov];
              return (
                <button
                  key={gov}
                  onClick={() => { setGovernor(gov); setDirty(true); }}
                  disabled={busy || !isAdmin}
                  className={`rounded-lg border p-3 text-left transition-colors ${
                    governor === gov
                      ? 'border-teal-500/50 bg-teal-500/10'
                      : 'border-slate-700/50 bg-slate-800/30 hover:bg-slate-800/50'
                  } ${!isAdmin ? 'opacity-60 cursor-not-allowed' : ''}`}
                >
                  <div className="flex items-center justify-between">
                    <span className={`text-sm font-medium ${
                      governor === gov ? 'text-teal-300' : 'text-white'
                    }`}>
                      {info?.name || gov}
                    </span>
                    {info?.recommended && (
                      <span className="text-[10px] text-teal-400 bg-teal-500/10 px-1.5 py-0.5 rounded">
                        {t('system:power.dynamicMode.recommended')}
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-slate-500 mt-1">
                    {info?.description || gov}
                  </p>
                </button>
              );
            })}
          </div>
        </div>

        {/* Frequency Range */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs sm:text-sm text-slate-400 mb-1">
              {t('system:power.dynamicMode.minFrequency')}
            </label>
            <div className="flex items-center gap-2">
              <input
                type="number"
                min={config.system_min_freq_mhz}
                max={config.system_max_freq_mhz}
                step={100}
                value={minFreq}
                onChange={(e) => { setMinFreq(Number(e.target.value)); setDirty(true); }}
                disabled={busy || !isAdmin}
                className="w-full rounded bg-slate-900 border border-slate-600 px-3 py-2 text-sm text-white focus:border-teal-400 focus:outline-none disabled:opacity-50"
              />
              <span className="text-xs text-slate-500 whitespace-nowrap">MHz</span>
            </div>
            <p className="text-[10px] text-slate-500 mt-1">
              {t('system:power.dynamicMode.systemMin')}: {formatClockSpeed(config.system_min_freq_mhz)}
            </p>
          </div>
          <div>
            <label className="block text-xs sm:text-sm text-slate-400 mb-1">
              {t('system:power.dynamicMode.maxFrequency')}
            </label>
            <div className="flex items-center gap-2">
              <input
                type="number"
                min={config.system_min_freq_mhz}
                max={config.system_max_freq_mhz}
                step={100}
                value={maxFreq}
                onChange={(e) => { setMaxFreq(Number(e.target.value)); setDirty(true); }}
                disabled={busy || !isAdmin}
                className="w-full rounded bg-slate-900 border border-slate-600 px-3 py-2 text-sm text-white focus:border-teal-400 focus:outline-none disabled:opacity-50"
              />
              <span className="text-xs text-slate-500 whitespace-nowrap">MHz</span>
            </div>
            <p className="text-[10px] text-slate-500 mt-1">
              {t('system:power.dynamicMode.systemMax')}: {formatClockSpeed(config.system_max_freq_mhz)}
            </p>
          </div>
        </div>

        {/* Validation Error */}
        {validationError && (
          <p className="text-xs text-red-400">{validationError}</p>
        )}

        {/* Save Button */}
        {isAdmin && (dirty || hasChanges) && (
          <div className="flex justify-end">
            <button
              onClick={handleSave}
              disabled={busy || !!validationError}
              className="rounded-lg bg-teal-500/20 px-4 py-2 text-sm font-medium text-teal-300 hover:bg-teal-500/30 transition-colors disabled:opacity-50"
            >
              {t('system:power.dynamicMode.save')}
            </button>
          </div>
        )}

        {/* Info when active */}
        {config.config.enabled && (
          <p className="text-xs text-teal-400/70 border-t border-slate-700/50 pt-3">
            {t('system:power.dynamicMode.profilesPaused')}
          </p>
        )}
      </div>
    </div>
  );
}
