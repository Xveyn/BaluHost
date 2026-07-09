/**
 * Auto-Scaling config card for Power Management.
 *
 * Displays and edits the CPU-percentage thresholds that drive automatic
 * profile scaling (surge/medium/low) plus the cooldown period.
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { AdminBadge } from '../ui/AdminBadge';
import { handleApiError } from '../../lib/errorHandling';
import { updateAutoScalingConfig, type AutoScalingConfig } from '../../api/power-management';
import { isValidAutoScaling } from './utils';

interface AutoScalingSectionProps {
  autoScaling: AutoScalingConfig;
  dimmed: boolean;
  busy: boolean;
  onBusyChange: (b: boolean) => void;
  onRefresh: () => void;
}

export function AutoScalingSection({
  autoScaling, dimmed, busy, onBusyChange, onRefresh,
}: AutoScalingSectionProps) {
  const { t } = useTranslation(['system', 'common']);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<AutoScalingConfig | null>(null);

  const startEdit = () => {
    setDraft({ ...autoScaling });
    setEditing(true);
  };
  const cancelEdit = () => {
    setEditing(false);
    setDraft(null);
  };
  const save = async () => {
    if (!draft || busy) return;
    if (!isValidAutoScaling(draft)) {
      toast.error(t('system:power.autoScaling.validationError'));
      return;
    }
    onBusyChange(true);
    try {
      await updateAutoScalingConfig(draft);
      onRefresh();
      setEditing(false);
      setDraft(null);
      toast.success(t('system:power.autoScaling.thresholdsSaved'));
    } catch (err) {
      handleApiError(err, t('system:power.autoScaling.thresholdsSaveFailed'));
    } finally {
      onBusyChange(false);
    }
  };

  return (
    <div
      data-testid="auto-scaling-section"
      className={`card border-slate-700/50 p-4 sm:p-6 ${dimmed ? 'opacity-50 pointer-events-none' : ''}`}
    >
      <div className="mb-3 sm:mb-4 flex items-center justify-between">
        <h2 className="text-base sm:text-lg font-medium text-white flex items-center gap-2">
          {t('system:power.autoScaling.title')}
          <AdminBadge />
        </h2>
        {!editing ? (
          <button
            data-testid="auto-scaling-edit"
            onClick={startEdit}
            disabled={busy}
            className="text-xs text-slate-400 hover:text-white flex items-center gap-1"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
            </svg>
            {t('system:power.autoScaling.editButton')}
          </button>
        ) : (
          <div className="flex gap-2">
            <button
              onClick={cancelEdit}
              disabled={busy}
              className="rounded px-3 py-1 text-xs bg-slate-700 text-slate-300 hover:bg-slate-600"
            >
              {t('system:power.autoScaling.cancelButton')}
            </button>
            <button
              data-testid="auto-scaling-save"
              onClick={save}
              disabled={busy}
              className="rounded px-3 py-1 text-xs bg-blue-500/20 text-blue-300 hover:bg-blue-500/30"
            >
              {t('system:power.autoScaling.saveButton')}
            </button>
          </div>
        )}
      </div>
      {editing && draft ? (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2 sm:gap-4">
            <div className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-2 sm:p-4">
              <label className="block text-[10px] sm:text-sm text-slate-400 mb-1">{t('system:power.autoScaling.surge')}</label>
              <div className="flex items-center gap-1">
                <span className="text-red-300 text-sm">&gt;</span>
                <input
                  data-testid="auto-scaling-input-surge"
                  type="number"
                  min={0}
                  max={100}
                  value={draft.cpu_surge_threshold}
                  onChange={(e) => setDraft({ ...draft!, cpu_surge_threshold: Number(e.target.value) })}
                  className="w-full rounded bg-slate-900 border border-slate-600 px-2 py-1 text-sm sm:text-xl font-semibold text-red-300 focus:border-red-400 focus:outline-none"
                />
                <span className="text-red-300 text-sm">%</span>
              </div>
            </div>
            <div className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-2 sm:p-4">
              <label className="block text-[10px] sm:text-sm text-slate-400 mb-1">{t('system:power.autoScaling.medium')}</label>
              <div className="flex items-center gap-1">
                <span className="text-yellow-300 text-sm">&gt;</span>
                <input
                  type="number"
                  min={0}
                  max={100}
                  value={draft.cpu_medium_threshold}
                  onChange={(e) => setDraft({ ...draft!, cpu_medium_threshold: Number(e.target.value) })}
                  className="w-full rounded bg-slate-900 border border-slate-600 px-2 py-1 text-sm sm:text-xl font-semibold text-yellow-300 focus:border-yellow-400 focus:outline-none"
                />
                <span className="text-yellow-300 text-sm">%</span>
              </div>
            </div>
            <div className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-2 sm:p-4">
              <label className="block text-[10px] sm:text-sm text-slate-400 mb-1">{t('system:power.autoScaling.low')}</label>
              <div className="flex items-center gap-1">
                <span className="text-blue-300 text-sm">&gt;</span>
                <input
                  type="number"
                  min={0}
                  max={100}
                  value={draft.cpu_low_threshold}
                  onChange={(e) => setDraft({ ...draft!, cpu_low_threshold: Number(e.target.value) })}
                  className="w-full rounded bg-slate-900 border border-slate-600 px-2 py-1 text-sm sm:text-xl font-semibold text-blue-300 focus:border-blue-400 focus:outline-none"
                />
                <span className="text-blue-300 text-sm">%</span>
              </div>
            </div>
          </div>
          <div className="mt-2 sm:mt-3 flex items-center gap-4">
            <div className="flex items-center gap-2">
              <span className="text-xs sm:text-sm text-slate-500">{t('system:power.autoScaling.cooldown')}:</span>
              <input
                type="number"
                min={0}
                value={draft.cooldown_seconds}
                onChange={(e) => setDraft({ ...draft!, cooldown_seconds: Number(e.target.value) })}
                className="w-20 rounded bg-slate-900 border border-slate-600 px-2 py-1 text-xs sm:text-sm text-white focus:border-blue-400 focus:outline-none"
              />
              <span className="text-xs sm:text-sm text-slate-500">s</span>
            </div>
          </div>
        </>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2 sm:gap-4">
            <div className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-2 sm:p-4">
              <p className="text-[10px] sm:text-sm text-slate-400">{t('system:power.autoScaling.surge')}</p>
              <p className="text-sm sm:text-xl font-semibold text-red-300">&gt;{autoScaling.cpu_surge_threshold}%</p>
            </div>
            <div className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-2 sm:p-4">
              <p className="text-[10px] sm:text-sm text-slate-400">{t('system:power.autoScaling.medium')}</p>
              <p className="text-sm sm:text-xl font-semibold text-yellow-300">&gt;{autoScaling.cpu_medium_threshold}%</p>
            </div>
            <div className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-2 sm:p-4">
              <p className="text-[10px] sm:text-sm text-slate-400">{t('system:power.autoScaling.low')}</p>
              <p className="text-sm sm:text-xl font-semibold text-blue-300">&gt;{autoScaling.cpu_low_threshold}%</p>
            </div>
          </div>
          <p className="mt-2 sm:mt-3 text-xs sm:text-sm text-slate-500">
            {t('system:power.autoScaling.cooldown')}: {autoScaling.cooldown_seconds}s &bull; {t('system:power.autoScaling.cpuMonitor')}:{' '}
            {autoScaling.use_cpu_monitoring ? t('system:power.autoScaling.active') : t('system:power.autoScaling.inactive')}
          </p>
        </>
      )}
    </div>
  );
}
