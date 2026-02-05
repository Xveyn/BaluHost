/**
 * StatCard -- a reusable stat-display card used across
 * SystemMonitor, PowerManagement, and other pages.
 */

interface StatCardProps {
  label: string;
  value: string | number;
  unit?: string;
  subValue?: string;
  color: string;
  icon: React.ReactNode;
}

export function StatCard({ label, value, unit, subValue, color, icon }: StatCardProps) {
  return (
    <div className={`card border-${color}-500/20 bg-gradient-to-br from-${color}-500/10 to-transparent p-3 sm:p-5`}>
      <div className="flex items-center justify-between">
        <div className="min-w-0 flex-1">
          <p className="text-[10px] sm:text-xs font-medium uppercase tracking-wider text-slate-400 truncate">{label}</p>
          <p className="mt-1 sm:mt-2 text-lg sm:text-2xl font-semibold text-white truncate">
            {value}
            {unit && <span className="ml-1 text-sm sm:text-lg text-slate-400">{unit}</span>}
          </p>
          {subValue && <p className="mt-0.5 sm:mt-1 text-xs sm:text-sm text-slate-400 truncate">{subValue}</p>}
        </div>
        <div className={`rounded-full bg-${color}-500/20 p-2 sm:p-3 flex-shrink-0 ml-2`}>{icon}</div>
      </div>
    </div>
  );
}
