import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { X } from 'lucide-react';
import type { FanScheduleEntry, FanCurvePoint, CreateFanScheduleEntryRequest, UpdateFanScheduleEntryRequest } from '../../api/fan-control';
import { CURVE_PRESETS } from '../../api/fan-control';

interface ScheduleEntryFormProps {
  entry?: FanScheduleEntry; // If provided, we're editing; otherwise creating
  onSubmit: (data: CreateFanScheduleEntryRequest | UpdateFanScheduleEntryRequest) => Promise<void>;
  onCancel: () => void;
  isSubmitting: boolean;
}

type PresetKey = 'silent' | 'balanced' | 'performance' | 'custom';

function detectPreset(points: FanCurvePoint[]): PresetKey {
  for (const [name, presetPoints] of Object.entries(CURVE_PRESETS)) {
    if (points.length === presetPoints.length &&
      points.every((p, i) => p.temp === presetPoints[i].temp && p.pwm === presetPoints[i].pwm)
    ) {
      return name as PresetKey;
    }
  }
  return 'custom';
}

export default function ScheduleEntryForm({ entry, onSubmit, onCancel, isSubmitting }: ScheduleEntryFormProps) {
  const { t } = useTranslation(['system', 'common']);
  const isEditing = !!entry;

  const [name, setName] = useState(entry?.name ?? '');
  const [startTime, setStartTime] = useState(entry?.start_time ?? '22:00');
  const [endTime, setEndTime] = useState(entry?.end_time ?? '06:00');
  const [priority, setPriority] = useState(entry?.priority ?? 0);
  const [isEnabled, setIsEnabled] = useState(entry?.is_enabled ?? true);
  const [selectedPreset, setSelectedPreset] = useState<PresetKey>(
    entry ? detectPreset(entry.curve_points) : 'silent'
  );
  const [curvePoints, setCurvePoints] = useState<FanCurvePoint[]>(
    entry?.curve_points ?? CURVE_PRESETS.silent
  );

  // Sync curve when preset changes
  useEffect(() => {
    if (selectedPreset !== 'custom' && CURVE_PRESETS[selectedPreset]) {
      setCurvePoints([...CURVE_PRESETS[selectedPreset]]);
    }
  }, [selectedPreset]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;

    if (isEditing) {
      const update: UpdateFanScheduleEntryRequest = {
        name: name.trim(),
        start_time: startTime,
        end_time: endTime,
        curve_points: curvePoints,
        priority,
        is_enabled: isEnabled,
      };
      await onSubmit(update);
    } else {
      const create: CreateFanScheduleEntryRequest = {
        name: name.trim(),
        start_time: startTime,
        end_time: endTime,
        curve_points: curvePoints,
        priority,
        is_enabled: isEnabled,
      };
      await onSubmit(create);
    }
  };

  return (
    <div className="border border-slate-700 rounded-lg bg-slate-800/50 p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-white">
          {isEditing
            ? t('system:fanControl.schedule.editEntry')
            : t('system:fanControl.schedule.addEntry')
          }
        </h3>
        <button
          onClick={onCancel}
          className="p-1 text-slate-400 hover:text-slate-300 transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Name */}
        <div>
          <label className="block text-xs text-slate-400 mb-1">
            {t('system:fanControl.schedule.name')}
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t('system:fanControl.schedule.namePlaceholder')}
            className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white text-sm focus:outline-none focus:border-sky-500"
            maxLength={100}
            required
          />
        </div>

        {/* Time Range */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-slate-400 mb-1">
              {t('system:fanControl.schedule.startTime')}
            </label>
            <input
              type="time"
              value={startTime}
              onChange={(e) => setStartTime(e.target.value)}
              className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white text-sm focus:outline-none focus:border-sky-500"
              required
            />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">
              {t('system:fanControl.schedule.endTime')}
            </label>
            <input
              type="time"
              value={endTime}
              onChange={(e) => setEndTime(e.target.value)}
              className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white text-sm focus:outline-none focus:border-sky-500"
              required
            />
          </div>
        </div>

        {/* Overnight indicator */}
        {startTime > endTime && (
          <p className="text-xs text-amber-400">
            {t('system:fanControl.schedule.overnight')} ({startTime} &rarr; {endTime})
          </p>
        )}

        {/* Curve Preset Selector */}
        <div>
          <label className="block text-xs text-slate-400 mb-1">
            {t('system:fanControl.schedule.curvePreset')}
          </label>
          <div className="flex gap-2 flex-wrap">
            {(['silent', 'balanced', 'performance', 'custom'] as PresetKey[]).map((preset) => (
              <button
                key={preset}
                type="button"
                onClick={() => setSelectedPreset(preset)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  selectedPreset === preset
                    ? 'bg-sky-500 text-white shadow-lg shadow-sky-500/30'
                    : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                }`}
              >
                {preset === 'custom'
                  ? t('system:fanControl.schedule.customCurve')
                  : t(`system:fanControl.presets.${preset}`)
                }
              </button>
            ))}
          </div>
        </div>

        {/* Custom Curve Editor (simplified table) */}
        {selectedPreset === 'custom' && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm border border-slate-700 rounded">
              <thead className="bg-slate-900">
                <tr>
                  <th className="px-3 py-1.5 text-left text-xs text-slate-400">Temp (°C)</th>
                  <th className="px-3 py-1.5 text-left text-xs text-slate-400">PWM (%)</th>
                  <th className="px-3 py-1.5 text-left text-xs text-slate-400"></th>
                </tr>
              </thead>
              <tbody>
                {curvePoints.map((point, i) => (
                  <tr key={i} className="border-t border-slate-700">
                    <td className="px-3 py-1.5">
                      <input
                        type="number"
                        value={point.temp}
                        onChange={(e) => {
                          const updated = [...curvePoints];
                          updated[i] = { ...updated[i], temp: parseFloat(e.target.value) || 0 };
                          setCurvePoints(updated);
                        }}
                        className="w-16 px-2 py-1 bg-slate-800 border border-slate-600 rounded text-white text-xs"
                        min={0}
                        max={150}
                      />
                    </td>
                    <td className="px-3 py-1.5">
                      <input
                        type="number"
                        value={point.pwm}
                        onChange={(e) => {
                          const updated = [...curvePoints];
                          updated[i] = { ...updated[i], pwm: parseInt(e.target.value) || 0 };
                          setCurvePoints(updated);
                        }}
                        className="w-16 px-2 py-1 bg-slate-800 border border-slate-600 rounded text-white text-xs"
                        min={0}
                        max={100}
                      />
                    </td>
                    <td className="px-3 py-1.5">
                      {curvePoints.length > 2 && (
                        <button
                          type="button"
                          onClick={() => setCurvePoints(curvePoints.filter((_, j) => j !== i))}
                          className="text-rose-400 hover:text-rose-300 text-xs"
                        >
                          &times;
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {curvePoints.length < 10 && (
              <button
                type="button"
                onClick={() => {
                  const last = curvePoints[curvePoints.length - 1];
                  setCurvePoints([...curvePoints, { temp: (last?.temp ?? 50) + 10, pwm: Math.min((last?.pwm ?? 50) + 15, 100) }]);
                }}
                className="mt-2 px-3 py-1 bg-slate-700 text-slate-300 rounded text-xs hover:bg-slate-600"
              >
                + {t('system:fanControl.curve.addPoint')}
              </button>
            )}
          </div>
        )}

        {/* Priority & Enabled */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-slate-400 mb-1">
              {t('system:fanControl.schedule.priority')}
            </label>
            <input
              type="number"
              value={priority}
              onChange={(e) => setPriority(parseInt(e.target.value) || 0)}
              className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white text-sm focus:outline-none focus:border-sky-500"
              min={0}
              max={100}
            />
            <p className="text-[10px] text-slate-500 mt-0.5">
              {t('system:fanControl.schedule.priorityHint')}
            </p>
          </div>
          <div className="flex items-center">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={isEnabled}
                onChange={(e) => setIsEnabled(e.target.checked)}
                className="w-4 h-4 rounded border-slate-600 bg-slate-800 text-sky-500 focus:ring-sky-500 focus:ring-offset-0"
              />
              <span className="text-sm text-slate-300">
                {t('system:fanControl.schedule.enabled')}
              </span>
            </label>
          </div>
        </div>

        {/* Actions */}
        <div className="flex justify-end gap-2 pt-2 border-t border-slate-700">
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 bg-slate-700 text-slate-300 rounded-lg hover:bg-slate-600 text-sm"
            disabled={isSubmitting}
          >
            {t('system:fanControl.schedule.cancel')}
          </button>
          <button
            type="submit"
            disabled={!name.trim() || isSubmitting}
            className="px-4 py-2 bg-sky-500 text-white rounded-lg hover:bg-sky-600 shadow-lg shadow-sky-500/30 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSubmitting ? (
              <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
            ) : isEditing ? (
              t('system:fanControl.schedule.update')
            ) : (
              t('system:fanControl.schedule.create')
            )}
          </button>
        </div>
      </form>
    </div>
  );
}
