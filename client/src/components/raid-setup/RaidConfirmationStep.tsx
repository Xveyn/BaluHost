import { type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import type { RaidLevelInfo } from './raidLevels';

interface RaidConfirmationStepProps {
  arrayName: string;
  onArrayNameChange: (name: string) => void;
  isArrayNameValid: boolean;
  raidInfo: RaidLevelInfo | undefined;
  capacity: string;
  selectedDisks: string[];
  busy: boolean;
  onBack: () => void;
  onCancel: () => void;
  onSubmit: (e: FormEvent) => void;
}

export default function RaidConfirmationStep({
  arrayName, onArrayNameChange, isArrayNameValid, raidInfo, capacity, selectedDisks, busy, onBack, onCancel, onSubmit,
}: RaidConfirmationStepProps) {
  const { t } = useTranslation('system');

  return (
    <form onSubmit={onSubmit}>
      <h3 className="text-xl font-semibold text-white">{t('raidWizard.confirm.title')}</h3>
      <p className="mt-2 text-sm text-slate-400">{t('raidWizard.confirm.description')}</p>

      <div className="mt-6 space-y-4">
        {/* Array Name */}
        <div>
          <label className="block text-sm font-medium text-slate-300">{t('raidWizard.confirm.arrayName')}</label>
          <input
            type="text"
            value={arrayName}
            onChange={(e) => onArrayNameChange(e.target.value)}
            required
            pattern="^md([0-9]+|_[a-zA-Z0-9]+)$"
            maxLength={32}
            placeholder="md0"
            className={`mt-1 w-full rounded-lg border bg-slate-950/70 px-3 py-2 text-sm text-slate-200 focus:outline-none ${
              arrayName && !isArrayNameValid
                ? 'border-red-500/60 focus:border-red-500'
                : 'border-slate-800 focus:border-sky-500'
            }`}
          />
          {arrayName && !isArrayNameValid && (
            <p className="mt-1 text-xs text-red-400">
              {t('raidWizard.confirm.invalidName', 'Name must be "md" + digits (e.g. md0) or "md_" + alphanumerics (e.g. md_backup).')}
            </p>
          )}
        </div>

        {/* Configuration Summary */}
        <div className="rounded-lg border border-slate-700/70 bg-slate-900/60 p-4">
          <h4 className="font-medium text-white">{t('raidWizard.confirm.summary')}</h4>

          <div className="mt-3 space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-slate-400">{t('raidWizard.confirm.raidLevelLabel')}</span>
              <span className="font-medium text-slate-200">{raidInfo?.name}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">{t('raidWizard.confirm.diskCount')}</span>
              <span className="font-medium text-slate-200">{selectedDisks.length}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">{t('raidWizard.confirm.availableCapacity')}</span>
              <span className="font-medium text-emerald-200">{capacity}</span>
            </div>
          </div>

          <div className="mt-4 border-t border-slate-800 pt-3">
            <p className="text-xs font-medium text-slate-400">{t('raidWizard.confirm.selectedDisks')}</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {selectedDisks.map((disk) => (
                <span
                  key={disk}
                  className="rounded-md bg-slate-800/60 px-2 py-1 text-xs font-medium text-slate-300"
                >
                  /dev/{disk}
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* Warning */}
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3">
          <div className="flex items-start gap-3">
            <svg
              className="mt-0.5 h-5 w-5 flex-shrink-0 text-amber-400"
              fill="currentColor"
              viewBox="0 0 20 20"
            >
              <path
                fillRule="evenodd"
                d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
                clipRule="evenodd"
              />
            </svg>
            <div>
              <p className="text-sm font-medium text-amber-200">{t('raidWizard.confirm.warningTitle')}</p>
              <p className="mt-1 text-xs text-amber-200/80">
                {t('raidWizard.confirm.warningMessage')}
              </p>
            </div>
          </div>
        </div>
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
            type="submit"
            disabled={busy || !isArrayNameValid}
            className={`rounded-lg border px-4 py-2 text-sm transition ${
              busy || !isArrayNameValid
                ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                : 'border-emerald-500/40 bg-emerald-500/15 text-emerald-100 hover:border-emerald-500/60'
            }`}
          >
            {busy ? t('raidWizard.creating') : t('raidWizard.createArray')}
          </button>
        </div>
      </div>
    </form>
  );
}
