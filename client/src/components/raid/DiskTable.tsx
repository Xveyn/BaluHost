import { useTranslation } from 'react-i18next';
import type { AvailableDisk, RaidArray } from '../../api/raid';
import { formatBytes } from '../../lib/formatters';
import { Monitor, Zap } from 'lucide-react';

export interface DiskTableProps {
  availableDisks: AvailableDisk[];
  arrays: RaidArray[];
  busy: boolean;
  isDevMode: boolean;
  onRefreshDisks: () => void;
  onShowMockWizard: () => void;
  onShowCreateArray: () => void;
  onFormatDisk: (disk: AvailableDisk) => void;
}

export const DiskTable: React.FC<DiskTableProps> = ({
  availableDisks,
  arrays,
  busy,
  isDevMode,
  onRefreshDisks,
  onShowMockWizard,
  onShowCreateArray,
  onFormatDisk,
}) => {
  const { t } = useTranslation(['system', 'common']);

  return (
    <div className="card border-slate-800/60 bg-slate-900/55">
      <div className="border-b border-slate-800/60 px-4 sm:px-6 py-4 sm:py-5">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4">
          <div>
            <h2 className="text-lg sm:text-xl font-semibold text-white">{t('system:raid.diskManagement.title')}</h2>
            <p className="mt-1 text-xs sm:text-sm text-slate-400">{t('system:raid.diskManagement.subtitle')}</p>
          </div>
          <div className="flex gap-2 overflow-x-auto pb-2 sm:pb-0">
            <button
              onClick={onRefreshDisks}
              disabled={busy}
              className={`whitespace-nowrap rounded-xl border px-3 sm:px-4 py-1.5 sm:py-2 text-xs sm:text-sm transition touch-manipulation active:scale-95 ${
                busy
                  ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                  : 'border-sky-500/30 bg-sky-500/10 text-sky-200 hover:border-sky-500/50 hover:bg-sky-500/15'
              }`}
            >
              {t('system:raid.actions.refresh')}
            </button>
            {isDevMode && (
              <button
                onClick={onShowMockWizard}
                disabled={busy}
                className={`whitespace-nowrap rounded-xl border px-3 sm:px-4 py-1.5 sm:py-2 text-xs sm:text-sm transition touch-manipulation active:scale-95 ${
                  busy
                    ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                    : 'border-violet-500/40 bg-violet-500/15 text-violet-100 hover:border-violet-500/60'
                }`}
                title={t('system:raid.diskManagement.devModeAddMock')}
              >
                🧪 <span className="hidden sm:inline">{t('system:raid.actions.addMock')}</span>
              </button>
            )}
            <button
              onClick={onShowCreateArray}
              disabled={busy || availableDisks.filter(d => !d.in_raid && !d.is_os_disk).length < 2}
              className={`whitespace-nowrap rounded-xl border px-3 sm:px-4 py-1.5 sm:py-2 text-xs sm:text-sm transition touch-manipulation active:scale-95 ${
                busy || availableDisks.filter(d => !d.in_raid && !d.is_os_disk).length < 2
                  ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                  : 'border-emerald-500/40 bg-emerald-500/15 text-emerald-100 hover:border-emerald-500/60'
              }`}
              title={availableDisks.filter(d => !d.in_raid && !d.is_os_disk).length < 2 ? t('system:raid.diskManagement.minDisksRequired') : ''}
            >
              {t('system:raid.actions.createNewArray')}
            </button>
          </div>
        </div>
      </div>

      <div className="px-4 sm:px-6 py-4 sm:py-5">
        {/* Desktop disk table */}
        <div className="hidden lg:block overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-800/60">
            <thead>
              <tr className="text-left text-xs uppercase tracking-[0.24em] text-slate-500">
                <th className="px-5 py-3">{t('system:raid.tableHeaders.name')}</th>
                <th className="px-5 py-3">{t('system:raid.tableHeaders.size')}</th>
                <th className="px-5 py-3">{t('system:raid.tableHeaders.model')}</th>
                <th className="px-5 py-3">{t('system:raid.tableHeaders.status')}</th>
                <th className="px-5 py-3">{t('system:raid.tableHeaders.actions')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {availableDisks.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-5 py-8 text-center text-sm text-slate-400">
                    {t('system:raid.diskManagement.noDisks')}
                  </td>
                </tr>
              ) : (
                availableDisks.map((disk) => (
                  <tr key={disk.name} className="group transition hover:bg-slate-900/65">
                    <td className="px-5 py-4 text-sm font-medium text-slate-200">/dev/{disk.name}</td>
                    <td className="px-5 py-4 text-sm text-slate-300">{formatBytes(disk.size_bytes)}</td>
                    <td className="px-5 py-4 text-sm text-slate-300">{disk.model || t('system:raid.diskManagement.na')}</td>
                    <td className="px-5 py-4">
                      <div className="flex flex-wrap items-center gap-2">
                        {disk.in_raid ? (
                          (() => {
                            const diskArray = arrays.find(arr =>
                              arr.devices.some(dev => dev.name === `${disk.name}1` || dev.name === disk.name)
                            );
                            return diskArray ? (
                              <div className="flex items-center gap-2 rounded-full border border-sky-400/30 bg-sky-500/10 px-3 py-1">
                                <svg className="h-3.5 w-3.5 text-sky-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                  <path strokeLinecap="round" strokeLinejoin="round" d="M5.25 14.25h13.5m-13.5 0a3 3 0 01-3-3m3 3a3 3 0 100 6h13.5a3 3 0 100-6m-16.5-3a3 3 0 013-3h13.5a3 3 0 013 3m-19.5 0a4.5 4.5 0 01.9-2.7L5.737 5.1a3.375 3.375 0 012.7-1.35h7.126c1.062 0 2.062.5 2.7 1.35l2.587 3.45a4.5 4.5 0 01.9 2.7m0 0a3 3 0 01-3 3m0 3h.008v.008h-.008v-.008zm0-6h.008v.008h-.008v-.008zm-3 6h.008v.008h-.008v-.008zm0-6h.008v.008h-.008v-.008z" />
                                </svg>
                                <span className="text-xs font-medium text-sky-100">{diskArray.name}</span>
                                <span className="text-[0.65rem] uppercase tracking-wider text-sky-300/70">{diskArray.level}</span>
                              </div>
                            ) : (
                              <span className="rounded-full border border-sky-400/30 bg-sky-500/10 px-2 py-0.5 text-xs text-sky-100">
                                {t('system:raid.diskManagement.inRaid')}
                              </span>
                            );
                          })()
                        ) : (
                          <span className="rounded-full border border-slate-700/50 bg-slate-800/40 px-2 py-0.5 text-xs text-slate-400">
                            {t('system:raid.diskManagement.free')}
                          </span>
                        )}
                        {disk.is_partitioned && (
                          <span className="rounded-full border border-amber-400/30 bg-amber-500/10 px-2 py-0.5 text-xs text-amber-100">
                            {t('system:raid.diskManagement.partitioned')}
                          </span>
                        )}
                        {disk.is_os_disk && (
                          <div className="flex items-center gap-1.5 rounded-full border border-violet-400/30 bg-violet-500/10 px-2.5 py-0.5">
                            <Monitor className="h-3 w-3 text-violet-400" />
                            <span className="text-xs font-medium text-violet-100">
                              {t('system:raid.diskManagement.osDisk')}
                            </span>
                          </div>
                        )}
                        {disk.is_ssd && !disk.is_os_disk && (
                          <div className="flex items-center gap-1 rounded-full border border-cyan-400/30 bg-cyan-500/10 px-2 py-0.5">
                            <Zap className="h-3 w-3 text-cyan-400" />
                            <span className="text-xs font-medium text-cyan-100">SSD</span>
                          </div>
                        )}
                        {disk.is_cache_device && (
                          <span className="rounded-full border border-teal-400/30 bg-teal-500/10 px-2 py-0.5 text-xs text-teal-100">
                            {t('system:raid.diskManagement.cacheDevice')}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-5 py-4">
                      <button
                        onClick={() => onFormatDisk(disk)}
                        disabled={busy || disk.in_raid || disk.is_os_disk || !!disk.is_cache_device}
                        className={`rounded-lg border px-3 py-1.5 text-xs transition ${
                          busy || disk.in_raid || disk.is_os_disk || disk.is_cache_device
                            ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                            : 'border-rose-500/40 bg-rose-500/10 text-rose-200 hover:border-rose-500/60'
                        }`}
                      >
                        {t('system:raid.actions.format')}
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Mobile disk cards */}
        <div className="lg:hidden space-y-3">
          {availableDisks.length === 0 ? (
            <p className="py-6 text-center text-sm text-slate-400">
              {t('system:raid.diskManagement.noDisks')}
            </p>
          ) : (
            availableDisks.map((disk) => {
              const diskArray = disk.in_raid
                ? arrays.find(arr => arr.devices.some(dev => dev.name === `${disk.name}1` || dev.name === disk.name))
                : null;

              return (
                <div key={`${disk.name}-mobile`} className="rounded-xl border border-slate-800/60 bg-slate-900/60 p-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-slate-200">/dev/{disk.name}</span>
                    <span className="text-xs text-slate-400">{formatBytes(disk.size_bytes)}</span>
                  </div>
                  {disk.model && (
                    <p className="mt-1 text-xs text-slate-500 truncate">{disk.model}</p>
                  )}
                  <div className="mt-2 flex flex-wrap items-center gap-1.5">
                    {disk.in_raid ? (
                      diskArray ? (
                        <div className="flex items-center gap-1.5 rounded-full border border-sky-400/30 bg-sky-500/10 px-2 py-0.5">
                          <span className="text-[10px] font-medium text-sky-100">{diskArray.name}</span>
                          <span className="text-[10px] uppercase text-sky-300/70">{diskArray.level}</span>
                        </div>
                      ) : (
                        <span className="rounded-full border border-sky-400/30 bg-sky-500/10 px-2 py-0.5 text-[10px] text-sky-100">
                          {t('system:raid.diskManagement.inRaid')}
                        </span>
                      )
                    ) : (
                      <span className="rounded-full border border-slate-700/50 bg-slate-800/40 px-2 py-0.5 text-[10px] text-slate-400">
                        {t('system:raid.diskManagement.free')}
                      </span>
                    )}
                    {disk.is_partitioned && (
                      <span className="rounded-full border border-amber-400/30 bg-amber-500/10 px-2 py-0.5 text-[10px] text-amber-100">
                        {t('system:raid.diskManagement.partitioned')}
                      </span>
                    )}
                    {disk.is_os_disk && (
                      <div className="flex items-center gap-1 rounded-full border border-violet-400/30 bg-violet-500/10 px-2 py-0.5">
                        <Monitor className="h-2.5 w-2.5 text-violet-400" />
                        <span className="text-[10px] font-medium text-violet-100">
                          {t('system:raid.diskManagement.osDisk')}
                        </span>
                      </div>
                    )}
                    {disk.is_ssd && !disk.is_os_disk && (
                      <div className="flex items-center gap-1 rounded-full border border-cyan-400/30 bg-cyan-500/10 px-2 py-0.5">
                        <Zap className="h-2.5 w-2.5 text-cyan-400" />
                        <span className="text-[10px] font-medium text-cyan-100">SSD</span>
                      </div>
                    )}
                    {disk.is_cache_device && (
                      <span className="rounded-full border border-teal-400/30 bg-teal-500/10 px-2 py-0.5 text-[10px] text-teal-100">
                        {t('system:raid.diskManagement.cacheDevice')}
                      </span>
                    )}
                    {!disk.in_raid && !disk.is_os_disk && (
                      <button
                        onClick={() => onFormatDisk(disk)}
                        disabled={busy}
                        className={`ml-auto rounded-lg border px-2 py-1 text-[10px] transition touch-manipulation active:scale-95 ${
                          busy
                            ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                            : 'border-rose-500/40 bg-rose-500/10 text-rose-200'
                        }`}
                      >
                        {t('system:raid.actions.format')}
                      </button>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
};
