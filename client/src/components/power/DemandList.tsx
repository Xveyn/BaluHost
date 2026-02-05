/**
 * DemandList -- displays a list of active power demands with optional unregister.
 */

import type { ServicePowerProperty, PowerDemandInfo } from '../../api/power-management';
import { PROPERTY_INFO } from '../../api/power-management';
import { PropertyBadge } from './PropertyBadge';
import { getPropertyColorClasses, formatRelativeTime, formatTimestamp } from './utils';

interface DemandListProps {
  demands: PowerDemandInfo[];
  onUnregister: (source: string) => void;
  isAdmin: boolean;
  t: (key: string, options?: Record<string, unknown>) => string;
}

export function DemandList({ demands, onUnregister, isAdmin, t }: DemandListProps) {
  if (demands.length === 0) {
    return (
      <div className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-4 sm:p-6 text-center text-sm sm:text-base text-slate-400">
        {t('system:power.noDemands')}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {demands.map((demand) => {
        const property = (demand.power_property || demand.level) as ServicePowerProperty;
        return (
          <div
            key={demand.source}
            className={`flex flex-col sm:flex-row sm:items-center justify-between rounded-lg border p-3 gap-2 sm:gap-3 ${getPropertyColorClasses(property)}`}
          >
            <div className="flex items-start sm:items-center gap-2 sm:gap-3 flex-1 min-w-0">
              <span className="text-lg sm:text-xl flex-shrink-0">{PROPERTY_INFO[property].icon}</span>
              <div className="min-w-0 flex-1">
                <p className="font-medium text-sm sm:text-base truncate">{demand.source}</p>
                {demand.description && <p className="text-xs sm:text-sm opacity-80 truncate">{demand.description}</p>}
                <p className="text-[10px] sm:text-xs opacity-60">
                  {t('system:power.registered')}: {formatRelativeTime(demand.registered_at, t)}
                  {demand.expires_at && <span className="hidden sm:inline"> &bull; {t('system:power.expiresAt')}: {formatTimestamp(demand.expires_at)}</span>}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2 self-end sm:self-auto">
              <PropertyBadge property={property} size="sm" />
              {isAdmin && (
                <button
                  onClick={() => onUnregister(demand.source)}
                  className="rounded p-2 text-slate-400 hover:bg-slate-700 hover:text-white touch-manipulation active:scale-95 min-w-[36px] min-h-[36px] flex items-center justify-center"
                  title={t('system:power.removeDemand')}
                >
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
