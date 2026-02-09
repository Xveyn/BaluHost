/**
 * Shared formatting utilities.
 *
 * Canonical implementations – every page should import from here
 * instead of defining local copies.
 */

import i18n from '../i18n';

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
  const k = 1024;
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
  const exponent = Math.min(
    Math.floor(Math.log(bytes) / Math.log(k)),
    units.length - 1,
  );
  const size = bytes / k ** exponent;
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
