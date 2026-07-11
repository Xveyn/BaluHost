export function getCategoryColor(category: string): string {
  const colors: Record<string, string> = {
    monitoring: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
    storage: 'bg-green-500/20 text-green-400 border-green-500/30',
    network: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
    security: 'bg-red-500/20 text-red-400 border-red-500/30',
    general: 'bg-slate-500/20 text-slate-400 border-slate-500/30',
  };
  return colors[category] || colors.general;
}
