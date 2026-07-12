import { useTranslation } from 'react-i18next';
import { RAID_LEVELS } from './raidLevels';

interface RaidLevelSelectionStepProps {
  selectedDisks: string[];
  selectedRaidLevel: string;
  onSelectLevel: (level: string) => void;
  canProceed: boolean;
  onBack: () => void;
  onCancel: () => void;
  onNext: () => void;
}

export default function RaidLevelSelectionStep({
  selectedDisks, selectedRaidLevel, onSelectLevel, canProceed, onBack, onCancel, onNext,
}: RaidLevelSelectionStepProps) {
  const { t } = useTranslation('system');
  const availableRaidLevels = RAID_LEVELS.filter((r) => selectedDisks.length >= r.minDisks);

  return (
    <div>
      <h3 className="text-xl font-semibold text-white">{t('raidWizard.raidLevel.title')}</h3>
      <p className="mt-1 text-sm text-slate-400">
        {t('raidWizard.raidLevel.description', { count: selectedDisks.length })}
      </p>

      <div className="mt-6 space-y-3">
        {availableRaidLevels.map((raid) => (
          <button
            key={raid.level}
            type="button"
            onClick={() => onSelectLevel(raid.level)}
            className={`w-full rounded-lg border p-4 text-left transition ${
              selectedRaidLevel === raid.level
                ? 'border-sky-500 bg-sky-500/15'
                : 'border-slate-700/70 bg-slate-900/60 hover:border-slate-600'
            }`}
          >
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <p className="font-semibold text-white">{raid.name}</p>
                  {raid.recommended && (
                    <span className="rounded-full bg-emerald-500/20 px-2 py-0.5 text-xs font-medium text-emerald-200">
                      {t('raidWizard.raidLevel.recommended')}
                    </span>
                  )}
                </div>
                <p className="mt-1 text-sm text-slate-400">{raid.description}</p>

                <div className="mt-3 grid grid-cols-2 gap-3 text-xs">
                  <div>
                    <p className="text-slate-500">{t('raidWizard.raidLevel.redundancy')}</p>
                    <p className="text-slate-300">{raid.redundancy}</p>
                  </div>
                  <div>
                    <p className="text-slate-500">{t('raidWizard.raidLevel.capacity')}</p>
                    <p className="text-slate-300">{raid.capacity}</p>
                  </div>
                  <div className="col-span-2">
                    <p className="text-slate-500">{t('raidWizard.raidLevel.performance')}</p>
                    <p className="text-slate-300">{raid.performance}</p>
                  </div>
                </div>
              </div>
              <div
                className={`ml-4 flex h-5 w-5 items-center justify-center rounded-full border-2 transition ${
                  selectedRaidLevel === raid.level
                    ? 'border-sky-500 bg-sky-500'
                    : 'border-slate-600 bg-slate-900'
                }`}
              >
                {selectedRaidLevel === raid.level && (
                  <div className="h-2 w-2 rounded-full bg-white" />
                )}
              </div>
            </div>
          </button>
        ))}
      </div>

      <div className="mt-6 flex justify-between gap-3">
        <button
          type="button"
          onClick={onBack}
          className="rounded-lg border border-slate-700/70 bg-slate-900/60 px-4 py-2 text-sm text-slate-200 transition hover:border-slate-600"
        >
          {t('raidWizard.back')}
        </button>
        <div className="flex gap-3">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg border border-slate-700/70 bg-slate-900/60 px-4 py-2 text-sm text-slate-200 transition hover:border-slate-600"
          >
            {t('raidWizard.cancel')}
          </button>
          <button
            type="button"
            onClick={onNext}
            disabled={!canProceed}
            className={`rounded-lg border px-4 py-2 text-sm transition ${
              canProceed
                ? 'border-sky-500/40 bg-sky-500/15 text-sky-100 hover:border-sky-500/60'
                : 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
            }`}
          >
            {t('raidWizard.next')}
          </button>
        </div>
      </div>
    </div>
  );
}
