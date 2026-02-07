import { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { FanMode } from '../../api/fan-control';
import type { FanInfo } from '../../api/fan-control';
import { formatNumber } from '../../lib/formatters';

interface FanCardProps {
  fan: FanInfo;
  isSelected: boolean;
  onSelect: () => void;
  onModeChange: (fanId: string, mode: FanMode) => void;
  onPWMChange: (fanId: string, pwm: number) => void;
  isReadOnly: boolean;
  isLoading: boolean;
}

export default function FanCard({
  fan,
  isSelected,
  onSelect,
  onModeChange,
  onPWMChange,
  isReadOnly,
  isLoading
}: FanCardProps) {
  const { t } = useTranslation(['system', 'common']);
  const [localPWM, setLocalPWM] = useState(fan.pwm_percent);
  const debouncedPWMUpdate = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setLocalPWM(fan.pwm_percent);
  }, [fan.pwm_percent]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (debouncedPWMUpdate.current) {
        clearTimeout(debouncedPWMUpdate.current);
      }
    };
  }, []);

  const handlePWMSliderChange = (value: number) => {
    setLocalPWM(value);

    // Clear previous timeout
    if (debouncedPWMUpdate.current) {
      clearTimeout(debouncedPWMUpdate.current);
    }

    // Debounce API call (500ms)
    debouncedPWMUpdate.current = setTimeout(() => {
      if (fan.mode === FanMode.MANUAL) {
        onPWMChange(fan.fan_id, value);
      }
    }, 500);
  };

  const getModeColor = (mode: FanMode): string => {
    switch (mode) {
      case FanMode.AUTO:
        return 'border-sky-500/30 bg-sky-500/10 text-sky-300';
      case FanMode.MANUAL:
        return 'border-purple-500/30 bg-purple-500/10 text-purple-300';
      case FanMode.EMERGENCY:
        return 'border-rose-500/30 bg-rose-500/10 text-rose-300';
      default:
        return 'border-slate-500/30 bg-slate-500/10 text-slate-300';
    }
  };

  return (
    <div
      onClick={onSelect}
      className={`card transition-all duration-200 cursor-pointer touch-manipulation active:scale-[0.98] ${
        isSelected
          ? 'border-sky-500/60 bg-sky-500/5 shadow-[0_14px_44px_rgba(56,189,248,0.15)]'
          : 'border-slate-800/40 hover:border-slate-700/60 hover:bg-slate-900/80'
      }`}
    >
      {/* Fan Name & Mode */}
      <div className="flex items-start justify-between mb-3">
        <div>
          <h3 className="font-semibold text-white">{fan.name}</h3>
          <p className="text-xs text-slate-400 mt-1">{fan.fan_id}</p>
        </div>
        <span className={`px-2 py-1 rounded-full border text-xs font-medium ${getModeColor(fan.mode)}`}>
          {fan.mode.toUpperCase()}
        </span>
      </div>

      {/* RPM & PWM */}
      <div className="grid grid-cols-2 gap-3 mb-3">
        <div>
          <p className="text-xs text-slate-400">{t('system:fanControl.card.rpm')}</p>
          <p className="text-lg font-bold text-white">
            {fan.rpm !== null ? fan.rpm.toLocaleString() : '—'}
          </p>
        </div>
        <div>
          <p className="text-xs text-slate-400">{t('system:fanControl.card.pwm')}</p>
          <p className="text-lg font-bold text-white">
            {fan.pwm_percent}%
          </p>
        </div>
      </div>

      {/* Temperature */}
      {fan.temperature_celsius !== null && (
        <div className="mb-3">
          <p className="text-xs text-slate-400">{t('system:fanControl.card.temperature')}</p>
          <p className="text-lg font-bold text-white">
            {formatNumber(fan.temperature_celsius, 1)}°C
          </p>
        </div>
      )}

      {/* Mode Toggle */}
      <div className="flex gap-2 mb-3">
        <button
          onClick={(e) => {
            e.stopPropagation();
            onModeChange(fan.fan_id, FanMode.AUTO);
          }}
          disabled={fan.mode === FanMode.AUTO || isReadOnly || isLoading}
          className={`flex-1 px-3 py-1 text-xs rounded-lg transition-colors ${
            fan.mode === FanMode.AUTO
              ? 'bg-sky-500 text-white shadow-lg shadow-sky-500/30'
              : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
          } disabled:opacity-50 disabled:cursor-not-allowed`}
        >
          {isLoading && fan.mode !== FanMode.AUTO ? (
            <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-slate-300 border-t-transparent" />
          ) : (
            t('system:fanControl.card.auto')
          )}
        </button>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onModeChange(fan.fan_id, FanMode.MANUAL);
          }}
          disabled={fan.mode === FanMode.MANUAL || isReadOnly || isLoading}
          className={`flex-1 px-3 py-1 text-xs rounded-lg transition-colors ${
            fan.mode === FanMode.MANUAL
              ? 'bg-purple-500 text-white shadow-lg shadow-purple-500/30'
              : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
          } disabled:opacity-50 disabled:cursor-not-allowed`}
        >
          {isLoading && fan.mode !== FanMode.MANUAL ? (
            <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-slate-300 border-t-transparent" />
          ) : (
            t('system:fanControl.card.manual')
          )}
        </button>
      </div>

      {/* Manual PWM Slider */}
      {fan.mode === FanMode.MANUAL && (
        <div onClick={(e) => e.stopPropagation()}>
          <label className="text-xs text-slate-400 block mb-1">
            {t('system:fanControl.card.manualPwm')}: {localPWM}%
          </label>
          <input
            type="range"
            min={fan.min_pwm_percent}
            max={fan.max_pwm_percent}
            value={localPWM}
            onChange={(e) => handlePWMSliderChange(parseInt(e.target.value))}
            disabled={isReadOnly}
            className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed accent-purple-500"
          />
        </div>
      )}
    </div>
  );
}
