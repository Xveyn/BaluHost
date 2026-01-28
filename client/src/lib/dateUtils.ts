/**
 * Date utility functions for consistent timestamp handling.
 *
 * The backend sends UTC timestamps without timezone suffix (e.g., "2026-01-28T19:41:47").
 * JavaScript's Date constructor interprets such strings as local time.
 * These utilities ensure timestamps are correctly interpreted as UTC.
 */

/**
 * Parse a timestamp string as UTC.
 * If the timestamp lacks a timezone indicator, append 'Z' to treat it as UTC.
 *
 * @param timestamp - ISO timestamp string (with or without timezone)
 * @returns Date object correctly interpreted as UTC
 */
export function parseUtcTimestamp(timestamp: string): Date {
  // If timestamp already has timezone info (Z or +/-offset), use as-is
  if (timestamp.endsWith('Z') || /[+-]\d{2}:?\d{2}$/.test(timestamp)) {
    return new Date(timestamp);
  }
  // Otherwise, append 'Z' to interpret as UTC
  return new Date(timestamp + 'Z');
}

/**
 * Format a UTC timestamp to local time string.
 *
 * @param timestamp - ISO timestamp string from backend (UTC)
 * @param locale - Locale for formatting (default: 'de-DE')
 * @returns Formatted time string (HH:MM:SS)
 */
export function formatTimestamp(timestamp: string, locale = 'de-DE'): string {
  const date = parseUtcTimestamp(timestamp);
  return date.toLocaleTimeString(locale, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

/**
 * Format a UTC timestamp to local date string.
 *
 * @param timestamp - ISO timestamp string from backend (UTC)
 * @param locale - Locale for formatting (default: 'de-DE')
 * @returns Formatted date string
 */
export function formatDate(timestamp: string, locale = 'de-DE'): string {
  const date = parseUtcTimestamp(timestamp);
  return date.toLocaleDateString(locale);
}

/**
 * Format a UTC timestamp to local date and time string.
 *
 * @param timestamp - ISO timestamp string from backend (UTC)
 * @param locale - Locale for formatting (default: 'de-DE')
 * @returns Formatted date and time string
 */
export function formatDateTime(timestamp: string, locale = 'de-DE'): string {
  const date = parseUtcTimestamp(timestamp);
  return date.toLocaleString(locale);
}
