/**
 * Shared formatting utilities.
 *
 * Canonical implementations – every page should import from here
 * instead of defining local copies.
 */

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
  return `${size >= 100 ? Math.round(size) : size.toFixed(size < 10 ? 2 : 1)} ${units[exponent]}`;
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
  return `${value.toFixed(decimals)}%`;
};
