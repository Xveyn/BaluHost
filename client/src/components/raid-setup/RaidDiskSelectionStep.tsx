import { useTranslation } from 'react-i18next';
import type { AvailableDisk } from '../../api/raid';
import { formatBytes } from '../../lib/formatters';

interface RaidDiskSelectionStepProps {
  freeDisks: AvailableDisk[];
  selectedDisks: string[];
  onToggleDisk: (name: string) => void;
  canProceed: boolean;
  onCancel: () => void;
  onNext: () => void;
}

export default function RaidDiskSelectionStep({
  freeDisks, selectedDisks, onToggleDisk, canProceed, onCancel, onNext,
}: RaidDiskSelectionStepProps) {
  const { t } = useTranslation('system');

  return (
    <div>
      <h3 className="text-xl font-semibold text-white">{t('raidWizard.selectDisks.title')}</h3>
      <p className="mt-1 text-sm text-slate-400">
        {t('raidWizard.selectDisks.description')}
      </p>

      <div className="mt-6 space-y-3">
        {freeDisks.length === 0 ? (
          <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-center">
            <p className="text-sm text-amber-200">
              {t('raidWizard.selectDisks.noDisks')}
            </p>
          </div>
        ) : (
          freeDisks.map((disk) => (
            <button
              key={disk.name}
              type="button"
              onClick={() => onToggleDisk(disk.name)}
              className={`w-full rounded-lg border p-4 text-left transition ${
                selectedDisks.includes(disk.name)
                  ? 'border-sky-500 bg-sky-500/15'
                  : 'border-slate-700/70 bg-slate-900/60 hover:border-slate-600'
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <div
                    className={`flex h-5 w-5 items-center justify-center rounded border-2 transition ${
                      selectedDisks.includes(disk.name)
                        ? 'border-sky-500 bg-sky-500'
                        : 'border-slate-600 bg-slate-900'
                    }`}
                  >
                    {selectedDisks.includes(disk.name) && (
                      <svg className="h-3 w-3 text-white" fill="currentColor" viewBox="0 0 20 20">
                        <path
                          fillRule="evenodd"
                          d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                          clipRule="evenodd"
                        />
                      </svg>
                    )}
                  </div>
                  <div>
                    <p className="font-medium text-slate-200">/dev/{disk.name}</p>
                    <p className="text-xs text-slate-400">{disk.model || t('raidWizard.selectDisks.unknownModel')}</p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-sm font-medium text-slate-300">{formatBytes(disk.size_bytes)}</p>
                  {disk.partitions.length > 0 && (
                    <p className="text-xs text-slate-500">
                      {t('raidWizard.selectDisks.partitions', { count: disk.partitions.length })}
                    </p>
                  )}
                </div>
              </div>
            </button>
          ))
        )}
      </div>

      {selectedDisks.length > 0 && (
        <div className="mt-4 rounded-lg border border-slate-700/70 bg-slate-900/60 p-3">
          <p className="text-sm text-slate-300">
            {t('raidWizard.selectDisks.disksSelected', { count: selectedDisks.length })}
          </p>
        </div>
      )}

      <div className="mt-6 flex justify-end gap-3">
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
  );
}
