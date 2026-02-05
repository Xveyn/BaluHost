/**
 * PresetEditor -- modal for creating/editing custom power presets.
 */

import { useState } from 'react';
import { formatClockSpeed, type PowerPreset, type CreatePresetRequest } from '../../api/power-management';

interface PresetEditorProps {
  preset?: PowerPreset;
  onSave: (data: CreatePresetRequest) => void;
  onClose: () => void;
  onDelete?: () => void;
  t: (key: string, options?: Record<string, unknown>) => string;
}

export function PresetEditor({ preset, onSave, onClose, onDelete, t }: PresetEditorProps) {
  const [name, setName] = useState(preset?.name || '');
  const [description, setDescription] = useState(preset?.description || '');
  const [idleClock, setIdleClock] = useState(preset?.idle_clock_mhz || 800);
  const [lowClock, setLowClock] = useState(preset?.low_clock_mhz || 1200);
  const [mediumClock, setMediumClock] = useState(preset?.medium_clock_mhz || 2500);
  const [surgeClock, setSurgeClock] = useState(preset?.surge_clock_mhz || 4200);

  const handleSave = () => {
    onSave({
      name,
      description: description || undefined,
      idle_clock_mhz: idleClock,
      low_clock_mhz: lowClock,
      medium_clock_mhz: mediumClock,
      surge_clock_mhz: surgeClock,
      base_clock_mhz: Math.round((idleClock + lowClock + mediumClock + surgeClock) / 4),
    });
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-lg w-full max-w-md max-h-[90vh] overflow-y-auto">
        <div className="p-4 border-b border-slate-700 flex items-center justify-between">
          <h3 className="text-lg font-medium text-white">
            {preset ? t('system:power.presetEditor.editPreset') : t('system:power.presetEditor.createPreset')}
          </h3>
          <button onClick={onClose} className="text-slate-400 hover:text-white">
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="p-4 space-y-4">
          {/* Name */}
          <div>
            <label className="block text-sm font-medium text-slate-400 mb-1">{t('system:power.presetEditor.name')}</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={preset?.is_system_preset}
              className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
              placeholder={t('system:power.presetEditor.namePlaceholder')}
            />
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-slate-400 mb-1">{t('system:power.presetEditor.description')}</label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={preset?.is_system_preset}
              className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
              placeholder={t('system:power.presetEditor.descriptionPlaceholder')}
            />
          </div>

          {/* Clock sliders */}
          <div className="space-y-4">
            <div>
              <div className="flex justify-between mb-1">
                <label className="text-sm font-medium text-emerald-400">IDLE</label>
                <span className="text-sm text-slate-400">{formatClockSpeed(idleClock)}</span>
              </div>
              <input
                type="range"
                min="400"
                max="2000"
                step="100"
                value={idleClock}
                onChange={(e) => setIdleClock(Number(e.target.value))}
                className="w-full accent-emerald-500"
              />
            </div>

            <div>
              <div className="flex justify-between mb-1">
                <label className="text-sm font-medium text-blue-400">LOW</label>
                <span className="text-sm text-slate-400">{formatClockSpeed(lowClock)}</span>
              </div>
              <input
                type="range"
                min="600"
                max="3000"
                step="100"
                value={lowClock}
                onChange={(e) => setLowClock(Number(e.target.value))}
                className="w-full accent-blue-500"
              />
            </div>

            <div>
              <div className="flex justify-between mb-1">
                <label className="text-sm font-medium text-yellow-400">MEDIUM</label>
                <span className="text-sm text-slate-400">{formatClockSpeed(mediumClock)}</span>
              </div>
              <input
                type="range"
                min="1000"
                max="4500"
                step="100"
                value={mediumClock}
                onChange={(e) => setMediumClock(Number(e.target.value))}
                className="w-full accent-yellow-500"
              />
            </div>

            <div>
              <div className="flex justify-between mb-1">
                <label className="text-sm font-medium text-red-400">SURGE</label>
                <span className="text-sm text-slate-400">{formatClockSpeed(surgeClock)}</span>
              </div>
              <input
                type="range"
                min="2000"
                max="5500"
                step="100"
                value={surgeClock}
                onChange={(e) => setSurgeClock(Number(e.target.value))}
                className="w-full accent-red-500"
              />
            </div>
          </div>
        </div>

        <div className="p-4 border-t border-slate-700 flex gap-2">
          {onDelete && !preset?.is_system_preset && (
            <button
              onClick={onDelete}
              className="px-4 py-2 bg-red-500/20 text-red-300 rounded-lg hover:bg-red-500/30"
            >
              {t('system:power.presetEditor.delete')}
            </button>
          )}
          <div className="flex-1" />
          <button
            onClick={onClose}
            className="px-4 py-2 bg-slate-700 text-white rounded-lg hover:bg-slate-600"
          >
            {t('system:power.presetEditor.cancel')}
          </button>
          <button
            onClick={handleSave}
            disabled={!name.trim()}
            className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:opacity-50"
          >
            {t('system:power.presetEditor.save')}
          </button>
        </div>
      </div>
    </div>
  );
}
