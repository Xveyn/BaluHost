import { useTranslation } from 'react-i18next';
import { Globe, Check } from 'lucide-react';
import { availableLanguages } from '../i18n';

export default function LanguageSettings() {
  const { t, i18n } = useTranslation('settings');
  
  const handleLanguageChange = (langCode: string) => {
    i18n.changeLanguage(langCode);
  };

  return (
    <div className="card border-slate-800/60 bg-slate-900/55">
      <h3 className="text-lg font-semibold mb-4 flex items-center">
        <Globe className="w-5 h-5 mr-2 text-sky-400" />
        {t('language.title')}
      </h3>
      
      <p className="text-slate-400 text-sm mb-6">
        {t('language.description')}
      </p>
      
      <div className="space-y-2">
        {availableLanguages.map((lang) => (
          <button
            key={lang.code}
            onClick={() => handleLanguageChange(lang.code)}
            className={`w-full flex items-center justify-between px-4 py-3 rounded-lg border transition-all ${
              i18n.language === lang.code || i18n.language.startsWith(lang.code + '-')
                ? 'border-sky-500 bg-sky-500/10 text-white'
                : 'border-slate-700 bg-slate-800/50 text-slate-300 hover:border-slate-600 hover:bg-slate-800'
            }`}
          >
            <div className="flex items-center gap-3">
              <span className="text-2xl">{lang.flag}</span>
              <span className="font-medium">{lang.name}</span>
            </div>
            {(i18n.language === lang.code || i18n.language.startsWith(lang.code + '-')) && (
              <Check className="w-5 h-5 text-sky-400" />
            )}
          </button>
        ))}
      </div>
      
      <p className="text-slate-500 text-xs mt-4">
        {t('language.current')}: {availableLanguages.find(l => 
          i18n.language === l.code || i18n.language.startsWith(l.code + '-')
        )?.name || i18n.language}
      </p>
    </div>
  );
}
