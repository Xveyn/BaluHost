import { useTranslation } from 'react-i18next';
import { Cpu } from 'lucide-react';
import { AdminBadge } from '../ui/AdminBadge';
import type { GpuPowerStatus } from '../../types/gpuPower';
import { useGpuPower } from '../../hooks/useGpuPower';
import { GpuPowerThresholds } from './GpuPowerThresholds';
import { GpuPowerHardware } from './GpuPowerHardware';

const STATE_TONE: Record<GpuPowerStatus['current_state'], string> = {
  active: 'bg-emerald-500/15 border-emerald-500/40 text-emerald-300',
  standby: 'bg-amber-500/15 border-amber-500/40 text-amber-300',
  deep_idle: 'bg-blue-500/15 border-blue-500/40 text-blue-300',
};

export function GpuPowerCard({ isAdmin }: { isAdmin: boolean }) {
  const { t } = useTranslation(['system', 'common']);
  // Query-backed (#299) — 5s poll, draft-guarded editor, save-as-mutation.
  const { status, config, caps, draft, setDraft, dirty, loadError, saving, save } = useGpuPower();

  if (loadError && !status) {
    return (
      <div className="card border-slate-700/50 p-4 sm:p-6">
        <h2 className="text-base sm:text-lg font-medium text-white">
          {t('system:power.gpu.title')}
        </h2>
        <p className="mt-2 text-sm text-rose-400">
          {t('system:power.gpu.messages.loadFailed')}
        </p>
      </div>
    );
  }

  if (status && !status.detected) {
    return (
      <div className="card border-slate-700/50 p-4 sm:p-6">
        <div className="flex items-center gap-2">
          <Cpu className="h-5 w-5 text-slate-400" aria-hidden />
          <h2 className="text-base sm:text-lg font-medium text-white">
            {t('system:power.gpu.title')}
          </h2>
        </div>
        <p className="mt-2 text-sm text-slate-400">{t('system:power.gpu.noGpu')}</p>
      </div>
    );
  }

  const stateKey: GpuPowerStatus['current_state'] = status?.current_state ?? 'active';
  const stateTone = STATE_TONE[stateKey];

  return (
    <div className="card border-slate-700/50 p-4 sm:p-6 space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
        <div className="flex items-center gap-2">
          <Cpu className="h-5 w-5 text-purple-400" aria-hidden />
          <h2 className="text-base sm:text-lg font-medium text-white">
            {t('system:power.gpu.title')}
          </h2>
          {isAdmin && <AdminBadge />}
        </div>
        {status && (
          <div className="flex items-center gap-2 text-xs sm:text-sm">
            <span
              className={`inline-flex items-center rounded-full border px-2 py-0.5 font-medium ${stateTone}`}
            >
              {t(`system:power.gpu.states.${stateKey}`)}
            </span>
            {status.vendor && (
              <span className="uppercase tracking-wide text-slate-500">{status.vendor}</span>
            )}
          </div>
        )}
      </div>

      {status && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <StatItem label={t('system:power.gpu.stats.displays')} value={status.display_count} />
          <StatItem
            label={t('system:power.gpu.stats.usage')}
            value={`${(status.usage_percent ?? 0).toFixed(0)}%`}
          />
          <StatItem
            label={t('system:power.gpu.stats.demands')}
            value={status.active_demands.length}
          />
          <StatItem
            label={t('system:power.gpu.stats.permission')}
            value={
              status.has_write_permission
                ? t('system:power.gpu.permission.ok')
                : t('system:power.gpu.permission.missing')
            }
            tone={status.has_write_permission ? 'ok' : 'warn'}
          />
        </div>
      )}

      {draft && (
        <div className="space-y-3">
          <label
            className={`flex items-center gap-3 rounded-lg border border-slate-700/50 bg-slate-800/30 px-4 py-3 ${
              isAdmin && !saving ? 'cursor-pointer hover:bg-slate-800/50' : 'opacity-60'
            }`}
          >
            <input
              type="checkbox"
              disabled={!isAdmin || saving}
              checked={draft.enabled}
              onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })}
              className="h-4 w-4 rounded border-slate-600 bg-slate-900 text-emerald-500 focus:ring-emerald-500/40 focus:ring-offset-0"
            />
            <span className="text-sm text-slate-200">
              {t('system:power.gpu.enableLabel')}
            </span>
          </label>

          <details className="rounded-lg border border-slate-700/50 bg-slate-800/30">
            <summary className="cursor-pointer select-none px-4 py-3 text-sm font-medium text-slate-200 hover:bg-slate-800/50 rounded-lg">
              {t('system:power.gpu.thresholds.title')}
            </summary>
            <div className="border-t border-slate-700/50 p-4">
              <GpuPowerThresholds
                value={draft}
                onChange={setDraft}
                disabled={!isAdmin || saving}
              />
            </div>
          </details>

          <details className="rounded-lg border border-slate-700/50 bg-slate-800/30">
            <summary className="cursor-pointer select-none px-4 py-3 text-sm font-medium text-slate-200 hover:bg-slate-800/50 rounded-lg">
              {t('system:power.gpu.hardware.title')}
            </summary>
            <div className="border-t border-slate-700/50 p-4">
              <GpuPowerHardware
                value={draft}
                caps={caps}
                onChange={setDraft}
                disabled={!isAdmin || saving}
              />
            </div>
          </details>

          {isAdmin && (
            <div className="flex flex-wrap items-center gap-2 pt-2">
              <button
                type="button"
                onClick={() => void save()}
                disabled={!dirty || saving}
                className="rounded-lg bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30 disabled:opacity-40 disabled:cursor-not-allowed px-3 sm:px-4 py-2 text-xs sm:text-sm transition-colors touch-manipulation active:scale-95 min-h-[40px]"
              >
                {saving ? t('system:power.gpu.buttons.saving') : t('system:power.gpu.buttons.save')}
              </button>
              <button
                type="button"
                onClick={() => config && setDraft(config)}
                disabled={!dirty || saving}
                className="rounded-lg bg-slate-700 text-slate-300 hover:bg-slate-600 disabled:opacity-40 disabled:cursor-not-allowed px-3 sm:px-4 py-2 text-xs sm:text-sm transition-colors touch-manipulation active:scale-95 min-h-[40px]"
              >
                {t('system:power.gpu.buttons.reset')}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

interface StatItemProps {
  label: string;
  value: string | number;
  tone?: 'ok' | 'warn';
}

function StatItem({ label, value, tone }: StatItemProps) {
  const valueColor =
    tone === 'warn'
      ? 'text-amber-300'
      : tone === 'ok'
        ? 'text-emerald-300'
        : 'text-white';
  return (
    <div className="rounded-lg border border-slate-700/50 bg-slate-800/30 px-3 py-2">
      <p className="text-[10px] sm:text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-1 text-sm sm:text-base font-medium ${valueColor}`}>{value}</p>
    </div>
  );
}
