import type { FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import type { AvailableDisk, RaidArray, RaidDevice, RaidSpeedLimits } from '../../api/raid';
import { formatBytes, formatNumber } from '../../lib/formatters';
import SsdCachePanel from '../SsdCachePanel';
import { Zap } from 'lucide-react';
import {
  getStatusStyle,
  getDeviceStyle,
  upcase,
  canSimulateFailure,
  canStartRebuild,
  shouldShowFinalize,
} from './raidUtils';

export interface RaidArrayCardProps {
  array: RaidArray;
  busy: boolean;
  speedLimits: RaidSpeedLimits | null;
  availableDisks: AvailableDisk[];
  onSimulateFailure: (array: RaidArray, device?: RaidDevice) => Promise<void>;
  onStartRebuild: (array: RaidArray, device: RaidDevice) => Promise<void>;
  onFinalize: (array: RaidArray) => Promise<void>;
  onToggleBitmap: (array: RaidArray) => Promise<void>;
  onTriggerScrub: (array: RaidArray) => Promise<void>;
  onWriteMostly: (array: RaidArray, device: RaidDevice) => Promise<void>;
  onRemoveDevice: (array: RaidArray, device: RaidDevice) => Promise<void>;
  onAddSpare: (event: FormEvent<HTMLFormElement>, array: RaidArray) => Promise<void>;
  onUpdateSpeed: (event: FormEvent<HTMLFormElement>, array: RaidArray) => Promise<void>;
  onDeleteArray: (arrayName: string) => Promise<void>;
  onSetupCache: (arrayName: string) => void;
  onRefresh: () => Promise<void>;
}

export const RaidArrayCard: React.FC<RaidArrayCardProps> = ({
  array,
  busy,
  speedLimits,
  availableDisks,
  onSimulateFailure,
  onStartRebuild,
  onFinalize,
  onToggleBitmap,
  onTriggerScrub,
  onWriteMostly,
  onRemoveDevice,
  onAddSpare,
  onUpdateSpeed,
  onDeleteArray,
  onSetupCache,
  onRefresh,
}) => {
  const { t } = useTranslation(['system', 'common']);
  const lowerStatus = array.status.toLowerCase();
  const showFinalize = shouldShowFinalize(array);

  return (
    <div className="card border-slate-800/60 bg-slate-900/55">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4 border-b border-slate-800/60 px-4 sm:px-6 py-4 sm:py-5">
        <div className="space-y-1 flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <div className="flex h-8 w-8 sm:h-10 sm:w-10 items-center justify-center rounded-xl bg-gradient-to-br from-sky-500 to-indigo-600 shadow-lg shadow-sky-500/30 flex-shrink-0">
              <svg className="h-4 w-4 sm:h-5 sm:w-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5.25 14.25h13.5m-13.5 0a3 3 0 01-3-3m3 3a3 3 0 100 6h13.5a3 3 0 100-6m-16.5-3a3 3 0 013-3h13.5a3 3 0 013 3m-19.5 0a4.5 4.5 0 01.9-2.7L5.737 5.1a3.375 3.375 0 012.7-1.35h7.126c1.062 0 2.062.5 2.7 1.35l2.587 3.45a4.5 4.5 0 01.9 2.7m0 0a3 3 0 01-3 3m0 3h.008v.008h-.008v-.008zm0-6h.008v.008h-.008v-.008zm-3 6h.008v.008h-.008v-.008zm0-6h.008v.008h-.008v-.008z" />
              </svg>
            </div>
            <h2 className="text-base sm:text-xl font-semibold text-white truncate">{array.name}</h2>
            <span className={`rounded-full border px-2 sm:px-3 py-0.5 sm:py-1 text-[10px] sm:text-xs font-medium ${getStatusStyle(lowerStatus)}`}>
              {upcase(lowerStatus)}
            </span>
            <span className="rounded-full border border-slate-700/70 bg-slate-900/60 px-2 sm:px-3 py-0.5 sm:py-1 text-[10px] sm:text-xs uppercase tracking-[0.26em] text-slate-400">
              {array.level.replace(/^raid/i, 'RAID ')}
            </span>
            <span className="hidden sm:inline rounded-full border border-slate-800/70 bg-slate-900/60 px-3 py-1 text-xs text-slate-400">
              {t('system:raid.labels.bitmap')}: {array.bitmap ? array.bitmap : t('system:raid.labels.bitmapOff')}
            </span>
            {array.sync_action && (
              <span className="hidden sm:inline rounded-full border border-slate-800/70 bg-slate-900/60 px-3 py-1 text-xs text-slate-400">
                {t('system:raid.labels.sync')}: {array.sync_action}
              </span>
            )}
          </div>
          <p className="text-xs sm:text-sm text-slate-400">
            {formatBytes(array.size_bytes)} · {array.devices.length} {t('system:raid.labels.drives')} · {array.devices.filter(d => ['active', 'write-mostly', 'rebuilding'].includes(d.state.toLowerCase())).length} {t('system:raid.labels.active')}
          </p>
          <div className="flex flex-wrap gap-2 text-[10px] sm:text-xs text-slate-500">
            <span>{t('system:raid.labels.writeMostly')}: {array.devices.filter((device) => device.state === 'write-mostly').length}</span>
            <span>{t('system:raid.labels.spares')}: {array.devices.filter((device) => device.state === 'spare').length}</span>
          </div>
        </div>
        <div className="w-full sm:w-auto space-y-2">
          {array.resync_progress !== null && array.resync_progress !== undefined && (
            <div className="flex flex-row sm:flex-col items-center sm:items-end text-xs sm:text-sm text-slate-300">
              <span className="mr-2 sm:mr-0">{t('system:raid.labels.sync')}:</span>
              <span className="text-slate-200 font-medium">{formatNumber(array.resync_progress, 1)}%</span>
            </div>
          )}
          <div className="flex gap-2 overflow-x-auto pb-2 sm:pb-0">
            <button
              onClick={() => onToggleBitmap(array)}
              disabled={busy}
              className={`whitespace-nowrap rounded-xl border px-3 sm:px-4 py-1.5 sm:py-2 text-xs sm:text-sm transition touch-manipulation active:scale-95 ${
                busy
                  ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                  : 'border-slate-700/70 bg-slate-900/60 text-slate-200 hover:border-sky-500/40 hover:text-white'
              }`}
            >
              {array.bitmap ? t('system:raid.actions.disableBitmap') : t('system:raid.actions.enableBitmap')}
            </button>
            <button
              onClick={() => onTriggerScrub(array)}
              disabled={busy}
              className={`whitespace-nowrap rounded-xl border px-3 sm:px-4 py-1.5 sm:py-2 text-xs sm:text-sm transition touch-manipulation active:scale-95 ${
                busy
                  ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                  : 'border-indigo-500/40 bg-indigo-500/15 text-indigo-100 hover:border-indigo-500/60'
              }`}
            >
              <span className="hidden sm:inline">{t('system:raid.actions.integrityCheck')}</span>
              <span className="sm:hidden">{t('system:raid.actions.check')}</span>
            </button>
            <button
              onClick={() => onSimulateFailure(array)}
              disabled={busy}
              className={`whitespace-nowrap rounded-xl border px-3 sm:px-4 py-1.5 sm:py-2 text-xs sm:text-sm transition touch-manipulation active:scale-95 ${
                busy
                  ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                  : 'border-amber-500/40 bg-amber-500/15 text-amber-100 hover:border-amber-500/60'
              }`}
            >
              <span className="hidden sm:inline">{t('system:raid.actions.degradeArray')}</span>
              <span className="sm:hidden">Degrade</span>
            </button>
            {showFinalize && (
              <button
                onClick={() => onFinalize(array)}
                disabled={busy}
                className={`whitespace-nowrap rounded-xl border px-3 sm:px-4 py-1.5 sm:py-2 text-xs sm:text-sm transition touch-manipulation active:scale-95 ${
                  busy
                    ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                    : 'border-emerald-500/40 bg-emerald-500/15 text-emerald-100 hover:border-emerald-500/60'
                }`}
              >
                <span className="hidden sm:inline">{t('system:raid.actions.completeRebuild')}</span>
                <span className="sm:hidden">Rebuild</span>
              </button>
            )}
            <button
              onClick={() => onDeleteArray(array.name)}
              disabled={busy}
              className={`whitespace-nowrap rounded-xl border px-3 sm:px-4 py-1.5 sm:py-2 text-xs sm:text-sm transition touch-manipulation active:scale-95 ${
                busy
                  ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                  : 'border-rose-500/40 bg-rose-500/15 text-rose-200 hover:border-rose-500/60'
              }`}
            >
              <span className="hidden sm:inline">{t('system:raid.deleteArray')}</span>
              <span className="sm:hidden">Delete</span>
            </button>
          </div>
        </div>
      </div>

      {array.resync_progress !== null && array.resync_progress !== undefined && (
        <div className="border-b border-slate-800/60 px-4 sm:px-6 py-4">
          <div className="h-2 w-full overflow-hidden rounded-full bg-slate-800">
            <div
              className="h-full rounded-full bg-gradient-to-r from-sky-500 to-indigo-500"
              style={{ width: `${Math.min(Math.max(array.resync_progress, 0), 100)}%` }}
            />
          </div>
          <p className="mt-2 text-xs text-slate-500">
            {array.status.toLowerCase() === 'checking'
              ? t('system:raid.labels.checkProgress')
              : t('system:raid.labels.rebuildProgress')}
          </p>
        </div>
      )}

      <div className="px-4 sm:px-6 py-4 sm:py-5">
        {/* Desktop device table */}
        <div className="hidden lg:block overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-800/60">
            <thead>
              <tr className="text-left text-xs uppercase tracking-[0.24em] text-slate-500">
                <th className="px-5 py-3">{t('system:raid.tableHeaders.device')}</th>
                <th className="px-5 py-3">{t('system:raid.tableHeaders.status')}</th>
                <th className="px-5 py-3">{t('system:raid.tableHeaders.actions')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {array.devices.map((device) => {
                const lowerState = device.state.toLowerCase();
                const allowFailure = canSimulateFailure(device);
                const allowRebuild = canStartRebuild(device);

                return (
                  <tr key={`${array.name}-${device.name}`} className="group transition hover:bg-slate-900/65">
                    <td className="px-5 py-4 text-sm font-medium text-slate-200">
                      /dev/{device.name}
                    </td>
                    <td className="px-5 py-4">
                      <span className={`rounded-full border px-3 py-1 text-xs font-medium ${getDeviceStyle(lowerState)}`}>
                        {upcase(lowerState)}
                      </span>
                    </td>
                    <td className="px-5 py-4 text-sm">
                      <div className="flex gap-2">
                        <button
                          onClick={() => onSimulateFailure(array, device)}
                          disabled={busy || !allowFailure}
                          className={`whitespace-nowrap rounded-lg border px-3 py-1.5 text-xs transition touch-manipulation active:scale-95 ${
                            busy || !allowFailure
                              ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                              : 'border-amber-500/40 bg-amber-500/10 text-amber-100 hover:border-amber-500/60'
                          }`}
                        >
                          {t('system:raid.actions.degradeDevice')}
                        </button>
                        <button
                          onClick={() => onStartRebuild(array, device)}
                          disabled={busy || !allowRebuild}
                          className={`whitespace-nowrap rounded-lg border px-3 py-1.5 text-xs transition touch-manipulation active:scale-95 ${
                            busy || !allowRebuild
                              ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                              : 'border-sky-500/50 bg-sky-500/10 text-sky-100 hover:border-sky-500/60'
                          }`}
                        >
                          {t('system:raid.actions.startRebuild')}
                        </button>
                        <button
                          onClick={() => onWriteMostly(array, device)}
                          disabled={busy || !['active', 'write-mostly'].includes(lowerState)}
                          className={`whitespace-nowrap rounded-lg border px-3 py-1.5 text-xs transition touch-manipulation active:scale-95 ${
                            busy || !['active', 'write-mostly'].includes(lowerState)
                              ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                              : 'border-slate-700/70 bg-slate-900/60 text-slate-200 hover:border-slate-600'
                          }`}
                        >
                          {lowerState === 'write-mostly' ? t('system:raid.actions.removeWriteMostly') : t('system:raid.actions.writeMostly')}
                        </button>
                        {lowerState === 'spare' && (
                          <button
                            onClick={() => onRemoveDevice(array, device)}
                            disabled={busy}
                            className={`whitespace-nowrap rounded-lg border px-3 py-1.5 text-xs transition touch-manipulation active:scale-95 ${
                              busy
                                ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                                : 'border-rose-500/40 bg-rose-500/10 text-rose-200 hover:border-rose-500/60'
                            }`}
                          >
                            {t('system:raid.actions.removeSpare')}
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Mobile device cards */}
        <div className="lg:hidden space-y-3">
          {array.devices.map((device) => {
            const lowerState = device.state.toLowerCase();
            const allowFailure = canSimulateFailure(device);
            const allowRebuild = canStartRebuild(device);

            return (
              <div key={`${array.name}-${device.name}-mobile`} className="rounded-xl border border-slate-800/60 bg-slate-900/60 p-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-slate-200">/dev/{device.name}</span>
                  <span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${getDeviceStyle(lowerState)}`}>
                    {upcase(lowerState)}
                  </span>
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  <button
                    onClick={() => onSimulateFailure(array, device)}
                    disabled={busy || !allowFailure}
                    className={`rounded-lg border px-2 py-1 text-[10px] transition touch-manipulation active:scale-95 ${
                      busy || !allowFailure
                        ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                        : 'border-amber-500/40 bg-amber-500/10 text-amber-100'
                    }`}
                  >
                    Degrade
                  </button>
                  <button
                    onClick={() => onStartRebuild(array, device)}
                    disabled={busy || !allowRebuild}
                    className={`rounded-lg border px-2 py-1 text-[10px] transition touch-manipulation active:scale-95 ${
                      busy || !allowRebuild
                        ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                        : 'border-sky-500/50 bg-sky-500/10 text-sky-100'
                    }`}
                  >
                    Rebuild
                  </button>
                  <button
                    onClick={() => onWriteMostly(array, device)}
                    disabled={busy || !['active', 'write-mostly'].includes(lowerState)}
                    className={`rounded-lg border px-2 py-1 text-[10px] transition touch-manipulation active:scale-95 ${
                      busy || !['active', 'write-mostly'].includes(lowerState)
                        ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                        : 'border-slate-700/70 bg-slate-900/60 text-slate-200'
                    }`}
                  >
                    {lowerState === 'write-mostly' ? 'RW' : 'WM'}
                  </button>
                  {lowerState === 'spare' && (
                    <button
                      onClick={() => onRemoveDevice(array, device)}
                      disabled={busy}
                      className={`rounded-lg border px-2 py-1 text-[10px] transition touch-manipulation active:scale-95 ${
                        busy
                          ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                          : 'border-rose-500/40 bg-rose-500/10 text-rose-200'
                      }`}
                    >
                      {t('system:raid.actions.remove')}
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* SSD Cache Panel */}
      {array.cache ? (
        <SsdCachePanel
          cache={array.cache}
          onRefresh={onRefresh}
        />
      ) : (
        <div className="border-t border-slate-800/60 px-4 sm:px-6 py-3 sm:py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-xs text-slate-500">
              <Zap className="h-3.5 w-3.5" />
              <span>{t('system:raid.cache.noCache')}</span>
            </div>
            <button
              onClick={() => onSetupCache(array.name)}
              disabled={busy || availableDisks.filter(d => d.is_ssd && !d.is_os_disk && !d.in_raid && !d.is_cache_device).length === 0}
              className={`rounded-lg border px-3 py-1.5 text-xs transition touch-manipulation active:scale-95 ${
                busy || availableDisks.filter(d => d.is_ssd && !d.is_os_disk && !d.in_raid && !d.is_cache_device).length === 0
                  ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                  : 'border-cyan-500/30 bg-cyan-500/10 text-cyan-200 hover:border-cyan-500/50'
              }`}
            >
              {t('system:raid.cache.actions.setup')}
            </button>
          </div>
        </div>
      )}

      <div className="border-t border-slate-800/60 px-4 sm:px-6 py-4 sm:py-5">
        <div className="grid gap-3 sm:gap-5 md:grid-cols-2">
          <form onSubmit={(event) => onAddSpare(event, array)} className="rounded-xl border border-slate-800 bg-slate-900/60 px-3 sm:px-4 py-3 sm:py-4 text-xs sm:text-sm text-slate-300">
            <p className="text-[10px] sm:text-xs uppercase tracking-[0.24em] text-slate-500">{t('system:raid.labels.addSpare')}</p>
            <div className="mt-2 sm:mt-3 flex items-center gap-2 sm:gap-3">
              <input
                name="spare-device"
                placeholder={t('system:raid.labels.sparePlaceholder')}
                className="flex-1 rounded-lg border border-slate-800 bg-slate-950/70 px-2 sm:px-3 py-1.5 sm:py-2 text-xs sm:text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
              />
              <button
                type="submit"
                disabled={busy}
                className={`rounded-lg border px-3 py-1.5 sm:py-2 text-[10px] sm:text-xs font-medium transition touch-manipulation active:scale-95 ${
                  busy
                    ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                    : 'border-emerald-500/40 bg-emerald-500/15 text-emerald-100 hover:border-emerald-500/60'
                }`}
              >
                {t('system:raid.actions.add')}
              </button>
            </div>
          </form>

          <form onSubmit={(event) => onUpdateSpeed(event, array)} className="rounded-xl border border-slate-800 bg-slate-900/60 px-3 sm:px-4 py-3 sm:py-4 text-xs sm:text-sm text-slate-300">
            <p className="text-[10px] sm:text-xs uppercase tracking-[0.24em] text-slate-500">{t('system:raid.labels.syncLimitsKbs')}</p>
            <div className="mt-2 sm:mt-3 grid grid-cols-2 gap-2 sm:gap-3">
              <input
                name="speed-min"
                type="number"
                min={0}
                placeholder={speedLimits?.minimum?.toString() ?? t('system:raid.labels.min')}
                className="rounded-lg border border-slate-800 bg-slate-950/70 px-2 sm:px-3 py-1.5 sm:py-2 text-xs sm:text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
              />
              <input
                name="speed-max"
                type="number"
                min={0}
                placeholder={speedLimits?.maximum?.toString() ?? t('system:raid.labels.max')}
                className="rounded-lg border border-slate-800 bg-slate-950/70 px-2 sm:px-3 py-1.5 sm:py-2 text-xs sm:text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
              />
            </div>
            <button
              type="submit"
              disabled={busy}
              className={`mt-2 sm:mt-3 w-full sm:w-auto rounded-lg border px-3 py-1.5 sm:py-2 text-[10px] sm:text-xs font-medium transition touch-manipulation active:scale-95 ${
                busy
                  ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                  : 'border-slate-700/70 bg-slate-900/60 text-slate-200 hover:border-sky-500/40 hover:text-white'
              }`}
            >
              {t('system:raid.actions.apply')}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
};
