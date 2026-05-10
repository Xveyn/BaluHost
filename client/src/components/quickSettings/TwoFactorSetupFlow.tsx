import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { Copy, KeyRound } from 'lucide-react';
import {
  setup2FA,
  verifySetup2FA,
  type TwoFactorSetupData,
} from '../../api/two-factor';

export type TwoFactorSetupStep = 'loading' | 'verify' | 'backup-codes';

export interface TwoFactorSetupFlowProps {
  onComplete: () => void;
  onCancel: () => void;
  /** Optional callback whenever the internal step changes. Used by the
   * parent (e.g., a Modal) to suppress accidental dismissal during the
   * backup-codes step. */
  onStepChange?: (step: TwoFactorSetupStep) => void;
}

export function TwoFactorSetupFlow({
  onComplete,
  onCancel,
  onStepChange,
}: TwoFactorSetupFlowProps) {
  const { t } = useTranslation('settings');
  const [step, setStep] = useState<TwoFactorSetupStep>('loading');
  const [setupData, setSetupData] = useState<TwoFactorSetupData | null>(null);
  const [verifyCode, setVerifyCode] = useState('');
  const [backupCodes, setBackupCodes] = useState<string[]>([]);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  // Trigger setup once on mount
  useEffect(() => {
    let cancelled = false;
    setSaving(true);
    setup2FA()
      .then((data) => {
        if (cancelled) return;
        setSetupData(data);
        setStep('verify');
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const detail =
          err instanceof Object && 'response' in err
            ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
            : undefined;
        setError(detail || 'Failed to start 2FA setup');
      })
      .finally(() => {
        if (!cancelled) setSaving(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Notify parent of step transitions
  useEffect(() => {
    onStepChange?.(step);
  }, [step, onStepChange]);

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!setupData) return;
    setError('');
    setSaving(true);
    try {
      const result = await verifySetup2FA(setupData.secret, verifyCode);
      setBackupCodes(result.backup_codes);
      setVerifyCode('');
      setStep('backup-codes');
    } catch (err: unknown) {
      const detail =
        err instanceof Object && 'response' in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined;
      setError(detail || 'Invalid verification code');
    } finally {
      setSaving(false);
    }
  };

  const handleCopyBackupCodes = () => {
    void navigator.clipboard.writeText(backupCodes.join('\n'));
    toast.success(t('security.backupCodesCopied'));
  };

  // Loading / initial setup call in flight
  if (step === 'loading' || !setupData) {
    return (
      <div className="text-sm text-slate-300 py-4">
        {error ? (
          <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-rose-200">
            {error}
          </div>
        ) : (
          t('profile.loading')
        )}
      </div>
    );
  }

  if (step === 'backup-codes') {
    return (
      <div>
        <div className="flex items-center gap-2 mb-3">
          <KeyRound className="w-5 h-5 text-amber-400" />
          <h4 className="text-base font-semibold text-slate-100">
            {t('security.backupCodesTitle')}
          </h4>
        </div>
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200 mb-4">
          {t('security.backupCodesWarning')}
        </div>
        <div className="grid grid-cols-2 gap-2 mb-4">
          {backupCodes.map((code) => (
            <div
              key={code}
              className="px-3 py-2 rounded-lg bg-slate-800/60 border border-slate-700/40 font-mono text-sm text-center"
            >
              {code}
            </div>
          ))}
        </div>
        <div className="flex flex-col sm:flex-row gap-2">
          <button
            type="button"
            onClick={handleCopyBackupCodes}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2 text-sm text-white rounded-lg bg-slate-700 hover:bg-slate-600 transition-colors"
          >
            <Copy className="w-4 h-4" />
            {t('security.copyBackupCodes')}
          </button>
          <button
            type="button"
            onClick={onComplete}
            className="flex-1 px-4 py-2 text-sm text-white rounded-lg bg-sky-500 hover:bg-sky-500-secondary transition-colors"
          >
            {t('security.backupCodesDone')}
          </button>
        </div>
      </div>
    );
  }

  // step === 'verify'
  return (
    <div>
      {error && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200 mb-4">
          {error}
        </div>
      )}

      <p className="text-sm text-slate-300 mb-4">{t('security.setupStep1')}</p>

      <div className="flex justify-center mb-4">
        <img
          src={setupData.qr_code}
          alt="TOTP QR Code"
          className="w-48 h-48 sm:w-56 sm:h-56 rounded-lg bg-white p-2"
        />
      </div>

      <div className="mb-4">
        <label className="block text-xs font-medium text-slate-400 mb-1">
          {t('security.manualEntry')}
        </label>
        <div className="px-3 py-2 rounded-lg bg-slate-800/60 border border-slate-700/40 font-mono text-sm break-all select-all">
          {setupData.secret}
        </div>
      </div>

      <p className="text-sm text-slate-300 mb-3">{t('security.setupStep2')}</p>

      <form onSubmit={handleVerify} className="space-y-3">
        <div>
          <label className="block text-sm font-medium mb-1">
            {t('security.verificationCode')}
          </label>
          <input
            type="text"
            value={verifyCode}
            onChange={(e) => setVerifyCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
            className="input text-center text-xl tracking-[0.4em] font-mono"
            placeholder="000000"
            autoComplete="one-time-code"
            inputMode="numeric"
            required
          />
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="flex-1 px-4 py-2 text-sm text-slate-300 rounded-lg bg-slate-700 hover:bg-slate-600 transition-colors"
          >
            {t('security.cancel')}
          </button>
          <button
            type="submit"
            disabled={saving || verifyCode.length < 6}
            className="flex-1 px-4 py-2 text-sm text-white rounded-lg bg-sky-500 hover:bg-sky-500-secondary transition-colors disabled:opacity-50"
          >
            {saving ? t('security.verifying') : t('security.verify')}
          </button>
        </div>
      </form>
    </div>
  );
}
