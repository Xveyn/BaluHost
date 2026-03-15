import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { Shield, ShieldCheck, ShieldOff, Copy, RefreshCw, KeyRound } from 'lucide-react';
import { get2FAStatus, setup2FA, verifySetup2FA, disable2FA, regenerateBackupCodes, type TwoFactorStatus, type TwoFactorSetupData } from '../../api/two-factor';

export default function TwoFactorCard() {
  const { t } = useTranslation('settings');
  const [status, setStatus] = useState<TwoFactorStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [setupData, setSetupData] = useState<TwoFactorSetupData | null>(null);
  const [verifyCode, setVerifyCode] = useState('');
  const [backupCodes, setBackupCodes] = useState<string[] | null>(null);
  const [showDisable, setShowDisable] = useState(false);
  const [disablePassword, setDisablePassword] = useState('');
  const [disableCode, setDisableCode] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    loadStatus();
  }, []);

  const loadStatus = async () => {
    try {
      const data = await get2FAStatus();
      setStatus(data);
    } catch {
      // Failed to load 2FA status
    } finally {
      setLoading(false);
    }
  };

  const handleStartSetup = async () => {
    setError('');
    setSaving(true);
    try {
      const data = await setup2FA();
      setSetupData(data);
    } catch (err: unknown) {
      const detail = err instanceof Object && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : undefined;
      setError(detail || 'Failed to start 2FA setup');
    } finally {
      setSaving(false);
    }
  };

  const handleVerifySetup = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!setupData) return;
    setError('');
    setSaving(true);
    try {
      const result = await verifySetup2FA(setupData.secret, verifyCode);
      setBackupCodes(result.backup_codes);
      setSetupData(null);
      setVerifyCode('');
    } catch (err: unknown) {
      const detail = err instanceof Object && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : undefined;
      setError(detail || 'Invalid verification code');
    } finally {
      setSaving(false);
    }
  };

  const handleBackupCodesDone = () => {
    setBackupCodes(null);
    loadStatus();
  };

  const handleCopyBackupCodes = () => {
    if (backupCodes) {
      navigator.clipboard.writeText(backupCodes.join('\n'));
      toast.success(t('security.backupCodesCopied'));
    }
  };

  const handleDisable = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSaving(true);
    try {
      await disable2FA(disablePassword, disableCode);
      setShowDisable(false);
      setDisablePassword('');
      setDisableCode('');
      loadStatus();
    } catch (err: unknown) {
      const detail = err instanceof Object && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : undefined;
      setError(detail || 'Failed to disable 2FA');
    } finally {
      setSaving(false);
    }
  };

  const handleRegenerateBackupCodes = async () => {
    if (!confirm(t('security.regenerateWarning'))) return;
    setError('');
    setSaving(true);
    try {
      const result = await regenerateBackupCodes();
      setBackupCodes(result.backup_codes);
    } catch (err: unknown) {
      const detail = err instanceof Object && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : undefined;
      setError(detail || 'Failed to regenerate backup codes');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="card border-slate-800/60 bg-slate-900/55">
        <h3 className="text-base sm:text-lg font-semibold mb-3 sm:mb-4 flex items-center">
          <Shield className="w-4 h-4 sm:w-5 sm:h-5 mr-2 text-sky-400" />
          {t('security.twoFactor')}
        </h3>
        <p className="text-slate-400 text-sm">{t('profile.loading')}</p>
      </div>
    );
  }

  // Show backup codes after setup or regeneration
  if (backupCodes) {
    return (
      <div className="card border-slate-800/60 bg-slate-900/55">
        <h3 className="text-base sm:text-lg font-semibold mb-3 sm:mb-4 flex items-center">
          <KeyRound className="w-4 h-4 sm:w-5 sm:h-5 mr-2 text-amber-400" />
          {t('security.backupCodesTitle')}
        </h3>
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200 mb-4">
          {t('security.backupCodesWarning')}
        </div>
        <div className="grid grid-cols-2 gap-2 mb-4">
          {backupCodes.map((code, i) => (
            <div key={i} className="px-3 py-2 rounded-lg bg-slate-800/60 border border-slate-700/40 font-mono text-sm text-center">
              {code}
            </div>
          ))}
        </div>
        <div className="flex flex-col sm:flex-row gap-2">
          <button
            onClick={handleCopyBackupCodes}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2 text-sm text-white rounded-lg bg-slate-700 hover:bg-slate-600 transition-colors touch-manipulation active:scale-95"
          >
            <Copy className="w-4 h-4" />
            {t('security.copyBackupCodes')}
          </button>
          <button
            onClick={handleBackupCodesDone}
            className="flex-1 px-4 py-2 text-sm text-white rounded-lg bg-sky-500 hover:bg-sky-500-secondary transition-colors touch-manipulation active:scale-95"
          >
            {t('security.backupCodesDone')}
          </button>
        </div>
      </div>
    );
  }

  // Show setup flow (QR code + verify)
  if (setupData) {
    return (
      <div className="card border-slate-800/60 bg-slate-900/55">
        <h3 className="text-base sm:text-lg font-semibold mb-3 sm:mb-4 flex items-center">
          <Shield className="w-4 h-4 sm:w-5 sm:h-5 mr-2 text-sky-400" />
          {t('security.twoFactor')}
        </h3>

        {error && (
          <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200 mb-4">
            {error}
          </div>
        )}

        <p className="text-sm text-slate-100-secondary mb-4">{t('security.setupStep1')}</p>

        <div className="flex justify-center mb-4">
          <img
            src={setupData.qr_code}
            alt="TOTP QR Code"
            className="w-48 h-48 sm:w-56 sm:h-56 rounded-lg bg-white p-2"
          />
        </div>

        <div className="mb-4">
          <label className="block text-xs font-medium text-slate-100-tertiary mb-1">{t('security.manualEntry')}</label>
          <div className="px-3 py-2 rounded-lg bg-slate-800/60 border border-slate-700/40 font-mono text-sm break-all select-all">
            {setupData.secret}
          </div>
        </div>

        <p className="text-sm text-slate-100-secondary mb-3">{t('security.setupStep2')}</p>

        <form onSubmit={handleVerifySetup} className="space-y-3">
          <div>
            <label className="block text-sm font-medium mb-1">{t('security.verificationCode')}</label>
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
              onClick={() => { setSetupData(null); setVerifyCode(''); setError(''); }}
              className="flex-1 px-4 py-2 text-sm text-slate-300 rounded-lg bg-slate-700 hover:bg-slate-600 transition-colors touch-manipulation active:scale-95"
            >
              {t('security.cancel')}
            </button>
            <button
              type="submit"
              disabled={saving || verifyCode.length < 6}
              className="flex-1 px-4 py-2 text-sm text-white rounded-lg bg-sky-500 hover:bg-sky-500-secondary transition-colors disabled:opacity-50 touch-manipulation active:scale-95"
            >
              {saving ? t('security.verifying') : t('security.verify')}
            </button>
          </div>
        </form>
      </div>
    );
  }

  // Show disable form
  if (showDisable) {
    return (
      <div className="card border-slate-800/60 bg-slate-900/55">
        <h3 className="text-base sm:text-lg font-semibold mb-3 sm:mb-4 flex items-center">
          <ShieldOff className="w-4 h-4 sm:w-5 sm:h-5 mr-2 text-rose-400" />
          {t('security.disable2FA')}
        </h3>

        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200 mb-4">
          {t('security.disableWarning')}
        </div>

        {error && (
          <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200 mb-4">
            {error}
          </div>
        )}

        <form onSubmit={handleDisable} className="space-y-3">
          <div>
            <label className="block text-sm font-medium mb-1">{t('security.disablePassword')}</label>
            <input
              type="password"
              value={disablePassword}
              onChange={(e) => setDisablePassword(e.target.value)}
              className="input"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">{t('security.disableCode')}</label>
            <input
              type="text"
              value={disableCode}
              onChange={(e) => setDisableCode(e.target.value.replace(/\D/g, '').slice(0, 8))}
              className="input text-center font-mono tracking-wider"
              placeholder="000000"
              autoComplete="one-time-code"
              inputMode="numeric"
              required
            />
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => { setShowDisable(false); setError(''); setDisablePassword(''); setDisableCode(''); }}
              className="flex-1 px-4 py-2 text-sm text-slate-300 rounded-lg bg-slate-700 hover:bg-slate-600 transition-colors touch-manipulation active:scale-95"
            >
              {t('security.cancel')}
            </button>
            <button
              type="submit"
              disabled={saving}
              className="flex-1 px-4 py-2 text-sm text-white rounded-lg bg-rose-500 hover:bg-rose-600 transition-colors disabled:opacity-50 touch-manipulation active:scale-95"
            >
              {saving ? t('security.changing') : t('security.disable2FA')}
            </button>
          </div>
        </form>
      </div>
    );
  }

  // Default: show status
  return (
    <div className="card border-slate-800/60 bg-slate-900/55">
      <h3 className="text-base sm:text-lg font-semibold mb-3 sm:mb-4 flex items-center">
        <Shield className="w-4 h-4 sm:w-5 sm:h-5 mr-2 text-sky-400" />
        {t('security.twoFactor')}
      </h3>
      <p className="text-sm text-slate-100-secondary mb-4">{t('security.twoFactorDescription')}</p>

      {error && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200 mb-4">
          {error}
        </div>
      )}

      {status?.enabled ? (
        <div className="space-y-4">
          <div className="flex items-center gap-3 p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30">
            <ShieldCheck className="w-5 h-5 text-emerald-400 flex-shrink-0" />
            <div>
              <p className="text-sm font-medium text-emerald-300">{t('security.twoFactorEnabled')}</p>
              {status.enabled_at && (
                <p className="text-xs text-emerald-400/70">
                  {t('security.twoFactorEnabledSince')} {new Date(status.enabled_at).toLocaleDateString()}
                </p>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2 text-sm text-slate-100-secondary">
            <KeyRound className="w-4 h-4" />
            <span>{t('security.backupCodesRemaining', { count: status.backup_codes_remaining })}</span>
          </div>

          <div className="flex flex-col sm:flex-row gap-2">
            <button
              onClick={handleRegenerateBackupCodes}
              disabled={saving}
              className="flex items-center justify-center gap-2 px-4 py-2 text-sm text-slate-300 rounded-lg bg-slate-700 hover:bg-slate-600 transition-colors disabled:opacity-50 touch-manipulation active:scale-95"
            >
              <RefreshCw className="w-4 h-4" />
              {t('security.regenerateBackupCodes')}
            </button>
            <button
              onClick={() => { setShowDisable(true); setError(''); }}
              className="flex items-center justify-center gap-2 px-4 py-2 text-sm text-rose-300 rounded-lg bg-rose-500/10 border border-rose-500/30 hover:bg-rose-500/20 transition-colors touch-manipulation active:scale-95"
            >
              <ShieldOff className="w-4 h-4" />
              {t('security.disable2FA')}
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="flex items-center gap-3 p-3 rounded-lg bg-slate-800/60 border border-slate-700/40">
            <ShieldOff className="w-5 h-5 text-slate-400 flex-shrink-0" />
            <p className="text-sm text-slate-400">{t('security.twoFactorDisabled')}</p>
          </div>
          <button
            onClick={handleStartSetup}
            disabled={saving}
            className="flex items-center justify-center gap-2 px-4 py-2 text-sm text-white rounded-lg bg-sky-500 hover:bg-sky-500-secondary transition-colors disabled:opacity-50 touch-manipulation active:scale-95"
          >
            <ShieldCheck className="w-4 h-4" />
            {saving ? t('profile.loading') : t('security.enable2FA')}
          </button>
        </div>
      )}
    </div>
  );
}
