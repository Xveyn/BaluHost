/** Admin: how long a session lives — idle logout and access-token lifetime. */
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { getAuthPolicy, updateAuthPolicy } from '../../api/pin';
import { handleApiError } from '../../lib/errorHandling';

export function SessionPolicySettings() {
  const { t } = useTranslation('admin');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [idleMinutes, setIdleMinutes] = useState(4);
  const [warningSeconds, setWarningSeconds] = useState(60);
  const [tokenMinutes, setTokenMinutes] = useState(15);

  useEffect(() => {
    getAuthPolicy()
      .then((p) => {
        setIdleMinutes(p.idle_timeout_minutes);
        setWarningSeconds(p.idle_warning_seconds);
        setTokenMinutes(p.access_token_minutes);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  /**
   * One Save for all three, rather than the save-on-change the PIN card uses.
   * The server refuses an idle window that outlives the token, so raising the
   * idle timeout and the token lifetime has to travel in one request —
   * otherwise every such change would be rejected halfway through.
   */
  const save = async () => {
    const idleWindow = idleMinutes * 60 + warningSeconds;
    if (idleMinutes > 0 && idleWindow > tokenMinutes * 60) {
      // Mirrors the server rule so the admin gets a translated hint instead of
      // an English 400 detail. The server stays the enforcer.
      toast.error(t('sessionPolicy.idleExceedsToken'));
      return;
    }

    setBusy(true);
    try {
      const p = await updateAuthPolicy({
        idle_timeout_minutes: idleMinutes,
        idle_warning_seconds: warningSeconds,
        access_token_minutes: tokenMinutes,
      });
      setIdleMinutes(p.idle_timeout_minutes);
      setWarningSeconds(p.idle_warning_seconds);
      setTokenMinutes(p.access_token_minutes);
      toast.success(t('sessionPolicy.saved'));
    } catch (err) {
      handleApiError(err, t('sessionPolicy.saveError'));
    } finally {
      setBusy(false);
    }
  };

  if (loading) return null;

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6">
      <h3 className="text-lg font-semibold text-slate-100">{t('sessionPolicy.title')}</h3>
      <p className="mt-1 text-sm text-slate-400">{t('sessionPolicy.description')}</p>

      <label className="mt-4 block text-sm text-slate-300">
        {t('sessionPolicy.idleTimeout')}
        <input
          data-testid="session-idle-minutes"
          type="number" min={0} max={1440} className="input mt-1" disabled={busy}
          value={idleMinutes}
          onChange={(e) => setIdleMinutes(Number(e.target.value))}
        />
        <span className="mt-1 block text-xs text-slate-500">
          {idleMinutes === 0 ? t('sessionPolicy.idleDisabled') : t('sessionPolicy.idleHint')}
        </span>
      </label>

      <label className="mt-4 block text-sm text-slate-300">
        {t('sessionPolicy.warningSeconds')}
        <input
          data-testid="session-warning-seconds"
          type="number" min={10} max={300} className="input mt-1"
          disabled={busy || idleMinutes === 0}
          value={warningSeconds}
          onChange={(e) => setWarningSeconds(Number(e.target.value))}
        />
      </label>

      <label className="mt-4 block text-sm text-slate-300">
        {t('sessionPolicy.tokenMinutes')}
        <input
          data-testid="session-token-minutes"
          type="number" min={5} max={1440} className="input mt-1" disabled={busy}
          value={tokenMinutes}
          onChange={(e) => setTokenMinutes(Number(e.target.value))}
        />
        <span data-testid="session-token-hint" className="mt-1 block text-xs text-amber-400/80">
          {t('sessionPolicy.tokenHint')}
        </span>
      </label>

      <button
        data-testid="session-policy-save"
        onClick={() => { void save(); }}
        disabled={busy}
        className="mt-5 rounded-xl border border-sky-500/40 bg-sky-500/15 px-4 py-2 text-sm font-medium text-sky-200 transition hover:border-sky-400 hover:bg-sky-500/25 disabled:opacity-50"
      >
        {busy ? t('sessionPolicy.saving') : t('sessionPolicy.save')}
      </button>
    </div>
  );
}
