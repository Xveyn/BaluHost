import { useState } from 'react';
import toast from 'react-hot-toast';
import { useTranslation } from 'react-i18next';
import { Zap } from 'lucide-react';
import type { AvailableDisk } from '../api/raid';
import { attachCache, type CacheMode } from '../api/ssd-cache';
import { formatBytes } from '../lib/formatters';

interface CacheSetupWizardProps {
  arrayName: string;
  availableDisks: AvailableDisk[];
  onClose: () => void;
  onSuccess: () => Promise<void>;
}

type Step = 'select-ssd' | 'configure-mode' | 'confirm';

const modeDescriptions: Record<string, { risk: string; benefit: string }> = {
  writethrough: {
    benefit: 'raid.cache.modeInfo.writethroughBenefit',
    risk: 'raid.cache.modeInfo.writethroughRisk',
  },
  writeback: {
    benefit: 'raid.cache.modeInfo.writebackBenefit',
    risk: 'raid.cache.modeInfo.writebackRisk',
  },
  writearound: {
    benefit: 'raid.cache.modeInfo.writearoundBenefit',
    risk: 'raid.cache.modeInfo.writearoundRisk',
  },
};

export default function CacheSetupWizard({ arrayName, availableDisks, onClose, onSuccess }: CacheSetupWizardProps) {
  const { t } = useTranslation(['system']);
  const [step, setStep] = useState<Step>('select-ssd');
  const [selectedSsd, setSelectedSsd] = useState<AvailableDisk | null>(null);
  const [selectedMode, setSelectedMode] = useState<CacheMode>('writethrough');
  const [busy, setBusy] = useState(false);

  // Filter: only SSDs that are not OS disk, not in RAID, not already a cache device
  const eligibleSsds = availableDisks.filter(
    (d) => d.is_ssd && !d.is_os_disk && !d.in_raid && !d.is_cache_device,
  );

  const handleAttach = async () => {
    if (!selectedSsd) return;
    setBusy(true);
    try {
      // Use first partition if available, otherwise device name
      const cacheDevice = selectedSsd.partitions.length > 0
        ? selectedSsd.partitions[0]
        : selectedSsd.name;

      const response = await attachCache({
        array: arrayName,
        cache_device: cacheDevice,
        mode: selectedMode,
      });
      toast.success(response.message);
      await onSuccess();
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t('system:raid.cache.messages.attachFailed'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 backdrop-blur-xl" onClick={onClose}>
      <div
        className="card w-full max-w-[95vw] sm:max-w-lg border-cyan-500/30 bg-slate-900/80 backdrop-blur-2xl shadow-[0_20px_70px_rgba(6,182,212,0.2)]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center gap-3 mb-4">
          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-br from-cyan-500 to-teal-600 shadow-lg shadow-cyan-500/30">
            <Zap className="h-4 w-4 text-white" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-white">
              {t('system:raid.cache.wizard.title')}
            </h3>
            <p className="text-xs text-slate-400">
              {t('system:raid.cache.wizard.subtitle', { array: arrayName })}
            </p>
          </div>
        </div>

        {/* Step indicators */}
        <div className="flex items-center gap-2 mb-5">
          {(['select-ssd', 'configure-mode', 'confirm'] as Step[]).map((s, i) => (
            <div key={s} className="flex items-center gap-2">
              <div
                className={`flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-bold ${
                  step === s
                    ? 'bg-cyan-500 text-white'
                    : i < ['select-ssd', 'configure-mode', 'confirm'].indexOf(step)
                      ? 'bg-cyan-500/20 text-cyan-300'
                      : 'bg-slate-800 text-slate-500'
                }`}
              >
                {i + 1}
              </div>
              {i < 2 && <div className="h-px w-8 bg-slate-700" />}
            </div>
          ))}
        </div>

        {/* Step 1: Select SSD */}
        {step === 'select-ssd' && (
          <div className="space-y-3">
            <p className="text-sm text-slate-300">{t('system:raid.cache.wizard.selectSsd')}</p>
            {eligibleSsds.length === 0 ? (
              <div className="rounded-xl border border-slate-800/60 bg-slate-900/60 px-4 py-6 text-center text-sm text-slate-400">
                {t('system:raid.cache.wizard.noSsds')}
              </div>
            ) : (
              <div className="space-y-2 max-h-48 overflow-y-auto">
                {eligibleSsds.map((disk) => (
                  <button
                    key={disk.name}
                    onClick={() => setSelectedSsd(disk)}
                    className={`w-full rounded-xl border px-4 py-3 text-left transition ${
                      selectedSsd?.name === disk.name
                        ? 'border-cyan-500/50 bg-cyan-500/10'
                        : 'border-slate-800/60 bg-slate-900/60 hover:border-slate-700'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-slate-200">/dev/{disk.name}</span>
                      <span className="text-xs text-slate-400">{formatBytes(disk.size_bytes)}</span>
                    </div>
                    {disk.model && (
                      <p className="mt-0.5 text-xs text-slate-500 truncate">{disk.model}</p>
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Step 2: Configure Mode */}
        {step === 'configure-mode' && (
          <div className="space-y-3">
            <p className="text-sm text-slate-300">{t('system:raid.cache.wizard.selectMode')}</p>
            {(['writethrough', 'writeback', 'writearound'] as CacheMode[]).map((mode) => (
              <button
                key={mode}
                onClick={() => setSelectedMode(mode)}
                className={`w-full rounded-xl border px-4 py-3 text-left transition ${
                  selectedMode === mode
                    ? 'border-cyan-500/50 bg-cyan-500/10'
                    : 'border-slate-800/60 bg-slate-900/60 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-slate-200">{mode}</span>
                  {mode === 'writethrough' && (
                    <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[10px] text-emerald-200">
                      {t('system:raid.cache.labels.recommended')}
                    </span>
                  )}
                  {mode === 'writeback' && (
                    <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[10px] text-amber-200">
                      {t('system:raid.cache.labels.riskWarning')}
                    </span>
                  )}
                </div>
                <p className="mt-1 text-xs text-emerald-400">
                  {t(`system:${modeDescriptions[mode].benefit}`)}
                </p>
                <p className="mt-0.5 text-xs text-slate-500">
                  {t(`system:${modeDescriptions[mode].risk}`)}
                </p>
              </button>
            ))}
          </div>
        )}

        {/* Step 3: Confirm */}
        {step === 'confirm' && selectedSsd && (
          <div className="space-y-3">
            <p className="text-sm text-slate-300">{t('system:raid.cache.wizard.confirmTitle')}</p>
            <div className="rounded-xl border border-slate-800/60 bg-slate-900/60 px-4 py-3 space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-slate-400">{t('system:raid.cache.wizard.array')}</span>
                <span className="text-slate-200 font-medium">{arrayName}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">{t('system:raid.cache.wizard.ssd')}</span>
                <span className="text-slate-200 font-medium">/dev/{selectedSsd.name}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">{t('system:raid.cache.wizard.mode')}</span>
                <span className="text-slate-200 font-medium">{selectedMode}</span>
              </div>
            </div>
            {selectedMode === 'writeback' && (
              <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-xs text-amber-200">
                {t('system:raid.cache.wizard.writebackWarning')}
              </div>
            )}
          </div>
        )}

        {/* Footer buttons */}
        <div className="flex justify-end gap-3 mt-5 pt-4 border-t border-slate-800/60">
          <button
            onClick={onClose}
            className="rounded-lg border border-slate-700/70 bg-slate-900/60 px-4 py-2 text-sm text-slate-200 transition hover:border-slate-600"
          >
            {t('system:raid.actions.cancel')}
          </button>
          {step !== 'select-ssd' && (
            <button
              onClick={() =>
                setStep(step === 'confirm' ? 'configure-mode' : 'select-ssd')
              }
              className="rounded-lg border border-slate-700/70 bg-slate-900/60 px-4 py-2 text-sm text-slate-200 transition hover:border-slate-600"
            >
              {t('system:raid.cache.wizard.back')}
            </button>
          )}
          {step === 'select-ssd' && (
            <button
              onClick={() => setStep('configure-mode')}
              disabled={!selectedSsd}
              className={`rounded-lg border px-4 py-2 text-sm transition ${
                !selectedSsd
                  ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                  : 'border-cyan-500/40 bg-cyan-500/15 text-cyan-100 hover:border-cyan-500/60'
              }`}
            >
              {t('system:raid.cache.wizard.next')}
            </button>
          )}
          {step === 'configure-mode' && (
            <button
              onClick={() => setStep('confirm')}
              className="rounded-lg border border-cyan-500/40 bg-cyan-500/15 px-4 py-2 text-sm text-cyan-100 transition hover:border-cyan-500/60"
            >
              {t('system:raid.cache.wizard.next')}
            </button>
          )}
          {step === 'confirm' && (
            <button
              onClick={handleAttach}
              disabled={busy}
              className={`rounded-lg border px-4 py-2 text-sm transition ${
                busy
                  ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                  : 'border-cyan-500/40 bg-cyan-500/15 text-cyan-100 hover:border-cyan-500/60'
              }`}
            >
              {busy ? t('system:raid.cache.wizard.attaching') : t('system:raid.cache.wizard.attach')}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
