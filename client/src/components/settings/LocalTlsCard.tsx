/**
 * LocalTlsCard -- Statuskarte des Plugins `local_tls` (Integrations-Tab).
 *
 * Der DNS-Token wird nur geschrieben: das Feld wird nach dem Speichern
 * geleert, angezeigt wird nur "gesetzt / nicht gesetzt".
 */
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { toast } from 'react-hot-toast';
import { ShieldCheck, Loader2, Copy, Settings } from 'lucide-react';
import {
  getLocalTlsStatus, setLocalTlsToken, clearLocalTlsToken, renewLocalTls,
  updateLocalTlsDns, localTlsErrorKey, type LocalTlsStatus,
} from '../../api/localTls';
import { getPluginConfig } from '../../api/plugins';

const LEGO_INSTALL_COMMAND = 'sudo apt install -t trixie-backports lego';

type Severity = 'red' | 'yellow' | 'green';

const SEVERITY_CLASS: Record<Severity, string> = {
  red: 'text-red-400',
  yellow: 'text-yellow-400',
  green: 'text-green-400',
};

function severityFor(days: number): Severity {
  if (days < 7) return 'red';
  if (days < 21) return 'yellow';
  return 'green';
}

const fmt = (iso: string | null) => (iso ? new Date(iso).toLocaleString() : null);

