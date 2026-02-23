import { useTranslation } from 'react-i18next';
import { Binary, Check } from 'lucide-react';
import { useByteUnitMode } from '../hooks/useByteUnitMode';
import type { ByteUnitMode } from '../lib/byteUnits';

const options: { mode: ByteUnitMode; example: string }[] = [
  { mode: 'binary',  example: '1 GiB = 1024 MiB' },
  { mode: 'decimal', example: '1 GB = 1000 MB' },
];

export default function ByteUnitSettings() {
  const { t } = useTranslation('settings');
  const [mode, setMode] = useByteUnitMode();

  return (
    <div className="card border-slate-800/60 bg-slate-900/55 mt-6">
      <h3 className="text-lg font-semibold mb-4 flex items-center">
        <Binary className="w-5 h-5 mr-2 text-sky-400" />
        {t('byteUnits.title')}
      </h3>

      <p className="text-slate-400 text-sm mb-6">
        {t('byteUnits.description')}
      </p>

      <div className="space-y-2">
        {options.map((opt) => (
          <button
            key={opt.mode}
            onClick={() => setMode(opt.mode)}
            className={`w-full flex items-center justify-between px-4 py-3 rounded-lg border transition-all ${
              mode === opt.mode
                ? 'border-sky-500 bg-sky-500/10 text-white'
                : 'border-slate-700 bg-slate-800/50 text-slate-300 hover:border-slate-600 hover:bg-slate-800'
            }`}
          >
            <div className="flex flex-col items-start">
              <span className="font-medium">{t(`byteUnits.${opt.mode}`)}</span>
              <span className="text-xs text-slate-500 mt-0.5">{opt.example}</span>
            </div>
            {mode === opt.mode && (
              <Check className="w-5 h-5 text-sky-400" />
            )}
          </button>
        ))}
      </div>
    </div>
  );
}
