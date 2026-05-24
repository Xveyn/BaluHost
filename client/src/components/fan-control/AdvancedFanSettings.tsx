import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronDown, ChevronRight } from 'lucide-react';
import type { FanInfo } from '../../api/fan-control';

interface Props {
  fan: FanInfo;
  onChange: (patch: Partial<FanInfo>) => void;
  disabled?: boolean;
}

export default function AdvancedFanSettings({ fan, onChange, disabled }: Props) {
  const { t } = useTranslation(['system']);
  const [open, setOpen] = useState(false);

  return (
    <div className="border border-slate-700 rounded">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center w-full px-3 py-2 text-sm font-medium text-white hover:bg-slate-800/50"
      >
        {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        <span className="ml-1">{t('system:fanControl.advanced.title')}</span>
      </button>
      {open && (
        <div className="p-3 space-y-4 border-t border-slate-700">
          <div>
            <label className="text-sm text-white">
              {t('system:fanControl.advanced.startPwm')}: {fan.start_pwm_percent ?? 0}%
            </label>
            <input
              type="range" min={0} max={100} step={1}
              value={fan.start_pwm_percent ?? 0}
              onChange={(e) => onChange({ start_pwm_percent: Number(e.target.value) })}
              disabled={disabled}
              className="w-full"
            />
          </div>
          <div>
            <label className="text-sm text-white">
              {t('system:fanControl.advanced.stopBelowTemp')}:{' '}
              {fan.stop_below_temp_celsius != null ? `${fan.stop_below_temp_celsius}°C` : t('common:disabled')}
            </label>
            <input
              type="range" min={0} max={60} step={1}
              value={fan.stop_below_temp_celsius ?? 0}
              onChange={(e) => onChange({ stop_below_temp_celsius: Number(e.target.value) || null })}
              disabled={disabled}
              className="w-full"
            />
          </div>
          <div>
            <label className="text-sm text-white">
              {t('system:fanControl.advanced.responseTime')}: {(fan.response_time_seconds ?? 0).toFixed(1)}s
            </label>
            <input
              type="range" min={0} max={10} step={0.5}
              value={fan.response_time_seconds ?? 0}
              onChange={(e) => onChange({ response_time_seconds: Number(e.target.value) })}
              disabled={disabled}
              className="w-full"
            />
          </div>
          <div>
            <label className="text-sm text-white">{t('system:fanControl.advanced.pwmSteps')}</label>
            <div className="flex gap-2 mt-1">
              {[1, 5, 10, 25].map((s) => (
                <button
                  key={s}
                  onClick={() => onChange({ pwm_steps: s })}
                  disabled={disabled}
                  className={`px-3 py-1 text-sm rounded ${
                    (fan.pwm_steps ?? 1) === s ? 'bg-sky-500 text-white' : 'bg-slate-700 text-slate-300'
                  }`}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
