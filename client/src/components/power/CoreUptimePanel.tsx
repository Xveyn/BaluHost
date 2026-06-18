/**
 * Core Operating Hours panel.
 *
 * Shows master toggle + list of windows + add button.
 * Auto-saves all changes (no global Save button).
 */
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { Shield, Plus } from 'lucide-react';
import {
  listCoreUptimeWindows,
  createCoreUptimeWindow,
  updateCoreUptimeWindow,
  deleteCoreUptimeWindow,
  type CoreUptimeWindow,
  type CoreUptimeWindowUpdate,
} from '../../api/coreUptime';
import {
  getSleepConfig,
  updateSleepConfig,
} from '../../api/sleep';
import { CoreUptimeWindowCard } from './CoreUptimeWindowCard';

export function CoreUptimePanel() {
  const { t } = useTranslation('system');
  const [masterEnabled, setMasterEnabled] = useState(false);
  const [suspendOnExit, setSuspendOnExit] = useState(false);
  const [windows, setWindows] = useState<CoreUptimeWindow[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = async () => {
    try {
      const [cfg, ws] = await Promise.all([getSleepConfig(), listCoreUptimeWindows()]);
      setMasterEnabled(cfg.core_uptime_enabled);
      setSuspendOnExit(cfg.core_uptime_suspend_on_exit);
      setWindows(ws);
    } catch {
      toast.error(t('sleep.coreUptime.loadFailed'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const handleMasterToggle = async () => {
    const next = !masterEnabled;
    setMasterEnabled(next); // optimistic
    try {
      await updateSleepConfig({ core_uptime_enabled: next });
    } catch (err) {
      setMasterEnabled(!next);
      toast.error(err instanceof Error ? err.message : t('sleep.coreUptime.saveFailed'));
    }
  };

  const handleSuspendOnExitToggle = async () => {
    const next = !suspendOnExit;
    setSuspendOnExit(next); // optimistic
    try {
      await updateSleepConfig({ core_uptime_suspend_on_exit: next });
    } catch (err) {
      setSuspendOnExit(!next);
      toast.error(err instanceof Error ? err.message : t('sleep.coreUptime.saveFailed'));
    }
  };

  const handleAdd = async () => {
    try {
      const created = await createCoreUptimeWindow({
        label: '',
        start_time: '08:00',
        end_time: '22:00',
        weekdays: [0, 1, 2, 3, 4],
      });
      setWindows((prev) => [...prev, created]);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t('sleep.coreUptime.createFailed'));
    }
  };

  const handleUpdate = async (id: number, patch: CoreUptimeWindowUpdate) => {
    const original = windows.find((w) => w.id === id);
    if (!original) return;
    setWindows((prev) =>
      prev.map((w) => (w.id === id ? { ...w, ...patch } as CoreUptimeWindow : w)),
    );
    try {
      const updated = await updateCoreUptimeWindow(id, patch);
      setWindows((prev) => prev.map((w) => (w.id === id ? updated : w)));
    } catch (err) {
      // Rollback
      setWindows((prev) => prev.map((w) => (w.id === id ? original : w)));
      toast.error(err instanceof Error ? err.message : t('sleep.coreUptime.saveFailed'));
    }
  };

  const handleDelete = async (id: number) => {
    if (!window.confirm(t('sleep.coreUptime.deleteConfirm'))) return;
    const original = windows;
    setWindows((prev) => prev.filter((w) => w.id !== id));
    try {
      await deleteCoreUptimeWindow(id);
    } catch (err) {
      setWindows(original);
      toast.error(err instanceof Error ? err.message : t('sleep.coreUptime.deleteFailed'));
    }
  };

  if (loading) {
    return (
      <div className="card border-slate-700/50 p-6">
        <div className="animate-pulse space-y-4">
          <div className="h-6 bg-slate-700/50 rounded w-1/3" />
          <div className="h-32 bg-slate-700/50 rounded" />
        </div>
      </div>
    );
  }

  return (
    <div className="card border-slate-700/50 p-4 sm:p-6 space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <Shield className="h-4 w-4 text-emerald-400" />
          <div>
            <h4 className="text-sm font-medium text-white">{t('sleep.coreUptime.title')}</h4>
            <p className="mt-0.5 text-xs text-slate-400">
              {t('sleep.coreUptime.description')}
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={handleMasterToggle}
          className={`relative inline-flex h-6 w-11 shrink-0 rounded-full transition-colors ${
            masterEnabled ? 'bg-emerald-500' : 'bg-slate-600'
          }`}
          aria-label={t('sleep.coreUptime.masterToggle')}
        >
          <span
            className={`pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow transform transition-transform ${
              masterEnabled ? 'translate-x-5.5 ml-0.5' : 'translate-x-0.5'
            } mt-0.5`}
          />
        </button>
      </div>

      {masterEnabled && (
        <div className="space-y-2">
          {windows.map((w) => (
            <CoreUptimeWindowCard
              key={w.id}
              window={w}
              onChange={handleUpdate}
              onDelete={handleDelete}
            />
          ))}
          <button
            type="button"
            onClick={handleAdd}
            className="w-full rounded-lg border border-dashed border-slate-600 hover:border-teal-500/40 hover:bg-teal-500/5 p-3 text-sm text-slate-400 hover:text-teal-300 transition-colors flex items-center justify-center gap-2"
          >
            <Plus className="h-4 w-4" />
            {t('sleep.coreUptime.addWindow')}
          </button>
          <div className="flex items-start justify-between gap-3 pt-2 border-t border-slate-700/50">
            <div>
              <p className="text-sm text-white">{t('sleep.coreUptime.suspendOnExit')}</p>
              <p className="mt-0.5 text-xs text-slate-400">{t('sleep.coreUptime.suspendOnExitDesc')}</p>
            </div>
            <button
              type="button"
              onClick={handleSuspendOnExitToggle}
              className={`relative inline-flex h-6 w-11 shrink-0 rounded-full transition-colors ${
                suspendOnExit ? 'bg-emerald-500' : 'bg-slate-600'
              }`}
              aria-label={t('sleep.coreUptime.suspendOnExit')}
            >
              <span
                className={`pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow transform transition-transform ${
                  suspendOnExit ? 'translate-x-5.5 ml-0.5' : 'translate-x-0.5'
                } mt-0.5`}
              />
            </button>
          </div>
          <p className="text-xs text-slate-500 mt-2">
            {t('sleep.coreUptime.blockedActions')}
          </p>
        </div>
      )}
    </div>
  );
}
