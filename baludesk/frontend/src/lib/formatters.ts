/**
 * Formatting utilities for common data types
 */

/**
 * Format bytes to human-readable size (B, KB, MB, GB, TB)
 */
export const formatBytes = (bytes: number): string => {
  if (!bytes || Number.isNaN(bytes)) return '0 B';
  const k = 1024;
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  const value = bytes / Math.pow(k, i);
  return `${value.toFixed(value >= 100 ? 1 : 2)} ${units[i]}`;
};

/**
 * Format bytes with a simpler calculation (rounded)
 */
export const formatSize = (bytes?: number): string => {
  if (!bytes) return 'Unknown';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let size = bytes;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex++;
  }
  return `${size.toFixed(2)} ${units[unitIndex]}`;
};

/**
 * Format uptime in seconds to human-readable format
 */
export const formatUptime = (seconds: number): string => {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const mins = Math.floor((seconds % 3600) / 60);

  if (days > 0) {
    return `${days}d ${hours}h`;
  } else if (hours > 0) {
    return `${hours}h ${mins}m`;
  } else {
    return `${mins}m`;
  }
};

/**
 * Format ISO date string to localized format
 */
export const formatDate = (dateString: string): string => {
  try {
    return new Date(dateString).toLocaleString();
  } catch {
    return dateString;
  }
};

/**
 * Format ISO date string to short format (YYYY-MM-DD)
 */
export const formatDateShort = (dateString: string): string => {
  try {
    const date = new Date(dateString);
    return date.toISOString().split('T')[0];
  } catch {
    return dateString;
  }
};

/**
 * Format ISO date string to time only (HH:MM:SS)
 */
export const formatTime = (dateString: string): string => {
  try {
    const date = new Date(dateString);
    return date.toLocaleTimeString();
  } catch {
    return dateString;
  }
};
