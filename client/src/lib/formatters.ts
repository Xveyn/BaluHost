/**
 * Shared formatting utilities.
 *
 * Canonical implementations – every page should import from here
 * instead of defining local copies.
 */

import i18n from '../i18n';
import { getByteUnitMode, getUnitConfig } from './byteUnits';

/** Locale-aware number formatting (de: "1,5" / en: "1.5"). */
export function formatNumber(value: number, decimals: number, locale?: string): string {
  return new Intl.NumberFormat(locale ?? i18n.language ?? 'de', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
    useGrouping: false,
  }).format(value);
}

/**
 * Format a byte count into a human-readable string (e.g. "1.50 GB").
 *
 * Handles zero, NaN, negative and very large values gracefully.
 */
export const formatBytes = (bytes: number): string => {
  if (!bytes || !Number.isFinite(bytes) || bytes <= 0) return '0 B';
  const { divisor, units } = getUnitConfig(getByteUnitMode());
  const exponent = Math.min(
    Math.floor(Math.log(bytes) / Math.log(divisor)),
    units.length - 1,
  );
  const size = bytes / divisor ** exponent;
  return `${size >= 100 ? Math.round(size) : formatNumber(size, size < 10 ? 2 : 1)} ${units[exponent]}`;
};

/**
 * Format a duration given in seconds into "Xd Yh Zm".
 */
export const formatUptime = (seconds: number): string => {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return `${days}d ${hours}h ${minutes}m`;
};

/**
 * Format a number as a percentage string (e.g. "42.5%").
 */
export const formatPercentage = (value: number, decimals = 1): string => {
  return `${formatNumber(value, decimals)}%`;
};

/**
 * Format an ETA given in seconds into a compact string (e.g. "5s", "2m 30s", "1h 15m").
 */
export function formatEta(seconds: number): string {
  if (seconds < 60) return `${Math.ceil(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.ceil(seconds % 60)}s`;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m}m`;
}

/**
 * Format a date string as a relative time (e.g. "Just now", "5m ago", "2h ago", "3d ago").
 * Handles future dates too (e.g. "in 5m", "in 3d", "in 89d").
 * Falls back to locale date string for dates more than 7 days in the past.
 * Returns "Never" for null/undefined input.
 */
export function formatRelativeTime(dateStr: string | null | undefined): string {
  if (!dateStr) return 'Never';
  const date = new Date(dateStr);
  const diffMs = Date.now() - date.getTime();

  // Future dates
  if (diffMs < 0) {
    const futureMins = Math.floor(-diffMs / 60000);
    if (futureMins < 1) return 'Just now';
    if (futureMins < 60) return `in ${futureMins}m`;
    const futureHours = Math.floor(futureMins / 60);
    if (futureHours < 24) return `in ${futureHours}h`;
    const futureDays = Math.floor(futureHours / 24);
    return `in ${futureDays}d`;
  }

  // Past dates
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}
