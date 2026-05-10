import { useTranslation } from 'react-i18next';
import { Globe } from 'lucide-react';
import { availableLanguages } from '../../i18n';

export function LanguageSection() {
  const { t, i18n } = useTranslation('common');

  const isActive = (code: string) =>
    i18n.language === code || i18n.language.startsWith(code + '-');

  return (
    <section className="px-3 py-2">
      <div className="flex items-center gap-2 mb-2 text-xs font-semibold text-slate-400 uppercase tracking-wider">
        <Globe className="w-3.5 h-3.5" />
        {t('userMenu.quickSettings.language.title')}
      </div>
      <div className="flex gap-2">
        {availableLanguages.map((lang) => {
          const active = isActive(lang.code);
          return (
            <button
              key={lang.code}
              type="button"
              aria-pressed={active}
              onClick={() => void i18n.changeLanguage(lang.code)}
              className={`flex-1 flex items-center justify-center gap-2 rounded-lg border px-3 py-1.5 text-sm transition ${
                active
                  ? 'border-sky-500/60 bg-sky-500/15 text-white'
                  : 'border-slate-700/60 bg-slate-800/40 text-slate-300 hover:border-slate-600 hover:bg-slate-800'
              }`}
            >
              <span className="text-base leading-none">{lang.flag}</span>
              <span>{lang.name}</span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
