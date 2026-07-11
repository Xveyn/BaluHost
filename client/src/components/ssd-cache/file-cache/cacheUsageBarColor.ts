export function cacheUsageBarColor(usagePercent: number): string {
  return usagePercent >= 90 ? 'bg-red-500' : usagePercent >= 70 ? 'bg-amber-500' : 'bg-cyan-500';
}
