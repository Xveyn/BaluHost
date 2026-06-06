/** Admin: system-wide PIN-login policy (grace window + kill switch). */
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { getAuthPolicy, updateAuthPolicy } from '../../api/pin';
import { handleApiError } from '../../lib/errorHandling';

const WINDOW_OPTIONS: { key: string; seconds: number }[] = [
  { key: '1h', seconds: 3600 },
  { key: '8h', seconds: 28800 },
  { key: '24h', seconds: 86400 },
  { key: '7d', seconds: 604800 },
];

export function AuthPolicySettings() {
  const { t } = useTranslation('admin');
  const [loading, setLoading] = useState(true);
  const [enabled, setEnabled] = useState(true);
  const [windowSeconds, setWindowSeconds] = useState(86400);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getAuthPolicy()
      .then((p) => { setEnabled(p.pin_login_enabled); setWindowSeconds(p.pin_grace_window_seconds); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const save = async (next: { pin_login_enabled?: boolean; pin_grace_window_seconds?: number }) => {
    setBusy(true);
    try {
      const p = await updateAuthPolicy(next);
      setEnabled(p.pin_login_enabled);
      setWindowSeconds(p.pin_grace_window_seconds);
      toast.success(t('authPolicy.saved'));
    } catch (err) {
      handleApiError(err, t('authPolicy.saveError'));
    } finally {
      setBusy(false);
    }
  };

  if (loading) return null;

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6">
      <h3 className="text-lg font-semibold text-slate-100">{t('authPolicy.title')}</h3>
      <p className="mt-1 text-sm text-slate-400">{t('authPolicy.description')}</p>

      <label className="mt-4 flex items-center justify-between">
        <span className="text-sm text-slate-300">{t('authPolicy.enabled')}</span>
        <input type="checkbox" checked={enabled} disabled={busy}
          onChange={(e) => save({ pin_login_enabled: e.target.checked })}
          className="h-4 w-4 rounded border-slate-600 bg-slate-800 text-sky-500 focus:ring-sky-500/50" />
      </label>

      <label className="mt-4 block text-sm text-slate-300">
        {t('authPolicy.window')}
        <select className="input mt-1" value={windowSeconds} disabled={busy}
          onChange={(e) => save({ pin_grace_window_seconds: Number(e.target.value) })}>
          {WINDOW_OPTIONS.map((o) => (
            <option key={o.key} value={o.seconds}>{t(`authPolicy.windows.${o.key}`)}</option>
          ))}
        </select>
      </label>
    </div>
  );
}
