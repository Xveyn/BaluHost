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

/**
 * Time range types used by charts for dynamic X-axis formatting.
 */
export type ChartTimeRange = '10m' | '1h' | '24h' | '7d' | 'today' | 'week' | 'month';

/**
 * Format a timestamp for chart X-axis based on the selected time range.
 *
 * | Range         | Format              | Example (de) |
 * |---------------|---------------------|--------------|
 * | 10m, 1h, 24h, today | HH:mm        | 14:30        |
 * | 7d, week      | Weekday + HH:mm    | Mo 14:00     |
 * | month         | dd.MM.             | 15.01.       |
 *
 * @param timestamp - ISO string, epoch ms, or Date
 * @param range - The currently selected time range
 * @param locale - Locale for formatting (default: 'de')
 */
export function formatTimeForRange(
  timestamp: string | number | Date,
  range: ChartTimeRange,
  locale: string = 'de'
): string {
  const date = timestamp instanceof Date
    ? timestamp
    : typeof timestamp === 'string'
      ? parseUtcTimestamp(timestamp)
      : new Date(timestamp);

  switch (range) {
    case '10m':
    case '1h':
    case '24h':
    case 'today':
      return date.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' });
    case '7d':
    case 'week':
      return date.toLocaleDateString(locale, { weekday: 'short' })
        + ' ' + date.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' });
    case 'month':
      return date.toLocaleDateString(locale, { day: '2-digit', month: '2-digit' });
  }
}
