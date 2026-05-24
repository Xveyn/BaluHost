import { useTranslation } from 'react-i18next';
import type { FanCurveProfile } from '../../api/fan-control';

interface Props {
  profiles: FanCurveProfile[];
  curveAId: number | null;
  curveBId: number | null;
  fn: 'max' | 'sum';
  onChange: (next: { curveAId: number | null; curveBId: number | null; fn: 'max' | 'sum' }) => void;
  disabled?: boolean;
}

export default function CurveEditorMix({ profiles, curveAId, curveBId, fn, onChange, disabled }: Props) {
  const { t } = useTranslation(['system']);
  return (
    <div className="space-y-3">
      <p className="text-xs text-slate-400">{t('system:fanControl.curveTypes.mixDescription')}</p>
      <div className="grid grid-cols-2 gap-2">
        <select
          value={curveAId ?? ''}
          onChange={(e) => onChange({ curveAId: e.target.value ? Number(e.target.value) : null, curveBId, fn })}
          disabled={disabled}
          className="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-white"
        >
          <option value="">{t('system:fanControl.curveTypes.selectCurve')}</option>
          {profiles.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <select
          value={curveBId ?? ''}
          onChange={(e) => onChange({ curveAId, curveBId: e.target.value ? Number(e.target.value) : null, fn })}
          disabled={disabled}
          className="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-white"
        >
          <option value="">{t('system:fanControl.curveTypes.selectCurve')}</option>
          {profiles.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </div>
      <div className="flex gap-2">
        {(['max', 'sum'] as const).map((f) => (
          <button
            key={f}
            onClick={() => onChange({ curveAId, curveBId, fn: f })}
            disabled={disabled}
            className={`px-3 py-1 rounded text-sm ${fn === f ? 'bg-sky-500 text-white' : 'bg-slate-700 text-slate-300'}`}
          >
            {t(`system:fanControl.curveTypes.mixFn.${f}`)}
          </button>
        ))}
      </div>
    </div>
  );
}
