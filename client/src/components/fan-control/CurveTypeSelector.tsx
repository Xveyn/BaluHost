import { useTranslation } from 'react-i18next';

export type CurveType = 'graph' | 'flat' | 'target' | 'mix' | 'sync';

interface Props {
  value: CurveType;
  onChange: (v: CurveType) => void;
  disabled?: boolean;
}

const TYPES: CurveType[] = ['graph', 'flat', 'target', 'mix', 'sync'];

export default function CurveTypeSelector({ value, onChange, disabled }: Props) {
  const { t } = useTranslation(['system']);
  return (
    <div className="inline-flex bg-slate-800/60 rounded p-1 gap-0.5">
      {TYPES.map((tp) => (
        <button
          key={tp}
          onClick={() => onChange(tp)}
          disabled={disabled}
          className={`px-3 py-1 text-sm rounded transition-colors ${
            value === tp ? 'bg-slate-900 shadow-sm font-medium text-white' : 'text-slate-400 hover:text-white'
          }`}
        >
          {t(`system:fanControl.curveTypes.${tp}`)}
        </button>
      ))}
    </div>
  );
}
