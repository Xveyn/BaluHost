/**
 * Check if a time (HH:MM) falls within a sleep window.
 * Handles overnight windows (e.g. 23:00-06:00).
 */
export function isTimeInSleepWindow(
  syncTime: string,
  sleepTime: string,
  wakeTime: string,
): boolean {
  if (sleepTime === wakeTime) return false;

  const toMinutes = (t: string) => {
    const [h, m] = t.split(':').map(Number);
    return h * 60 + m;
  };

  const sync = toMinutes(syncTime);
  const sleep = toMinutes(sleepTime);
  const wake = toMinutes(wakeTime);

  if (sleep < wake) {
    // Normal window: e.g. 14:00-16:00
    return sync >= sleep && sync < wake;
  }
  // Overnight window: e.g. 23:00-06:00
  return sync >= sleep || sync < wake;
}
