export function usageBarColor(percent: number, warn: number, crit: number): string {
  return percent >= crit ? 'bg-red-500' : percent >= warn ? 'bg-amber-500' : 'bg-sky-500';
}
