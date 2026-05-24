import { useTranslation } from 'react-i18next';

interface Props {
  value: number;
  onChange: (v: number) => void;
  disabled?: boolean;
}

export default function CurveEditorFlat({ value, onChange, disabled }: Props) {
  const { t } = useTranslation(['system']);
  return (
    <div className="space-y-2">
      <label className="text-sm font-medium text-white">
        {t('system:fanControl.curveTypes.flatLabel')}: {value}%
      </label>
      <input
        type="range"
        min={0}
        max={100}
        step={1}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        disabled={disabled}
        className="w-full"
      />
    </div>
  );
}
