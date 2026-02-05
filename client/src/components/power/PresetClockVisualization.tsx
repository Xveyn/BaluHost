/**
 * PresetClockVisualization -- bar chart showing clock speeds per power property.
 */

import type { ServicePowerProperty } from '../../api/power-management';
import { PROPERTY_INFO, formatClockSpeed, type PowerPreset } from '../../api/power-management';

interface PresetClockVisualizationProps {
  preset: PowerPreset;
  currentProperty?: ServicePowerProperty;
  t: (key: string, options?: Record<string, unknown>) => string;
}

export function PresetClockVisualization({ preset, currentProperty, t }: PresetClockVisualizationProps) {
  const properties: ServicePowerProperty[] = ['idle', 'low', 'medium', 'surge'];
  const maxClock = Math.max(preset.idle_clock_mhz, preset.low_clock_mhz, preset.medium_clock_mhz, preset.surge_clock_mhz);

  const getClockForProperty = (prop: ServicePowerProperty): number => {
    switch (prop) {
      case 'idle': return preset.idle_clock_mhz;
      case 'low': return preset.low_clock_mhz;
      case 'medium': return preset.medium_clock_mhz;
      case 'surge': return preset.surge_clock_mhz;
    }
  };

  return (
    <div className="space-y-3">
      {properties.map((prop) => {
        const clock = getClockForProperty(prop);
        const percentage = (clock / maxClock) * 100;
        const isActive = prop === currentProperty;
        const info = PROPERTY_INFO[prop];

        return (
          <div key={prop} className={`${isActive ? 'opacity-100' : 'opacity-70'}`}>
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-2">
                <span className="text-sm">{info.icon}</span>
                <span className="text-sm font-medium text-white">{info.name}</span>
                {isActive && (
                  <span className="px-1.5 py-0.5 text-[10px] bg-emerald-500/20 text-emerald-300 rounded">{t('system:power.activeLabel')}</span>
                )}
              </div>
              <span className="text-sm text-slate-400">{formatClockSpeed(clock)}</span>
            </div>
            <div className="h-2 bg-slate-700/50 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-300 ${
                  isActive ? 'bg-emerald-500' :
                  prop === 'surge' ? 'bg-red-500/70' :
                  prop === 'medium' ? 'bg-yellow-500/70' :
                  prop === 'low' ? 'bg-blue-500/70' :
                  'bg-emerald-500/70'
                }`}
                style={{ width: `${percentage}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