export default function LocalTlsCard() {
  const { t } = useTranslation('localTls');
  const [status, setStatus] = useState<LocalTlsStatus | null>(null);
  const [domain, setDomain] = useState<string | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [token, setToken] = useState('');
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setStatus(await getLocalTlsStatus());
      setLoadFailed(false);
    } catch {
      setLoadFailed(true);
    }
  }, []);

  useEffect(() => {
    load();
    getPluginConfig('local_tls')
      .then((c) => setDomain(typeof c.config?.domain === 'string' ? c.config.domain : null))
      .catch(() => setDomain(null));
  }, [load]);

  const errorText = (err: unknown) => {
    const key = localTlsErrorKey(err);
    return t(key ? `error.${key}` : 'error.unknown', { defaultValue: t('error.unknown') });
  };

  const run = async (name: string, fn: () => Promise<void>) => {
    setBusy(name);
    setNotice(null);
    try {
      await fn();
    } catch (err) {
      setNotice(errorText(err));
    } finally {
      setBusy(null);
    }
  };

  const onSaveToken = () =>
    run('token', async () => {
      const value = token;
      try {
        await setLocalTlsToken(value);
      } finally {
        setToken('');
      }
      toast.success(t('token.saved'));
      await load();
    });

  const onRemoveToken = () =>
    run('remove', async () => {
      await clearLocalTlsToken();
      toast.success(t('token.removed'));
      await load();
    });

  const onRenew = () =>
    run('renew', async () => {
      setStatus(await renewLocalTls());
      toast.success(t('actions.renewDone'));
    });

  const onUpdateDns = () =>
    run('dns', async () => {
      setStatus(await updateLocalTlsDns());
      toast.success(t('actions.dnsDone'));
    });

  const copyHint = async () => {
    try {
      await navigator.clipboard.writeText(status?.nginx_hint ?? '');
      toast.success(t('actions.copied'));
    } catch {
      /* Zwischenablage nicht verfuegbar: Block bleibt markierbar */
    }
  };

  const days = status?.cert_not_after
    ? Math.floor((new Date(status.cert_not_after).getTime() - Date.now()) / 86400_000)
    : null;
  const severity = days === null ? null : severityFor(days);
  const legoBad = status && status.lego !== 'ok';

  return (
    <div className="card border-slate-800/60 bg-slate-900/55 shadow-[0_4px_24px_rgba(99,102,241,0.06)]">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-base sm:text-lg font-semibold flex items-center">
          <ShieldCheck className="w-4 h-4 sm:w-5 sm:h-5 mr-2 text-indigo-400" />
          {t('title')}
        </h3>
        <Link
          to="/plugins"
          className="text-sm text-indigo-300 hover:text-indigo-200 flex items-center gap-1"
        >
          <Settings className="w-4 h-4" />
          {t('settings')}
        </Link>
      </div>

      {loadFailed && <p className="text-sm text-red-400">{t('error.load')}</p>}
      {!status && !loadFailed && <Loader2 className="w-5 h-5 animate-spin text-slate-400" />}

      {status && (
        <div className="space-y-4 text-sm">
          <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2">
            <div>
              <dt className="text-slate-400">{t('domain')}</dt>
              <dd>{domain ?? t('notConfigured')}</dd>
            </div>
            <div>
              <dt className="text-slate-400">{t('address.current')}</dt>
              <dd>{status.current_ip ?? t('address.none')}</dd>
            </div>
            <div>
              <dt className="text-slate-400">{t('address.last')}</dt>
              <dd>
                {status.last_ip ?? t('address.none')}
                {status.last_ip_set_at && (
                  <span className="text-slate-500"> ({t('address.setAt', { date: fmt(status.last_ip_set_at) })})</span>
                )}
              </dd>
            </div>
            <div>
              <dt className="text-slate-400">{t('cert.validUntil')}</dt>
              <dd
                data-testid="cert-expiry"
                data-severity={severity ?? 'none'}
                className={severity ? SEVERITY_CLASS[severity] : 'text-slate-400'}
              >
                {status.cert_not_after
                  ? `${fmt(status.cert_not_after)} (${
                      days !== null && days < 0
                        ? t('cert.expired')
                        : t('cert.daysLeft', { count: days ?? 0 })
                    })`
                  : t('cert.none')}
              </dd>
            </div>
            <div className="sm:col-span-2">
              <dt className="text-slate-400">{t('renewal.last')}</dt>
              <dd>
                {status.last_renew_at ? (
                  <>
                    {fmt(status.last_renew_at)} –{' '}
                    <span className={status.last_renew_ok ? 'text-green-400' : 'text-red-400'}>
                      {status.last_renew_ok ? t('renewal.ok') : t('renewal.failed')}
                    </span>
                    {status.last_renew_reason && (
                      <span className="text-slate-500"> ({status.last_renew_reason})</span>
                    )}
                  </>
                ) : (
                  t('renewal.never')
                )}
              </dd>
            </div>
          </dl>

          <div>
            <span className="text-slate-400">{t('lego.label')}: </span>
            {legoBad ? (
              <>
                <span className="text-yellow-400">{t(`lego.${status.lego}`)}</span>
                <pre className="mt-1 p-2 rounded bg-slate-950/70 border border-slate-700/40 overflow-x-auto">
                  <code>{LEGO_INSTALL_COMMAND}</code>
                </pre>
              </>
            ) : (
              <span>{t('lego.ok', { version: status.lego_version ?? '' })}</span>
            )}
          </div>

          {status.nginx_hint && (
            <div>
              <p className="text-yellow-400 mb-1">{t('nginx.hint')}</p>
              <pre className="p-2 rounded bg-slate-950/70 border border-slate-700/40 overflow-x-auto">
                <code>{status.nginx_hint}</code>
              </pre>
              <button type="button" onClick={copyHint} className="btn btn-secondary mt-2 flex items-center gap-1">
                <Copy className="w-4 h-4" />
                {t('actions.copy')}
              </button>
            </div>
          )}

          <div>
            <p className="text-slate-400 mb-1">
              {t('token.label')}:{' '}
              <span className={status.token_set ? 'text-green-400' : 'text-yellow-400'}>
                {status.token_set ? t('token.set') : t('token.notSet')}
              </span>
            </p>
            <div className="flex flex-col sm:flex-row gap-2">
              <input
                data-testid="token-input"
                type="password"
                autoComplete="off"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                placeholder={t('providers.duckdns.token')}
                aria-label={t('providers.duckdns.token')}
                className="input flex-1"
              />
              <button
                type="button"
                className="btn btn-primary"
                disabled={!token || busy !== null}
                onClick={onSaveToken}
              >
                {t('token.save')}
              </button>
              {status.token_set && (
                <button type="button" className="btn btn-secondary" disabled={busy !== null} onClick={onRemoveToken}>
                  {t('token.remove')}
                </button>
              )}
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            <button type="button" className="btn btn-primary" disabled={busy !== null} onClick={onRenew}>
              {busy === 'renew' && <Loader2 className="w-4 h-4 animate-spin inline mr-1" />}
              {t('actions.renew')}
            </button>
            <button type="button" className="btn btn-secondary" disabled={busy !== null} onClick={onUpdateDns}>
              {busy === 'dns' && <Loader2 className="w-4 h-4 animate-spin inline mr-1" />}
              {t('actions.updateDns')}
            </button>
          </div>
          {notice && <p role="alert" className="text-yellow-400">{notice}</p>}
        </div>
      )}
    </div>
  );
}
