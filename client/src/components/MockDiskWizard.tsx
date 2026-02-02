import { type FormEvent, useState } from 'react';
import toast from 'react-hot-toast';
import { useTranslation } from 'react-i18next';

interface MockDiskWizardProps {
  onClose: () => void;
  onSuccess: () => Promise<void>;
}

const DISK_LETTERS = ['h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z'];

export default function MockDiskWizard({ onClose, onSuccess }: MockDiskWizardProps) {
  const { t } = useTranslation('system');
  const [step, setStep] = useState<number>(1);
  const [busy, setBusy] = useState<boolean>(false);
  
  // Form State
  const [diskLetter, setDiskLetter] = useState<string>('h');
  const [diskSize, setDiskSize] = useState<number>(10);
  const [diskName, setDiskName] = useState<string>('Mock Dev Disk');
  const [diskPurpose, setDiskPurpose] = useState<string>('storage');

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);

    try {
      // Dev-Mode API Call (to be implemented in backend)
      const response = await fetch('/api/system/raid/dev/add-mock-disk', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          letter: diskLetter,
          size_gb: diskSize,
          name: diskName,
          purpose: diskPurpose,
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to add mock disk');
      }

      const result = await response.json();
      toast.success(result.message || t('mockDisk.successMessage'));
      await onSuccess();
      onClose();
    } catch (err) {
      const message = err instanceof Error ? err.message : t('mockDisk.errorMessage');
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  const purposeOptions = [
    { value: 'storage', label: t('mockDisk.purpose.storage'), icon: '💾', desc: t('mockDisk.purpose.storageDesc') },
    { value: 'backup', label: t('mockDisk.purpose.backup'), icon: '🔄', desc: t('mockDisk.purpose.backupDesc') },
    { value: 'archive', label: t('mockDisk.purpose.archive'), icon: '📦', desc: t('mockDisk.purpose.archiveDesc') },
    { value: 'cache', label: t('mockDisk.purpose.cache'), icon: '⚡', desc: t('mockDisk.purpose.cacheDesc') },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4" onClick={onClose}>
      <div className="w-full max-w-2xl rounded-2xl border border-slate-800/60 bg-slate-900/98 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="border-b border-slate-800/60 px-6 py-5">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-2xl font-semibold text-white">{t('mockDisk.title')}</h2>
              <p className="mt-1 text-sm text-slate-400">{t('mockDisk.subtitle')}</p>
            </div>
            <button
              onClick={onClose}
              className="rounded-lg p-2 text-slate-400 transition hover:bg-slate-800/60 hover:text-white"
            >
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Progress Steps */}
          <div className="mt-6 flex items-center gap-2">
            <div className={`flex h-8 w-8 items-center justify-center rounded-full text-xs font-medium transition ${
              step === 1 ? 'bg-sky-500 text-white' : 'bg-slate-800 text-slate-400'
            }`}>
              1
            </div>
            <div className={`h-1 flex-1 rounded-full transition ${
              step > 1 ? 'bg-sky-500' : 'bg-slate-800'
            }`} />
            <div className={`flex h-8 w-8 items-center justify-center rounded-full text-xs font-medium transition ${
              step === 2 ? 'bg-sky-500 text-white' : 'bg-slate-800 text-slate-400'
            }`}>
              2
            </div>
            <div className={`h-1 flex-1 rounded-full transition ${
              step > 2 ? 'bg-sky-500' : 'bg-slate-800'
            }`} />
            <div className={`flex h-8 w-8 items-center justify-center rounded-full text-xs font-medium transition ${
              step === 3 ? 'bg-sky-500 text-white' : 'bg-slate-800 text-slate-400'
            }`}>
              3
            </div>
          </div>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="px-6 py-6">
            {/* Step 1: Disk Letter & Size */}
            {step === 1 && (
              <div className="space-y-6">
                <div>
                  <h3 className="text-lg font-semibold text-white">{t('mockDisk.step1.title')}</h3>
                  <p className="mt-1 text-sm text-slate-400">{t('mockDisk.step1.description')}</p>
                </div>

                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-slate-300">{t('mockDisk.step1.deviceLetter')}</label>
                    <p className="mt-1 text-xs text-slate-500">{t('mockDisk.step1.deviceLetterHint', { letter: diskLetter })}</p>
                    <select
                      value={diskLetter}
                      onChange={(e) => setDiskLetter(e.target.value)}
                      className="mt-2 w-full rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
                    >
                      {DISK_LETTERS.map((letter) => (
                        <option key={letter} value={letter}>
                          sd{letter} (/dev/sd{letter})
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-slate-300">{t('mockDisk.step1.diskSize')}</label>
                    <div className="mt-2 flex items-center gap-3">
                      <input
                        type="number"
                        min="1"
                        max="1000"
                        value={diskSize}
                        onChange={(e) => setDiskSize(Number(e.target.value))}
                        className="flex-1 rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
                      />
                      <span className="text-sm text-slate-400">GB</span>
                    </div>
                    <p className="mt-1 text-xs text-slate-500">{t('mockDisk.step1.sizeRecommendation')}</p>
                  </div>

                  <div className="rounded-xl border border-sky-500/30 bg-sky-500/10 px-4 py-3">
                    <div className="flex items-start gap-3">
                      <svg className="mt-0.5 h-5 w-5 flex-shrink-0 text-sky-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      <div className="text-sm text-sky-200">
                        <p className="font-medium">{t('mockDisk.step1.devModeNotice')}</p>
                        <p className="mt-1 text-xs text-sky-300">
                          {t('mockDisk.step1.devModeNoticeDesc')}
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Step 2: Disk Name & Purpose */}
            {step === 2 && (
              <div className="space-y-6">
                <div>
                  <h3 className="text-lg font-semibold text-white">{t('mockDisk.step2.title')}</h3>
                  <p className="mt-1 text-sm text-slate-400">{t('mockDisk.step2.description')}</p>
                </div>

                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-slate-300">{t('mockDisk.step2.modelName')}</label>
                    <input
                      type="text"
                      value={diskName}
                      onChange={(e) => setDiskName(e.target.value)}
                      placeholder="e.g. BaluHost Dev Disk 10GB"
                      className="mt-2 w-full rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
                    />
                    <p className="mt-1 text-xs text-slate-500">{t('mockDisk.step2.modelNameHint')}</p>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-slate-300">{t('mockDisk.step2.purpose')}</label>
                    <div className="mt-2 grid grid-cols-2 gap-3">
                      {purposeOptions.map((option) => (
                        <button
                          key={option.value}
                          type="button"
                          onClick={() => setDiskPurpose(option.value)}
                          className={`rounded-xl border p-4 text-left transition ${
                            diskPurpose === option.value
                              ? 'border-sky-500/50 bg-sky-500/15 shadow-lg shadow-sky-500/20'
                              : 'border-slate-800 bg-slate-900/60 hover:border-slate-700'
                          }`}
                        >
                          <div className="text-2xl">{option.icon}</div>
                          <div className="mt-2 font-medium text-slate-200">{option.label}</div>
                          <div className="mt-1 text-xs text-slate-400">{option.desc}</div>
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Step 3: Summary */}
            {step === 3 && (
              <div className="space-y-6">
                <div>
                  <h3 className="text-lg font-semibold text-white">{t('mockDisk.step3.title')}</h3>
                  <p className="mt-1 text-sm text-slate-400">{t('mockDisk.step3.description')}</p>
                </div>

                <div className="space-y-3 rounded-xl border border-slate-800 bg-slate-900/60 p-5">
                  <div className="flex items-center justify-between border-b border-slate-800/60 pb-3">
                    <span className="text-sm text-slate-400">{t('mockDisk.step3.deviceName')}</span>
                    <span className="font-medium text-slate-200">/dev/sd{diskLetter}</span>
                  </div>
                  <div className="flex items-center justify-between border-b border-slate-800/60 pb-3">
                    <span className="text-sm text-slate-400">{t('mockDisk.step3.size')}</span>
                    <span className="font-medium text-slate-200">{diskSize} GB</span>
                  </div>
                  <div className="flex items-center justify-between border-b border-slate-800/60 pb-3">
                    <span className="text-sm text-slate-400">{t('mockDisk.step3.modelName')}</span>
                    <span className="font-medium text-slate-200">{diskName}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-slate-400">{t('mockDisk.step3.purpose')}</span>
                    <span className="font-medium text-slate-200">
                      {purposeOptions.find(p => p.value === diskPurpose)?.label}
                    </span>
                  </div>
                </div>

                <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3">
                  <div className="flex items-start gap-3">
                    <svg className="mt-0.5 h-5 w-5 flex-shrink-0 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
                    </svg>
                    <div className="text-sm text-amber-200">
                      <p className="font-medium">{t('mockDisk.step3.important')}</p>
                      <p className="mt-1 text-xs text-amber-300">
                        {t('mockDisk.step3.importantDesc')}
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Footer Actions */}
          <div className="flex items-center justify-between border-t border-slate-800/60 px-6 py-5">
            <button
              type="button"
              onClick={() => {
                if (step > 1) {
                  setStep(step - 1);
                } else {
                  onClose();
                }
              }}
              className="rounded-lg border border-slate-700/70 bg-slate-900/60 px-4 py-2 text-sm text-slate-200 transition hover:border-slate-600"
            >
              {step === 1 ? t('mockDisk.cancel') : t('mockDisk.back')}
            </button>

            {step < 3 ? (
              <button
                type="button"
                onClick={() => setStep(step + 1)}
                className="rounded-lg border border-sky-500/50 bg-sky-500/15 px-6 py-2 text-sm font-medium text-sky-100 transition hover:border-sky-500/70 hover:bg-sky-500/20"
              >
                {t('mockDisk.next')}
              </button>
            ) : (
              <button
                type="submit"
                disabled={busy}
                className={`rounded-lg border px-6 py-2 text-sm font-medium transition ${
                  busy
                    ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                    : 'border-emerald-500/50 bg-emerald-500/15 text-emerald-100 hover:border-emerald-500/70 hover:bg-emerald-500/20'
                }`}
              >
                {busy ? t('mockDisk.adding') : t('mockDisk.addMockDisk')}
              </button>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}
