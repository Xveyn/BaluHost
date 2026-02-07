import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { TrendingUp, Table, LineChart as LineChartIcon, Zap, Volume2, Gauge, Info } from 'lucide-react';
import toast from 'react-hot-toast';
import { useTranslation } from 'react-i18next';
import type { FanInfo, FanCurvePoint } from '../../api/fan-control';
import { CURVE_PRESETS, updateFanConfig } from '../../api/fan-control';
import FanCurveChart from './FanCurveChart';

interface FanDetailsProps {
  fan: FanInfo;
  onCurveUpdate: (fanId: string, points: FanCurvePoint[]) => void;
  isReadOnly: boolean;
  onEditingChange?: (isEditing: boolean) => void;
  onConfigUpdate?: () => void;
}

export default function FanDetails({ fan, onCurveUpdate, isReadOnly, onEditingChange, onConfigUpdate }: FanDetailsProps) {
  const { t } = useTranslation(['system', 'common']);
  const [curvePoints, setCurvePoints] = useState<FanCurvePoint[]>(fan.curve_points);
  const [viewMode, setViewMode] = useState<'chart' | 'table'>('chart');
  const [hysteresis, setHysteresis] = useState<number>(fan.hysteresis_celsius ?? 3.0);
  const [isUpdatingHysteresis, setIsUpdatingHysteresis] = useState(false);

  // Tracks whether the user has manually edited the curve (prevents auto-refresh overwrites)
  const userEditedRef = useRef(false);

  // Editing is always enabled when not read-only (FanControl-style)
  const canEdit = !isReadOnly;

  // Check if curve has been modified (compare with original)
  const hasUnsavedChanges = useMemo(() => {
    if (curvePoints.length !== fan.curve_points.length) return true;
    const sortedCurrent = [...curvePoints].sort((a, b) => a.temp - b.temp);
    const sortedOriginal = [...fan.curve_points].sort((a, b) => a.temp - b.temp);
    return sortedCurrent.some((p, i) =>
      p.temp !== sortedOriginal[i].temp || p.pwm !== sortedOriginal[i].pwm
    );
  }, [curvePoints, fan.curve_points]);

  // Sync curve points from server — but only when user hasn't manually edited
  useEffect(() => {
    if (!userEditedRef.current) {
      setCurvePoints(fan.curve_points);
    }
  }, [fan.fan_id, fan.curve_points]);

  // Reset userEditedRef when switching to a different fan
  useEffect(() => {
    userEditedRef.current = false;
    setCurvePoints(fan.curve_points);
  }, [fan.fan_id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setHysteresis(fan.hysteresis_celsius ?? 3.0);
  }, [fan.fan_id, fan.hysteresis_celsius]);

  // Notify parent when there are unsaved changes (to pause auto-refresh)
  useEffect(() => {
    onEditingChange?.(hasUnsavedChanges);
  }, [hasUnsavedChanges, onEditingChange]);

  const validateCurvePoints = (points: FanCurvePoint[]): { valid: boolean; error?: string } => {
    if (points.length < 2) {
      return { valid: false, error: t('system:fanControl.validation.minPoints') };
    }

    // Check ascending temperatures
    const sorted = [...points].sort((a, b) => a.temp - b.temp);
    for (let i = 0; i < sorted.length - 1; i++) {
      if (sorted[i].temp >= sorted[i + 1].temp) {
        return { valid: false, error: t('system:fanControl.validation.ascendingTemp') };
      }
    }

    // Check PWM range
    for (const point of points) {
      if (point.pwm < fan.min_pwm_percent || point.pwm > fan.max_pwm_percent) {
        return {
          valid: false,
          error: t('system:fanControl.validation.pwmRange', { min: fan.min_pwm_percent, max: fan.max_pwm_percent })
        };
      }
    }

    return { valid: true };
  };

  const handleSaveCurve = () => {
    const validation = validateCurvePoints(curvePoints);
    if (!validation.valid) {
      toast.error(validation.error || t('system:fanControl.validation.invalidCurve'));
      return;
    }

    userEditedRef.current = false;
    onCurveUpdate(fan.fan_id, curvePoints);
  };

  const handleDiscardChanges = () => {
    userEditedRef.current = false;
    setCurvePoints(fan.curve_points);
  };

  const handleAddPoint = () => {
    userEditedRef.current = true;
    const lastPoint = curvePoints[curvePoints.length - 1];
    const newTemp = lastPoint ? lastPoint.temp + 10 : 40;
    const newPWM = lastPoint ? Math.min(lastPoint.pwm + 10, 100) : 50;
    setCurvePoints([...curvePoints, { temp: newTemp, pwm: newPWM }]);
  };

  const handleRemovePoint = (index: number) => {
    if (curvePoints.length > 2) {
      userEditedRef.current = true;
      setCurvePoints(curvePoints.filter((_, i) => i !== index));
    }
  };

  const handleUpdatePoint = (index: number, field: 'temp' | 'pwm', value: number) => {
    userEditedRef.current = true;
    const updated = [...curvePoints];
    updated[index] = { ...updated[index], [field]: value };
    setCurvePoints(updated);
  };

  const handleApplyPreset = (preset: keyof typeof CURVE_PRESETS) => {
    const presetPoints = CURVE_PRESETS[preset];
    if (presetPoints) {
      userEditedRef.current = true;
      setCurvePoints([...presetPoints]);
      toast.success(t('system:fanControl.curve.presetApplied', { preset }));
    }
  };

  // Wrapper for FanCurveChart's onPointsChange — marks as user-edited
  const handleChartPointsChange = useCallback((points: FanCurvePoint[]) => {
    userEditedRef.current = true;
    setCurvePoints(points);
  }, []);

  const handleHysteresisChange = async (value: number) => {
    setHysteresis(value);
  };

  const handleHysteresisSave = async () => {
    if (isReadOnly) return;

    setIsUpdatingHysteresis(true);
    try {
      await updateFanConfig(fan.fan_id, { hysteresis_celsius: hysteresis });
      toast.success(t('system:fanControl.messages.hysteresisSet', { value: hysteresis }));
      onConfigUpdate?.();
    } catch {
      toast.error(t('system:fanControl.messages.hysteresisFailed'));
      setHysteresis(fan.hysteresis_celsius ?? 3.0);
    } finally {
      setIsUpdatingHysteresis(false);
    }
  };

  const hysteresisChanged = hysteresis !== (fan.hysteresis_celsius ?? 3.0);

  return (
    <div className="card">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
        <h2 className="text-xl font-bold text-white flex items-center gap-2">
          <TrendingUp className="w-6 h-6 text-sky-400" />
          {fan.name} - {t('system:fanControl.curve.title')}
        </h2>

        {/* Preset Buttons */}
        {!isReadOnly && (
          <div className="flex gap-2">
            <button
              onClick={() => handleApplyPreset('silent')}
              className="px-3 py-1.5 bg-slate-700 text-slate-300 rounded-lg hover:bg-slate-600 text-sm flex items-center gap-1.5 transition-colors"
              title={t('system:fanControl.presets.silentDesc')}
            >
              <Volume2 className="w-4 h-4" />
              {t('system:fanControl.presets.silent')}
            </button>
            <button
              onClick={() => handleApplyPreset('balanced')}
              className="px-3 py-1.5 bg-slate-700 text-slate-300 rounded-lg hover:bg-slate-600 text-sm flex items-center gap-1.5 transition-colors"
              title={t('system:fanControl.presets.balancedDesc')}
            >
              <Gauge className="w-4 h-4" />
              {t('system:fanControl.presets.balanced')}
            </button>
            <button
              onClick={() => handleApplyPreset('performance')}
              className="px-3 py-1.5 bg-slate-700 text-slate-300 rounded-lg hover:bg-slate-600 text-sm flex items-center gap-1.5 transition-colors"
              title={t('system:fanControl.presets.performanceDesc')}
            >
              <Zap className="w-4 h-4" />
              {t('system:fanControl.presets.performance')}
            </button>
          </div>
        )}
      </div>

      {/* Curve Editor */}
      <div className="mb-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
          <p className="text-sm text-slate-400">
            {t('system:fanControl.curve.configureInfo')}
          </p>
          <div className="flex gap-2 items-center">
            {/* View Mode Toggle */}
            <div className="flex gap-1 bg-slate-800 rounded-lg p-1">
              <button
                onClick={() => setViewMode('chart')}
                className={`px-3 py-1 text-xs rounded-md transition-colors flex items-center gap-1 ${
                  viewMode === 'chart'
                    ? 'bg-sky-500 text-white shadow-lg shadow-sky-500/30'
                    : 'text-slate-400 hover:text-slate-300'
                }`}
              >
                <LineChartIcon className="w-3 h-3" />
                {t('system:fanControl.curve.chart')}
              </button>
              <button
                onClick={() => setViewMode('table')}
                className={`px-3 py-1 text-xs rounded-md transition-colors flex items-center gap-1 ${
                  viewMode === 'table'
                    ? 'bg-sky-500 text-white shadow-lg shadow-sky-500/30'
                    : 'text-slate-400 hover:text-slate-300'
                }`}
              >
                <Table className="w-3 h-3" />
                {t('system:fanControl.curve.table')}
              </button>
            </div>

            {/* Save/Discard Buttons - only shown when there are unsaved changes */}
            {hasUnsavedChanges && !isReadOnly && (
              <div className="flex gap-2">
                <button
                  onClick={handleDiscardChanges}
                  className="px-4 py-2 bg-slate-700 text-slate-300 rounded-lg hover:bg-slate-600 text-sm"
                >
                  {t('system:fanControl.curve.discard')}
                </button>
                <button
                  onClick={handleSaveCurve}
                  className="px-4 py-2 bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 shadow-lg shadow-emerald-500/30 text-sm"
                >
                  {t('system:fanControl.curve.save')}
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Chart View */}
        {viewMode === 'chart' && (
          <div className="mt-4">
            <FanCurveChart
              points={curvePoints}
              onPointsChange={handleChartPointsChange}
              currentTemp={fan.temperature_celsius}
              currentPWM={fan.pwm_percent}
              minPWM={fan.min_pwm_percent}
              maxPWM={fan.max_pwm_percent}
              emergencyTemp={fan.emergency_temp_celsius}
              isEditing={canEdit}
              isReadOnly={isReadOnly}
            />
          </div>
        )}

        {/* Table View */}
        {viewMode === 'table' && (
          <>
            <div className="overflow-x-auto">
              <table className="w-full border border-slate-700">
                <thead className="bg-slate-800">
                  <tr>
                    <th className="px-4 py-2 text-left text-sm font-medium text-slate-300">{t('system:fanControl.details.temperatureCol')}</th>
                    <th className="px-4 py-2 text-left text-sm font-medium text-slate-300">{t('system:fanControl.details.pwmCol')}</th>
                    {canEdit && <th className="px-4 py-2 text-left text-sm font-medium text-slate-300">{t('system:fanControl.details.actionsCol')}</th>}
                  </tr>
                </thead>
                <tbody>
                  {[...curvePoints]
                    .map((point, originalIndex) => ({ ...point, originalIndex }))
                    .sort((a, b) => a.temp - b.temp)
                    .map((point) => (
                      <tr key={point.originalIndex} className="border-t border-slate-700">
                        <td className="px-4 py-2">
                          {canEdit ? (
                            <input
                              type="number"
                              value={point.temp}
                              onChange={(e) => handleUpdatePoint(point.originalIndex, 'temp', parseFloat(e.target.value))}
                              className="w-20 px-2 py-1 border border-slate-600 rounded bg-slate-800 text-white"
                              min={0}
                              max={150}
                            />
                          ) : (
                            <span className="text-slate-300">{point.temp}°C</span>
                          )}
                        </td>
                        <td className="px-4 py-2">
                          {canEdit ? (
                            <input
                              type="number"
                              value={point.pwm}
                              onChange={(e) => handleUpdatePoint(point.originalIndex, 'pwm', parseInt(e.target.value))}
                              className="w-20 px-2 py-1 border border-slate-600 rounded bg-slate-800 text-white"
                              min={fan.min_pwm_percent}
                              max={fan.max_pwm_percent}
                            />
                          ) : (
                            <span className="text-slate-300">{point.pwm}%</span>
                          )}
                        </td>
                        {canEdit && (
                          <td className="px-4 py-2">
                            <button
                              onClick={() => handleRemovePoint(point.originalIndex)}
                              disabled={curvePoints.length <= 2}
                              className="text-rose-400 hover:text-rose-300 disabled:opacity-50 disabled:cursor-not-allowed text-sm"
                            >
                              {t('system:fanControl.curve.remove')}
                            </button>
                          </td>
                        )}
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>

            {canEdit && curvePoints.length < 10 && (
              <button
                onClick={handleAddPoint}
                className="mt-3 px-4 py-2 bg-sky-500 text-white rounded-lg hover:bg-sky-600 shadow-lg shadow-sky-500/30 text-sm"
              >
                {t('system:fanControl.curve.addPoint')}
              </button>
            )}
          </>
        )}
      </div>

      {/* Fan Stats */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 pt-4 border-t border-slate-700">
        <div>
          <p className="text-xs text-slate-400">{t('system:fanControl.details.minPwm')}</p>
          <p className="text-lg font-bold text-white">{fan.min_pwm_percent}%</p>
        </div>
        <div>
          <p className="text-xs text-slate-400">{t('system:fanControl.details.maxPwm')}</p>
          <p className="text-lg font-bold text-white">{fan.max_pwm_percent}%</p>
        </div>
        <div>
          <p className="text-xs text-slate-400">{t('system:fanControl.details.emergencyTemp')}</p>
          <p className="text-lg font-bold text-white">{fan.emergency_temp_celsius}°C</p>
        </div>
        <div>
          <p className="text-xs text-slate-400">{t('system:fanControl.details.sensorId')}</p>
          <p className="text-sm font-mono text-slate-300">{fan.temp_sensor_id || '—'}</p>
        </div>
        <div>
          <p className="text-xs text-slate-400 flex items-center gap-1">
            {t('system:fanControl.details.hysteresis')}
            <span
              className="cursor-help"
              title={t('system:fanControl.details.hysteresisTooltip')}
            >
              <Info className="w-3 h-3 text-slate-500" />
            </span>
          </p>
          {canEdit ? (
            <div className="flex items-center gap-2">
              <input
                type="number"
                value={hysteresis}
                onChange={(e) => handleHysteresisChange(parseFloat(e.target.value) || 0)}
                onBlur={handleHysteresisSave}
                onKeyDown={(e) => e.key === 'Enter' && handleHysteresisSave()}
                className="w-16 px-2 py-1 text-sm border border-slate-600 rounded bg-slate-800 text-white"
                min={0}
                max={15}
                step={0.5}
                disabled={isUpdatingHysteresis}
              />
              <span className="text-sm text-slate-400">°C</span>
              {hysteresisChanged && !isUpdatingHysteresis && (
                <span className="text-xs text-amber-400">{t('system:fanControl.details.unsaved')}</span>
              )}
              {isUpdatingHysteresis && (
                <span className="text-xs text-sky-400">{t('system:fanControl.details.saving')}</span>
              )}
            </div>
          ) : (
            <p className="text-lg font-bold text-white">{fan.hysteresis_celsius ?? 3.0}°C</p>
          )}
        </div>
      </div>
    </div>
  );
}
