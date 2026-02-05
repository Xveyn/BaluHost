/**
 * Shared status-badge color mappings.
 */

export type StatusLevel = 'success' | 'warning' | 'error' | 'info' | 'neutral';

const statusMap: Record<StatusLevel, string> = {
  success: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
  warning: 'border-amber-500/30 bg-amber-500/10 text-amber-300',
  error: 'border-rose-500/30 bg-rose-500/10 text-rose-300',
  info: 'border-sky-500/30 bg-sky-500/10 text-sky-300',
  neutral: 'border-slate-500/30 bg-slate-500/10 text-slate-300',
};

export const getStatusClasses = (level: StatusLevel): string => statusMap[level];

/** Map common status strings to a StatusLevel */
export const inferStatusLevel = (status: string): StatusLevel => {
  const lower = status.toLowerCase();
  if (['clean', 'optimal', 'passed', 'running', 'active', 'healthy', 'ok'].includes(lower)) return 'success';
  if (['degraded', 'warning', 'rebuilding', 'write-mostly', 'disabled'].includes(lower)) return 'warning';
  if (['failed', 'error', 'critical', 'removed', 'inactive'].includes(lower)) return 'error';
  if (['syncing', 'checking', 'pending'].includes(lower)) return 'info';
  return 'neutral';
};
