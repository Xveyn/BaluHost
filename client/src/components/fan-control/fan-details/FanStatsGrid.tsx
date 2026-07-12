import { Info } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { FanInfo } from '../../../api/fan-control';

interface FanStatsGridProps {
  fan: FanInfo;
  canEdit: boolean;
  hysteresis: number;
  isUpdatingHysteresis: boolean;
  hysteresisChanged: boolean;
  onHysteresisChange: (value: number) => void;
  onHysteresisSave: () => void;
}

export default function FanStatsGrid({
  fan, canEdit, hysteresis, isUpdatingHysteresis, hysteresisChanged,
  onHysteresisChange, onHysteresisSave,
}: FanStatsGridProps) {
  const { t } = useTranslation(['system', 'common']);

  return (
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
              onChange={(e) => onHysteresisChange(parseFloat(e.target.value) || 0)}
              onBlur={onHysteresisSave}
              onKeyDown={(e) => e.key === 'Enter' && onHysteresisSave()}
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
  );
}
