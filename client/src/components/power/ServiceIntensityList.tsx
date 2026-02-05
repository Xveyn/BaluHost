/**
 * ServiceIntensityList -- displays a list of services with their current power intensity.
 */

import type { ServicePowerProperty, ServiceIntensityInfo } from '../../api/power-management';
import { PROPERTY_INFO } from '../../api/power-management';

interface ServiceIntensityListProps {
  services: ServiceIntensityInfo[];
  t: (key: string, options?: Record<string, unknown>) => string;
}

export function ServiceIntensityList({ services, t }: ServiceIntensityListProps) {
  if (services.length === 0) {
    return (
      <div className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-4 sm:p-6 text-center text-sm sm:text-base text-slate-400">
        {t('system:power.serviceIntensity.noServices')}
      </div>
    );
  }

  const getIntensityColorClasses = (intensity: ServicePowerProperty): string => {
    const colors: Record<ServicePowerProperty, string> = {
      idle: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
      low: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
      medium: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/30',
      surge: 'bg-red-500/20 text-red-300 border-red-500/30',
    };
    return colors[intensity] || 'bg-slate-500/20 text-slate-300 border-slate-500/30';
  };

  const getStatusIndicatorColor = (service: ServiceIntensityInfo): string => {
    if (!service.is_alive) return 'bg-slate-500';
    if (service.intensity_level === 'surge') return 'bg-red-500 animate-pulse';
    if (service.intensity_level === 'medium') return 'bg-yellow-500';
    if (service.intensity_level === 'low') return 'bg-blue-500';
    return 'bg-emerald-500';
  };

  return (
    <div className="space-y-2">
      {services.map((service) => (
        <div
          key={service.name}
          className={`flex flex-col sm:flex-row sm:items-center justify-between rounded-lg border p-3 gap-2 sm:gap-3 ${
            service.is_alive ? 'border-slate-700/50 bg-slate-800/30' : 'border-slate-600/30 bg-slate-900/30 opacity-60'
          }`}
        >
          <div className="flex items-center gap-3 flex-1 min-w-0">
            {/* Status indicator */}
            <div className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${getStatusIndicatorColor(service)}`} />

            {/* Service info */}
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <p className="font-medium text-sm sm:text-base text-white truncate">{service.display_name}</p>
                {service.has_active_demand && (
                  <span className="px-1.5 py-0.5 text-[10px] bg-purple-500/20 text-purple-300 rounded border border-purple-500/30">
                    {t('system:power.serviceIntensity.activeDemand')}
                  </span>
                )}
              </div>

              {/* Metrics row */}
              <div className="flex items-center gap-3 text-xs text-slate-400 mt-0.5">
                {service.intensity_source === 'service' && (
                  <span className="text-slate-500">{t('system:power.serviceIntensity.backgroundService')}</span>
                )}
                {service.cpu_percent != null && (
                  <span>CPU: {service.cpu_percent.toFixed(1)}%</span>
                )}
                {service.memory_mb != null && (
                  <span>RAM: {service.memory_mb.toFixed(0)} MB</span>
                )}
                {service.demand_description && (
                  <span className="truncate">{service.demand_description}</span>
                )}
                {service.pid != null && (
                  <span className="text-slate-500">PID {service.pid}</span>
                )}
              </div>
            </div>
          </div>

          {/* Intensity badge */}
          <div className="flex items-center gap-2 self-end sm:self-auto">
            <span
              className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${getIntensityColorClasses(service.intensity_level)}`}
            >
              <span>{PROPERTY_INFO[service.intensity_level].icon}</span>
              <span>{PROPERTY_INFO[service.intensity_level].name}</span>
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}
