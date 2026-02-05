/**
 * PresetSelector -- grid of preset buttons for power profile selection.
 */

import type { PowerPreset } from '../../api/power-management';
import { getPresetColorClasses, getPresetIcon } from './utils';

interface PresetSelectorProps {
  presets: PowerPreset[];
  activePresetId?: number;
  onSelect: (presetId: number) => void;
  disabled?: boolean;
  t: (key: string, options?: Record<string, unknown>) => string;
}

export function PresetSelector({ presets, activePresetId, onSelect, disabled, t }: PresetSelectorProps) {
  // Order: system presets first (Energy Saver, Balanced, Performance), then custom
  const systemPresets = presets.filter(p => p.is_system_preset);
  const customPresets = presets.filter(p => !p.is_system_preset);
  const orderedPresets = [...systemPresets, ...customPresets];

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      {orderedPresets.map((preset) => {
        const isActive = preset.id === activePresetId;
        const icon = getPresetIcon(preset.name);

        return (
          <button
            key={preset.id}
            onClick={() => onSelect(preset.id)}
            disabled={disabled || isActive}
            className={`flex flex-col items-center rounded-lg border p-4 transition-all touch-manipulation active:scale-95 min-h-[140px] ${
              getPresetColorClasses(preset.name, isActive)
            } ${disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}`}
          >
            <span className="text-3xl">{icon}</span>
            <span className="mt-2 text-base font-medium text-white">{preset.name}</span>
            {preset.description && (
              <span className="mt-1 text-xs text-slate-400 text-center line-clamp-2">{preset.description}</span>
            )}
            {!preset.is_system_preset && (
              <span className="mt-1 px-2 py-0.5 text-[10px] bg-slate-700/50 rounded-full text-slate-400">{t('system:power.custom')}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}
