/**
 * OS Auto-Suspend Card
 *
 * Bidirectional read/write of the currently active power manager's
 * idle-suspend setting (KDE PowerDevil, GNOME gsd-power, or systemd-logind).
 * Hidden on unsupported platforms.
 */
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Moon, RefreshCw } from 'lucide-react';
import toast from 'react-hot-toast';

import {
  getOsAutoSuspend,
  setOsAutoSuspend,
  type OsAutoSuspendAction,
  type OsAutoSuspendResponse,
} from '../../api/sleep';

export function OsAutoSuspendCard() {
  const { t } = useTranslation('system');
  const [data, setData] = useState<OsAutoSuspendResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [enabled, setEnabled] = useState(false);
  const [timeoutMinutes, setTimeoutMinutes] = useState(15);
  const [action, setAction] = useState<OsAutoSuspendAction>('suspend');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getOsAutoSuspend();
      setData(res);
      setEnabled(res.enabled);
      setTimeoutMinutes(res.timeout_minutes || 15);
      setAction(res.action === 'ignore' ? 'suspend' : res.action);
    } catch {
      toast.error(t('sleep.osAutoSuspend.loadError'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const onSave = async () => {
    setSaving(true);
    try {
      const res = await setOsAutoSuspend({
        enabled,
        timeout_minutes: timeoutMinutes,
        action,
      });
      setData(res);
      setEnabled(res.enabled);
      setTimeoutMinutes(res.timeout_minutes || 15);
      setAction(res.action === 'ignore' ? 'suspend' : res.action);
      toast.success(t('sleep.osAutoSuspend.saved'));
    } catch {
      toast.error(t('sleep.osAutoSuspend.saveError'));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="card border-slate-700/50 p-4 sm:p-6">
        <div className="animate-pulse space-y-3">
          <div className="h-5 w-1/3 bg-slate-700/50 rounded" />
          <div className="h-4 w-2/3 bg-slate-700/40 rounded" />
        </div>
      </div>
    );
  }

  if (!data || !data.supported) return null;

  const badgeLabel = t(`sleep.osAutoSuspend.badgeSource.${data.source}`);

  return (
    <div
      className="card border-slate-700/50 p-4 sm:p-6 space-y-3"
      data-testid="os-auto-suspend-card"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h4 className="text-sm font-medium text-white flex items-center gap-2">
            <Moon className="h-4 w-4 text-slate-300" />
            {t('sleep.osAutoSuspend.title')}
          </h4>
          <p className="text-xs text-slate-400 mt-1">
            {t('sleep.osAutoSuspend.subtitle', { source: data.backend_label })}
          </p>
        </div>
        <span
          className="inline-flex items-center rounded bg-slate-700/40 text-slate-300 text-xs px-2 py-0.5"
          data-testid="os-auto-suspend-source-badge"
        >
          {badgeLabel}
        </span>
      </div>

      <div className="space-y-3 pt-2">
        <label className="flex items-center gap-2 text-sm text-slate-200">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
            className="rounded"
            data-testid="os-auto-suspend-enabled"
          />
          {t('sleep.osAutoSuspend.enabledLabel')}
        </label>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label className="block text-sm text-slate-300">
            <span className="block mb-1">{t('sleep.osAutoSuspend.timeoutLabel')}</span>
            <input
              type="number"
              min={1}
              max={1440}
              value={timeoutMinutes}
              onChange={(e) => setTimeoutMinutes(Math.max(1, Math.min(1440, Number(e.target.value))))}
              disabled={!enabled}
              className="w-full rounded bg-slate-900/60 border border-slate-700 px-2 py-1 text-slate-100 disabled:opacity-50"
              data-testid="os-auto-suspend-timeout"
            />
          </label>

          <label className="block text-sm text-slate-300">
            <span className="block mb-1">{t('sleep.osAutoSuspend.actionLabel')}</span>
            <select
              value={action}
              onChange={(e) => setAction(e.target.value as OsAutoSuspendAction)}
              disabled={!enabled}
              className="w-full rounded bg-slate-900/60 border border-slate-700 px-2 py-1 text-slate-100 disabled:opacity-50"
              data-testid="os-auto-suspend-action"
            >
              <option value="suspend">{t('sleep.osAutoSuspend.actionSuspend')}</option>
              <option value="hibernate">{t('sleep.osAutoSuspend.actionHibernate')}</option>
            </select>
          </label>
        </div>

        <div className="flex items-center gap-2 pt-2">
          <button
            type="button"
            onClick={() => void onSave()}
            disabled={saving}
            className="inline-flex items-center gap-1 rounded bg-blue-600/80 hover:bg-blue-600 disabled:opacity-60 text-white text-sm px-3 py-1"
            data-testid="os-auto-suspend-save"
          >
            {saving ? t('sleep.osAutoSuspend.saving') : t('sleep.osAutoSuspend.saveButton')}
          </button>
          <button
            type="button"
            onClick={() => void load()}
            disabled={loading || saving}
            className="inline-flex items-center gap-1 rounded text-xs text-slate-400 hover:text-slate-200"
            aria-label="Reload"
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}
