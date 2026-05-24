import { useTranslation } from 'react-i18next';
import type { FanInfo } from '../../api/fan-control';

interface Props {
  allFans: FanInfo[];
  currentFanId: string;
  syncFanId: string | null;
  onChange: (v: string | null) => void;
  disabled?: boolean;
}

export default function CurveEditorSync({ allFans, currentFanId, syncFanId, onChange, disabled }: Props) {
  const { t } = useTranslation(['system']);
  return (
    <div className="space-y-2">
      <p className="text-xs text-slate-400">{t('system:fanControl.curveTypes.syncDescription')}</p>
      <select
        value={syncFanId ?? ''}
        onChange={(e) => onChange(e.target.value || null)}
        disabled={disabled}
        className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-white"
      >
        <option value="">{t('system:fanControl.curveTypes.selectFan')}</option>
        {allFans.filter((f) => f.fan_id !== currentFanId).map((f) => (
          <option key={f.fan_id} value={f.fan_id}>{f.name}</option>
        ))}
      </select>
    </div>
  );
}
