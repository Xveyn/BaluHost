/**
 * Shared helper functions for power management components.
 */

import type { ServicePowerProperty } from '../../api/power-management';

// Format timestamp for display
export const formatTimestamp = (ts: string): string => {
  const date = new Date(ts);
  return date.toLocaleString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
};

// Format relative time (e.g. "5 minutes ago")
export const formatRelativeTime = (ts: string, t: (key: string, options?: Record<string, unknown>) => string): string => {
  const now = new Date();
  const then = new Date(ts);
  const diffMs = now.getTime() - then.getTime();
  const diffSeconds = Math.floor(diffMs / 1000);
  const diffMinutes = Math.floor(diffSeconds / 60);
  const diffHours = Math.floor(diffMinutes / 60);

  if (diffSeconds < 60) return t('system:power.relativeTime.secondsAgo', { count: diffSeconds });
  if (diffMinutes < 60) return t('system:power.relativeTime.minutesAgo', { count: diffMinutes });
  if (diffHours < 24) return t('system:power.relativeTime.hoursAgo', { count: diffHours });
  return formatTimestamp(ts);
};

// Profile color classes based on power property
export const getPropertyColorClasses = (property: ServicePowerProperty): string => {
  const colors: Record<ServicePowerProperty, string> = {
    idle: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200',
    low: 'border-blue-500/30 bg-blue-500/10 text-blue-200',
    medium: 'border-yellow-500/30 bg-yellow-500/10 text-yellow-200',
    surge: 'border-red-500/30 bg-red-500/10 text-red-200',
  };
  return colors[property] || 'border-slate-600/50 bg-slate-800/60 text-slate-300';
};

// Preset color classes (active vs inactive)
export const getPresetColorClasses = (presetName: string, isActive: boolean): string => {
  if (!isActive) return 'border-slate-700/50 bg-slate-800/50 hover:border-slate-600 hover:bg-slate-800';

  if (presetName.includes('Energy') || presetName.includes('Saver')) {
    return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200 ring-2 ring-emerald-500/50 ring-offset-2 ring-offset-slate-900';
  }
  if (presetName.includes('Performance')) {
    return 'border-red-500/30 bg-red-500/10 text-red-200 ring-2 ring-red-500/50 ring-offset-2 ring-offset-slate-900';
  }
  return 'border-blue-500/30 bg-blue-500/10 text-blue-200 ring-2 ring-blue-500/50 ring-offset-2 ring-offset-slate-900';
};

// Get emoji icon for a preset name
export const getPresetIcon = (presetName: string): string => {
  if (presetName.includes('Energy') || presetName.includes('Saver')) return '🌱';
  if (presetName.includes('Performance')) return '🚀';
  if (presetName.includes('Balanced')) return '⚖️';
  return '⚙️';
};
