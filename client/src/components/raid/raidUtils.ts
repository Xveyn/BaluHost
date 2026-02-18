import type { RaidArray, RaidDevice } from '../../api/raid';

export const statusStyles: Record<string, string> = {
  optimal: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200',
  checking: 'border-indigo-500/40 bg-indigo-500/15 text-indigo-100',
  rebuilding: 'border-sky-500/40 bg-sky-500/15 text-sky-100',
  degraded: 'border-amber-500/40 bg-amber-500/15 text-amber-100',
  inactive: 'border-slate-600/50 bg-slate-800/60 text-slate-300',
};

export const deviceStyles: Record<string, string> = {
  active: 'border-emerald-400/30 bg-emerald-500/10 text-emerald-200',
  rebuilding: 'border-sky-400/30 bg-sky-500/10 text-sky-100',
  failed: 'border-rose-500/40 bg-rose-500/15 text-rose-200',
  removed: 'border-rose-500/30 bg-rose-500/10 text-rose-200',
  spare: 'border-indigo-400/30 bg-indigo-500/10 text-indigo-100',
  blocked: 'border-amber-500/30 bg-amber-500/10 text-amber-100',
  'write-mostly': 'border-amber-500/30 bg-amber-500/10 text-amber-100',
};

export const getStatusStyle = (status: string): string =>
  statusStyles[status] ?? 'border-slate-700/70 bg-slate-900/65 text-slate-200';

export const getDeviceStyle = (state: string): string =>
  deviceStyles[state] ?? 'border-slate-700/60 bg-slate-900/60 text-slate-300';

export const upcase = (value: string): string =>
  value.charAt(0).toUpperCase() + value.slice(1);

export const canStartRebuild = (device: RaidDevice): boolean =>
  device.state === 'failed';

export const canSimulateFailure = (device: RaidDevice): boolean =>
  ['active', 'spare', 'write-mostly'].includes(device.state);

export const shouldShowFinalize = (array: RaidArray): boolean =>
  ['rebuilding', 'degraded'].includes(array.status.toLowerCase());
