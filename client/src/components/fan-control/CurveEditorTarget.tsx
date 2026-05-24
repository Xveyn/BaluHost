import { useTranslation } from 'react-i18next';

interface Props {
  targetTemp: number;
  targetPwm: number;
  onChange: (next: { targetTemp: number; targetPwm: number }) => void;
  disabled?: boolean;
}

export default function CurveEditorTarget({ targetTemp, targetPwm, onChange, disabled }: Props) {
  const { t } = useTranslation(['system']);
  return (
    <div className="space-y-3">
      <p className="text-xs text-slate-400">{t('system:fanControl.curveTypes.targetDescription')}</p>
      <div>
        <label className="text-sm font-medium text-white">
          {t('system:fanControl.curveTypes.targetTemp')}: {targetTemp.toFixed(0)}°C
        </label>
        <input
          type="range" min={20} max={100} step={1}
          value={targetTemp}
          onChange={(e) => onChange({ targetTemp: Number(e.target.value), targetPwm })}
          disabled={disabled}
          className="w-full"
        />
      </div>
      <div>
        <label className="text-sm font-medium text-white">
          {t('system:fanControl.curveTypes.targetPwm')}: {targetPwm}%
        </label>
        <input
          type="range" min={0} max={100} step={1}
          value={targetPwm}
          onChange={(e) => onChange({ targetTemp, targetPwm: Number(e.target.value) })}
          disabled={disabled}
          className="w-full"
        />
      </div>
    </div>
  );
}
