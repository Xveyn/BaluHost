import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { generateRecoveryCodes, getRecoveryCodesStatus, type RecoveryCodesStatus } from '../../api/recovery-codes';
import { get2FAStatus } from '../../api/two-factor';

export const RecoveryCodesCard: React.FC = () => {
  const { t } = useTranslation('settings');
  const [status, setStatus] = useState<RecoveryCodesStatus | null>(null);
  const [twoFA, setTwoFA] = useState(false);
  const [stepUp, setStepUp] = useState('');
  const [codes, setCodes] = useState<string[] | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = async () => {
    try { setStatus(await getRecoveryCodesStatus()); } catch { /* best-effort */ }
    try { setTwoFA((await get2FAStatus()).enabled); } catch { /* best-effort */ }
  };
  useEffect(() => { void refresh(); }, []);

  const handleGenerate = async () => {
    setLoading(true);
    try {
      const body = twoFA ? { code: stepUp } : { current_password: stepUp };
      const res = await generateRecoveryCodes(body);
      setCodes(res.recovery_codes);
      setStepUp('');
      await refresh();
      toast.success(t('recovery.generated'));
    } catch {
      toast.error(t('recovery.generateFailed'));
    } finally { setLoading(false); }
  };

  const handleCopy = async () => {
    if (!codes) return;
    try {
      if (!navigator.clipboard?.writeText) throw new Error('no clipboard');
      await navigator.clipboard.writeText(codes.join('\n'));
      toast.success(t('recovery.copied'));
    } catch {
      toast.error(t('recovery.copyUnavailable'));
    }
  };

  const handleDownload = () => {
    if (!codes) return;
    const blob = new Blob([codes.join('\n') + '\n'], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'baluhost-recovery-codes.txt';
    a.click(); URL.revokeObjectURL(url);
  };

  const notConfigured = status !== null && !status.configured;
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6">
      <h3 className="text-lg font-semibold text-slate-100">{t('recovery.title')}</h3>
      <p className="mt-1 text-sm text-slate-400">{t('recovery.desc')}</p>

      {notConfigured && (
        <div className="mt-3 rounded-lg border border-amber-700/50 bg-amber-950/30 px-3 py-2 text-xs text-amber-300">
          {t('recovery.banner')}
        </div>
      )}
      {status?.configured && !codes && (
        <p className="mt-3 text-xs text-slate-400">{t('recovery.remaining', { count: status.remaining })}</p>
      )}

      {codes && (
        <div className="mt-3">
          <div className="grid grid-cols-2 gap-2 rounded-lg bg-slate-950 p-3 font-mono text-xs text-slate-100">
            {codes.map((c) => (<span key={c}>{c}</span>))}
          </div>
          <div className="mt-2 flex gap-3">
            <button onClick={handleCopy} className="text-xs text-sky-400 hover:text-sky-300">{t('recovery.copy')}</button>
            <button onClick={handleDownload} className="text-xs text-sky-400 hover:text-sky-300">{t('recovery.download')}</button>
          </div>
          <p className="mt-1 text-xs text-amber-300">{t('recovery.shownOnce')}</p>
        </div>
      )}

      <div className="mt-4 space-y-3">
        <input
          type={twoFA ? 'text' : 'password'}
          inputMode={twoFA ? 'text' : undefined}
          autoComplete={twoFA ? 'one-time-code' : 'current-password'}
          placeholder={twoFA ? t('recovery.stepUpCode') : t('recovery.stepUpPassword')}
          aria-label={twoFA ? t('recovery.stepUpCode') : t('recovery.stepUpPassword')}
          className="input"
          value={stepUp}
          onChange={(e) => setStepUp(e.target.value)}
        />
        <p className="text-xs text-slate-400">
          {twoFA ? t('recovery.stepUpHintCode') : t('recovery.stepUpHintPassword')}
        </p>

        <div className="flex gap-2">
          <button
            onClick={handleGenerate}
            disabled={loading || !stepUp}
            className="btn btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? t('recovery.generating') : status?.configured ? t('recovery.regenerate') : t('recovery.generate')}
          </button>
        </div>
        {status?.configured && <p className="text-xs text-slate-400">{t('recovery.regenWarning')}</p>}
      </div>
    </div>
  );
};
