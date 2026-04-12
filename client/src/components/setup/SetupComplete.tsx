import { CheckCircle2, XCircle, LayoutDashboard } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '../ui/Button';

export interface SetupCompleteProps {
  configuredFeatures: string[];
  skippedFeatures: string[];
  onFinish: () => void;
}

export function SetupComplete({ configuredFeatures, skippedFeatures, onFinish }: SetupCompleteProps) {
  const { t } = useTranslation('setup');

  return (
    <div className="text-center">
      <div className="w-20 h-20 rounded-full bg-green-600/20 flex items-center justify-center mx-auto mb-6">
        <CheckCircle2 className="w-10 h-10 text-green-400" />
      </div>

      <h2 className="text-2xl font-bold text-slate-100 mb-2">{t('complete.title')}</h2>
      <p className="text-slate-400 text-sm mb-8">
        {t('complete.description')}
      </p>

      <div className="text-left space-y-2 mb-8">
        {configuredFeatures.length > 0 && (
          <div>
            <p className="text-xs font-medium text-slate-400 uppercase tracking-wide mb-2">
              {t('complete.configured')}
            </p>
            <div className="space-y-2">
              {configuredFeatures.map((key) => (
                <div
                  key={key}
                  className="flex items-center gap-3 px-4 py-2.5 rounded-lg bg-green-900/10 border border-green-700/40"
                >
                  <CheckCircle2 className="w-4 h-4 text-green-400 flex-shrink-0" />
                  <span className="text-sm text-slate-200">{t(`featureLabels.${key}`)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {skippedFeatures.length > 0 && (
          <div className="mt-4">
            <p className="text-xs font-medium text-slate-400 uppercase tracking-wide mb-2">
              {t('complete.skipped')}
            </p>
            <div className="space-y-2">
              {skippedFeatures.map((key) => (
                <div
                  key={key}
                  className="flex items-center gap-3 px-4 py-2.5 rounded-lg bg-slate-800/50 border border-slate-700"
                >
                  <XCircle className="w-4 h-4 text-slate-500 flex-shrink-0" />
                  <span className="text-sm text-slate-400">{t(`featureLabels.${key}`)}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <Button
        onClick={onFinish}
        size="lg"
        icon={<LayoutDashboard className="w-4 h-4" />}
        className="w-full"
      >
        {t('complete.toDashboard')}
      </Button>
    </div>
  );
}
