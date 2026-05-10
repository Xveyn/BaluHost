import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { Shield, ShieldCheck, ShieldOff, RefreshCw, KeyRound, Copy } from 'lucide-react';
import {
  get2FAStatus,
  disable2FA,
  regenerateBackupCodes,
  type TwoFactorStatus,
} from '../../api/two-factor';
import { TwoFactorSetupFlow } from '../quickSettings/TwoFactorSetupFlow';
import { refreshStatus as refreshTwoFactorCache } from '../quickSettings/twoFactorStatusStore';

export default function TwoFactorCard() {
  const { t } = useTranslation('settings');
  const [status, setStatus] = useState<TwoFactorStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [showSetup, setShowSetup] = useState(false);
  const [regeneratedCodes, setRegeneratedCodes] = useState<string[] | null>(null);
  const [showDisable, setShowDisable] = useState(false);
  const [disablePassword, setDisablePassword] = useState('');
  const [disableCode, setDisableCode] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    void loadStatus();
  }, []);

  const loadStatus = async () => {
    try {
      const data = await get2FAStatus();
      setStatus(data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  const handleSetupComplete = () => {
    setShowSetup(false);
    refreshTwoFactorCache();
    void loadStatus();
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
      refreshTwoFactorCache();
      void loadStatus();
    } catch (err: unknown) {
      const detail =
        err instanceof Object && 'response' in err
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
      setRegeneratedCodes(result.backup_codes);
    } catch (err: unknown) {
      const detail =
        err instanceof Object && 'response' in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined;
      setError(detail || 'Failed to regenerate backup codes');
    } finally {
      setSaving(false);
    }
  };

  const handleCopyRegenerated = () => {
    if (regeneratedCodes) {
      void navigator.clipboard.writeText(regeneratedCodes.join('\n'));
      toast.success(t('security.backupCodesCopied'));
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

  if (regeneratedCodes) {
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
          {regeneratedCodes.map((code) => (
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
            onClick={handleCopyRegenerated}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2 text-sm text-white rounded-lg bg-slate-700 hover:bg-slate-600 transition-colors"
          >
            <Copy className="w-4 h-4" />
            {t('security.copyBackupCodes')}
          </button>
          <button
            type="button"
            onClick={() => setRegeneratedCodes(null)}
            className="flex-1 px-4 py-2 text-sm text-white rounded-lg bg-sky-500 hover:bg-sky-500-secondary transition-colors"
          >
            {t('security.backupCodesDone')}
          </button>
        </div>
      </div>
    );
  }

  if (showSetup) {
    return (
      <div className="card border-slate-800/60 bg-slate-900/55">
        <h3 className="text-base sm:text-lg font-semibold mb-3 sm:mb-4 flex items-center">
          <Shield className="w-4 h-4 sm:w-5 sm:h-5 mr-2 text-sky-400" />
          {t('security.twoFactor')}
        </h3>
        <TwoFactorSetupFlow
          onComplete={handleSetupComplete}
          onCancel={() => setShowSetup(false)}
        />
      </div>
    );
  }

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
              className="flex-1 px-4 py-2 text-sm text-slate-300 rounded-lg bg-slate-700 hover:bg-slate-600 transition-colors"
            >
              {t('security.cancel')}
            </button>
            <button
              type="submit"
              disabled={saving}
              className="flex-1 px-4 py-2 text-sm text-white rounded-lg bg-rose-500 hover:bg-rose-600 transition-colors disabled:opacity-50"
            >
              {saving ? t('security.changing') : t('security.disable2FA')}
            </button>
          </div>
        </form>
      </div>
    );
  }

  return (
    <div className="card border-slate-800/60 bg-slate-900/55">
      <h3 className="text-base sm:text-lg font-semibold mb-3 sm:mb-4 flex items-center">
        <Shield className="w-4 h-4 sm:w-5 sm:h-5 mr-2 text-sky-400" />
        {t('security.twoFactor')}
      </h3>
      <p className="text-sm text-slate-300 mb-4">{t('security.twoFactorDescription')}</p>

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

          <div className="flex items-center gap-2 text-sm text-slate-300">
            <KeyRound className="w-4 h-4" />
            <span>{t('security.backupCodesRemaining', { count: status.backup_codes_remaining })}</span>
          </div>

          <div className="flex flex-col sm:flex-row gap-2">
            <button
              onClick={handleRegenerateBackupCodes}
              disabled={saving}
              className="flex items-center justify-center gap-2 px-4 py-2 text-sm text-slate-300 rounded-lg bg-slate-700 hover:bg-slate-600 transition-colors disabled:opacity-50"
            >
              <RefreshCw className="w-4 h-4" />
              {t('security.regenerateBackupCodes')}
            </button>
            <button
              onClick={() => { setShowDisable(true); setError(''); }}
              className="flex items-center justify-center gap-2 px-4 py-2 text-sm text-rose-300 rounded-lg bg-rose-500/10 border border-rose-500/30 hover:bg-rose-500/20 transition-colors"
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
            onClick={() => { setShowSetup(true); setError(''); }}
            disabled={saving}
            className="flex items-center justify-center gap-2 px-4 py-2 text-sm text-white rounded-lg bg-sky-500 hover:bg-sky-500-secondary transition-colors disabled:opacity-50"
          >
            <ShieldCheck className="w-4 h-4" />
            {t('security.enable2FA')}
          </button>
        </div>
      )}
    </div>
  );
}
