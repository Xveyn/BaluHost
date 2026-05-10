import { useTranslation } from 'react-i18next';
import { Binary } from 'lucide-react';
import { useByteUnitMode } from '../../hooks/useByteUnitMode';
import type { ByteUnitMode } from '../../lib/byteUnits';

const MODES: { mode: ByteUnitMode; shortKey: string; hintKey: string }[] = [
  { mode: 'binary',  shortKey: 'userMenu.quickSettings.byteUnits.binaryShort',  hintKey: 'userMenu.quickSettings.byteUnits.binaryHint'  },
  { mode: 'decimal', shortKey: 'userMenu.quickSettings.byteUnits.decimalShort', hintKey: 'userMenu.quickSettings.byteUnits.decimalHint' },
];

export function ByteUnitSection() {
  const { t } = useTranslation('common');
  const [mode, setMode] = useByteUnitMode();

  return (
    <section className="px-3 py-2">
      <div className="flex items-center gap-2 mb-2 text-xs font-semibold text-slate-400 uppercase tracking-wider">
        <Binary className="w-3.5 h-3.5" />
        {t('userMenu.quickSettings.byteUnits.title')}
      </div>
      <div className="flex gap-2">
        {MODES.map((opt) => {
          const active = mode === opt.mode;
          return (
            <button
              key={opt.mode}
              type="button"
              aria-pressed={active}
              onClick={() => setMode(opt.mode)}
              className={`flex-1 flex flex-col items-center rounded-lg border px-3 py-1.5 text-sm transition ${
                active
                  ? 'border-sky-500/60 bg-sky-500/15 text-white'
                  : 'border-slate-700/60 bg-slate-800/40 text-slate-300 hover:border-slate-600 hover:bg-slate-800'
              }`}
            >
              <span className="font-medium">{t(opt.shortKey)}</span>
              <span className="text-[10px] text-slate-400 leading-tight">{t(opt.hintKey)}</span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
