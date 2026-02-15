import { useState, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { getRaidStatus } from '../../api/raid';
import { fetchSmartStatus, getSmartMode, toggleSmartMode, runSmartTest } from '../../api/smart';
import type { RaidStatusResponse, RaidArray, RaidDevice } from '../../api/raid';
import type { SmartStatusResponse, SmartDevice, SmartAttribute, SmartModeResponse } from '../../api/smart';
import type { SchedulerStatus } from '../../api/schedulers';
import { formatRelativeTime, getStatusColor } from '../../api/schedulers';
import { useAsyncData } from '../../hooks/useAsyncData';
import { inferStatusLevel, getStatusClasses } from '../../lib/statusColors';
import { formatBytes } from '../../lib/formatters';
import { HardDrive, Activity, RefreshCw, Loader2, ChevronDown, ChevronUp, Database, Search, CheckCircle2, XCircle } from 'lucide-react';

function StatusBadge({ status }: { status?: string }) {
  const level = inferStatusLevel(status || 'unknown');
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${getStatusClasses(level)}`}>
      {status ?? 'unknown'}
    </span>
  );
}

function ProgressBar({ value }: { value?: number | null }) {
  const pct = value == null ? 0 : Math.max(0, Math.min(100, Math.round(value * 100)));
  return (
    <div className="mt-2 w-full rounded bg-slate-800/60">
      <div className="h-2 rounded bg-sky-500" style={{ width: `${pct}%` }} />
    </div>
  );
}

function LastRunInfo({ scheduler }: { scheduler: SchedulerStatus | undefined }) {
  const { t } = useTranslation('scheduler');
  if (!scheduler) return null;

  return (
    <span className="text-xs text-slate-400">
      {scheduler.last_run_at ? (
        <>
          {formatRelativeTime(scheduler.last_run_at)}
          {scheduler.last_status && (
            <span className={`ml-1.5 ${getStatusColor(scheduler.last_status)}`}>
              ({t(`status.${scheduler.last_status}`)})
            </span>
          )}
        </>
      ) : (
        t('card.neverRun')
      )}
    </span>
  );
}

function SmartAttributeRow({ attr }: { attr: SmartAttribute }) {
  const { t } = useTranslation('scheduler');
  const [expanded, setExpanded] = useState(false);

  return (
    <>
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-xs hover:bg-slate-800/60 transition-colors"
      >
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-slate-500 w-6 text-right shrink-0">#{attr.id}</span>
          <span className="text-slate-200 truncate">{attr.name}</span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <StatusBadge status={attr.status} />
          {expanded ? <ChevronUp className="h-3 w-3 text-slate-400" /> : <ChevronDown className="h-3 w-3 text-slate-400" />}
        </div>
      </button>
      {expanded && (
        <div className="mb-1 ml-2 rounded-md border border-slate-800 bg-slate-950/40 p-2">
          <table className="w-full text-xs">
            <tbody className="divide-y divide-slate-800/50">
              <tr>
                <td className="py-1 pr-3 text-slate-400">{t('maintenance.attrName')}</td>
                <td className="py-1 text-slate-200">{attr.name}</td>
              </tr>
              <tr>
                <td className="py-1 pr-3 text-slate-400">{t('maintenance.attrValue')}</td>
                <td className="py-1 text-slate-200">{attr.value}</td>
              </tr>
              <tr>
                <td className="py-1 pr-3 text-slate-400">{t('maintenance.attrWorst')}</td>
                <td className="py-1 text-slate-200">{attr.worst}</td>
              </tr>
              <tr>
                <td className="py-1 pr-3 text-slate-400">{t('maintenance.attrThreshold')}</td>
                <td className="py-1 text-slate-200">{attr.threshold}</td>
              </tr>
              <tr>
                <td className="py-1 pr-3 text-slate-400">{t('maintenance.attrRaw')}</td>
                <td className="py-1 font-mono text-slate-200">{attr.raw}</td>
              </tr>
              <tr>
                <td className="py-1 pr-3 text-slate-400">{t('maintenance.attrStatus')}</td>
                <td className="py-1"><StatusBadge status={attr.status} /></td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

interface MaintenancePanelProps {
  addToast: (message: string, type: 'success' | 'error' | 'info') => void;
  schedulers: SchedulerStatus[];
  onRunNow: (name: string) => Promise<void>;
}

export function MaintenancePanel({ addToast, schedulers, onRunNow }: MaintenancePanelProps) {
  const { t } = useTranslation(['scheduler', 'common']);
  const [selectedDevice, setSelectedDevice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Dev-mode detection
  const { data: modeData } = useAsyncData<{ dev_mode: boolean }>(
    () => fetch('/api/system/mode').then(r => r.json()),
  );
  const isDevMode = modeData?.dev_mode === true;

  // RAID status with auto-refresh
  const { data: raidData, loading: raidLoading } = useAsyncData<RaidStatusResponse>(
    () => getRaidStatus(),
    { refreshInterval: 30000 },
  );

  // SMART status with auto-refresh
  const { data: smartData, loading: smartLoading } = useAsyncData<SmartStatusResponse>(
    () => fetchSmartStatus(),
    { refreshInterval: 30000 },
  );

  // SMART mode only in dev mode
  const { data: smartModeData } = useAsyncData<SmartModeResponse>(
    () => getSmartMode(),
    { enabled: isDevMode },
  );

  // Auto-select first device when smart data loads
  const effectiveDevice = selectedDevice ?? smartData?.devices?.[0]?.name ?? null;

  // Find scheduler info for last-run display
  const scrubScheduler = useMemo(
    () => schedulers.find(s => s.name === 'raid_scrub'),
    [schedulers],
  );
  const smartScanScheduler = useMemo(
    () => schedulers.find(s => s.name === 'smart_scan'),
    [schedulers],
  );

  const initialLoading = raidLoading && !raidData && smartLoading && !smartData;

  const handleRaidScrub = async () => {
    setBusy(true);
    try {
      await onRunNow('raid_scrub');
    } finally {
      setBusy(false);
    }
  };

  const handleSmartTest = async () => {
    setBusy(true);
    try {
      const device = effectiveDevice;
      if (!device) throw new Error(t('scheduler:maintenance.noDeviceSelected'));
      const res = await runSmartTest({ device, type: 'short' });
      addToast(res.message || t('scheduler:maintenance.smartTestStarted'), 'success');
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : t('scheduler:maintenance.smartTestFailed');
      addToast(message, 'error');
    } finally {
      setBusy(false);
    }
  };

  const handleToggleSmart = async () => {
    setBusy(true);
    try {
      const res = await toggleSmartMode();
      addToast(res.message || t('scheduler:maintenance.smartMode', { mode: res.mode }), 'success');
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : t('scheduler:maintenance.toggleFailed');
      addToast(message, 'error');
    } finally {
      setBusy(false);
    }
  };

  if (initialLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
      </div>
    );
  }

  return (
    <>
      {/* Action buttons */}
      <div className="flex flex-wrap gap-2 mb-6">
        <button
          onClick={handleRaidScrub}
          disabled={busy}
          className="inline-flex items-center gap-2 min-h-[44px] rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50 transition-colors"
        >
          <HardDrive className="h-4 w-4" />
          {t('scheduler:maintenance.triggerRaidScrub')}
        </button>
        <button
          onClick={handleSmartTest}
          disabled={busy}
          className="inline-flex items-center gap-2 min-h-[44px] rounded-md bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-700 disabled:opacity-50 transition-colors"
        >
          <Activity className="h-4 w-4" />
          {t('scheduler:maintenance.runSmartShort')}
        </button>
        {isDevMode && (
          <button
            onClick={handleToggleSmart}
            disabled={busy}
            className="inline-flex items-center gap-2 min-h-[44px] rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-700 disabled:opacity-50 transition-colors"
          >
            <RefreshCw className="h-4 w-4" />
            {t('scheduler:maintenance.toggleSmartMode')}
          </button>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* RAID Status */}
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-medium text-white flex items-center gap-2">
              <HardDrive className="h-5 w-5" />
              {t('scheduler:maintenance.raidStatus')}
            </h3>
            <LastRunInfo scheduler={scrubScheduler} />
          </div>
          <div className="space-y-4">
            {raidData?.arrays?.length ? (
              raidData.arrays.map((a: RaidArray) => (
                <div key={a.name} className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                    <div>
                      <div className="text-sm font-medium text-white">
                        {a.name} <span className="text-xs text-slate-400">({a.level})</span>
                      </div>
                      <div className="text-xs text-slate-400">
                        {t('scheduler:maintenance.size')}: {a.size_bytes ? formatBytes(a.size_bytes) : 'n/a'}
                      </div>
                    </div>
                    <StatusBadge status={a.status || a.sync_action || undefined} />
                  </div>

                  {a.resync_progress != null && (
                    <div className="mt-3">
                      <div className="text-xs text-slate-400">{t('scheduler:maintenance.resyncProgress')}</div>
                      <ProgressBar value={a.resync_progress} />
                      <div className="mt-1 text-xs text-slate-400">
                        {Math.round((a.resync_progress || 0) * 100)}%
                      </div>
                    </div>
                  )}

                  <div className="mt-3 text-xs">
                    <div className="text-slate-400 mb-1">{t('scheduler:maintenance.devices')}</div>
                    <div className="flex flex-wrap gap-2">
                      {a.devices?.map((d: RaidDevice) => (
                        <div
                          key={d.name}
                          className="rounded-md border border-slate-800 bg-slate-900/60 px-2 py-1 text-xs"
                        >
                          {d.name}{' '}
                          <span className="text-[10px] text-slate-400">{d.state}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div className="flex flex-col items-center justify-center py-8 text-slate-400">
                <Database className="h-8 w-8 mb-2 opacity-40" />
                <p className="text-sm">{t('scheduler:maintenance.noArrays')}</p>
              </div>
            )}
          </div>
        </div>

        {/* SMART Status */}
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-medium text-white flex items-center gap-2">
              <Activity className="h-5 w-5" />
              {t('scheduler:maintenance.smartStatus')}
            </h3>
            <LastRunInfo scheduler={smartScanScheduler} />
          </div>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <label className="text-xs text-slate-400">{t('scheduler:maintenance.device')}:</label>
                <select
                  value={effectiveDevice ?? ''}
                  onChange={(e) => setSelectedDevice(e.target.value || null)}
                  className="rounded-md border border-slate-700 bg-slate-800 px-2 py-1 text-sm text-white"
                >
                  {(smartData?.devices ?? []).map((d: SmartDevice) => (
                    <option key={d.name} value={d.name}>
                      {d.name}
                      {d.model ? ` - ${d.model}` : ''}
                    </option>
                  ))}
                </select>
              </div>
              {isDevMode && (
                <div className="text-xs text-slate-400">
                  {t('scheduler:maintenance.mode')}: <span className="text-slate-100">{smartModeData?.mode ?? t('common:status.unknown')}</span>
                </div>
              )}
            </div>

            {smartData?.devices?.length ? (
              smartData.devices.map((dev: SmartDevice) => (
                <SmartDeviceCard key={dev.name} dev={dev} />
              ))
            ) : (
              <div className="flex flex-col items-center justify-center py-8 text-slate-400">
                <Search className="h-8 w-8 mb-2 opacity-40" />
                <p className="text-sm">{t('scheduler:maintenance.noSmartDevices')}</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}

function SmartDeviceCard({ dev }: { dev: SmartDevice }) {
  const { t } = useTranslation('scheduler');
  const [expanded, setExpanded] = useState(false);
  const hasAttributes = dev.attributes && dev.attributes.length > 0;

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-sm font-medium text-white">{dev.model ?? dev.name}</div>
          <div className="text-xs text-slate-400">
            {dev.name} {dev.serial ? `- ${dev.serial}` : ''}
          </div>
        </div>
        <div className="flex flex-col items-end gap-2">
          <div className="text-xs">
            {t('maintenance.temp')}: <span className="font-medium">{dev.temperature ?? 'n/a'}</span>
            {dev.temperature != null ? 'C' : ''}
          </div>
          <StatusBadge status={dev.status} />
        </div>
      </div>

      {/* Last self-test result */}
      {dev.last_self_test && (
        <div className="mt-3 rounded-md border border-slate-800 bg-slate-900/40 px-3 py-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-300">{t('maintenance.lastSelfTest')}</span>
            {dev.last_self_test.passed ? (
              <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-400">
                <CheckCircle2 className="h-3 w-3" />
                PASSED
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 rounded-full border border-red-500/30 bg-red-500/10 px-2 py-0.5 text-[10px] font-medium text-red-400">
                <XCircle className="h-3 w-3" />
                FAILED
              </span>
            )}
          </div>
          <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-400">
            <span>{dev.last_self_test.test_type}</span>
            <span>{dev.last_self_test.status}</span>
            <span>{t('maintenance.powerOnHours')}: {dev.last_self_test.power_on_hours.toLocaleString()}h</span>
          </div>
        </div>
      )}

      {/* Expandable attributes */}
      <div className="mt-3">
        <button
          onClick={() => setExpanded(!expanded)}
          disabled={!hasAttributes}
          className="flex items-center gap-1 text-xs text-slate-400 hover:text-slate-300 transition-colors disabled:opacity-50 disabled:cursor-default"
        >
          {t('maintenance.attributes')}: {dev.attributes?.length ?? 0}
          {hasAttributes && (
            expanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />
          )}
        </button>
        {expanded && hasAttributes && (
          <div className="mt-2 space-y-0.5">
            {dev.attributes.map((attr: SmartAttribute) => (
              <SmartAttributeRow key={attr.id} attr={attr} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
