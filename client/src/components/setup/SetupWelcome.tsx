import { ArrowRight, FolderOpen, HardDrive, Shield, Activity, Smartphone, Clock, BookOpen } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import logoMark from '../../assets/baluhost-logo.png';
import { Button } from '../ui/Button';
import { availableLanguages } from '../../i18n';

export interface SetupWelcomeProps {
  onStart: () => void;
}

const FEATURE_KEYS = [
  { icon: FolderOpen, key: 'fileManagement' },
  { icon: HardDrive, key: 'raidStorage' },
  { icon: Shield, key: 'vpnAccess' },
  { icon: Activity, key: 'systemMonitoring' },
  { icon: Smartphone, key: 'mobileDesktop' },
  { icon: Clock, key: 'backupVersions' },
  { icon: BookOpen, key: 'userManual' },
] as const;

export function SetupWelcome({ onStart }: SetupWelcomeProps) {
  const { t, i18n } = useTranslation('setup');

  const currentLang = i18n.language?.startsWith('de') ? 'de' : 'en';

  return (
    <div className="text-center">
      {/* Language selector */}
      <div className="flex justify-end mb-4 -mt-1">
        <div className="inline-flex rounded-lg border border-slate-700/60 bg-slate-800/50 p-0.5">
          {availableLanguages.map((lang) => (
            <button
              key={lang.code}
              onClick={() => i18n.changeLanguage(lang.code)}
              className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors ${
                currentLang === lang.code
                  ? 'bg-sky-500/20 text-sky-300 border border-sky-500/40'
                  : 'text-slate-400 hover:text-slate-200 border border-transparent'
              }`}
            >
              {lang.flag} {lang.code.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      <div className="glow-ring h-20 w-20 mx-auto mb-6">
        <div className="flex h-[72px] w-[72px] items-center justify-center rounded-full bg-slate-950 p-[2px] shadow-xl">
          <img src={logoMark} alt="BaluHost logo" className="h-full w-full rounded-full" />
        </div>
      </div>

      <h2 className="text-2xl font-semibold text-slate-100 mb-2">
        {t('welcome.title')}
      </h2>
      <p className="text-slate-400 text-sm max-w-lg mx-auto mb-8">
        {t('welcome.description')}
      </p>

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-8 text-left">
        {FEATURE_KEYS.map(({ icon: Icon, key }) => (
          <div
            key={key}
            className="rounded-xl border border-slate-800/60 bg-slate-800/30 p-3 backdrop-blur-sm"
          >
            <div className="w-8 h-8 rounded-lg bg-sky-500/10 flex items-center justify-center mb-2">
              <Icon className="w-4 h-4 text-sky-400" />
            </div>
            <p className="text-sm font-medium text-slate-200">{t(`features.${key}.title`)}</p>
            <p className="text-xs text-slate-400 mt-0.5">{t(`features.${key}.desc`)}</p>
          </div>
        ))}
      </div>

      <Button
        onClick={onStart}
        size="lg"
        icon={<ArrowRight className="w-4 h-4" />}
        className="w-full sm:w-auto"
      >
        {t('welcome.startButton')}
      </Button>
    </div>
  );
}
