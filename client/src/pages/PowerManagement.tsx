/**
 * Power Management Page
 *
 * Provides CPU frequency scaling controls with:
 * - Preset selection (Energy Saver / Balanced / Performance)
 * - Current power property display
 * - Active power demands list
 * - Profile change history
 * - Auto-scaling configuration
 * - Custom preset editor
 */

import { useEffect, useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { AlertTriangle } from 'lucide-react';
import {
  getPowerStatus,
  getPowerDemands,
  unregisterPowerDemand,
  getPowerMgmtHistory,
  getAutoScalingConfig,
  updateAutoScalingConfig,
  switchPowerBackend,
  getServiceIntensities,
  PROFILE_INFO,
  type PowerStatusResponse,
  type PowerDemandInfo,
  type PowerHistoryEntry,
  type AutoScalingConfig,
  type ServicePowerProperty,
  type ServiceIntensityInfo,
} from '../api/power-management';
import {
  listPresets,
  activatePreset,
  createPreset,
  updatePreset,
  deletePreset,
  formatClockSpeed,
  PROPERTY_INFO,
  type PowerPreset,
  type CreatePresetRequest,
} from '../api/power-presets';
import { AdminBadge } from '../components/ui/AdminBadge';

const REFRESH_INTERVAL_MS = 5000;

// Format timestamp
const formatTimestamp = (ts: string): string => {
  const date = new Date(ts);
  return date.toLocaleString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
};

// Format relative time
const formatRelativeTime = (ts: string, t: (key: string, options?: Record<string, unknown>) => string): string => {
  const now = new Date();
  const then = new Date(ts);
  const diffMs = now.getTime() - then.getTime();
  const diffSeconds = Math.floor(diffMs / 1000);
  const diffMinutes = Math.floor(diffSeconds / 60);
  const diffHours = Math.floor(diffMinutes / 60);

  if (diffSeconds < 60) return t('system:power.relativeTime.secondsAgo', { count: diffSeconds });
  if (diffMinutes < 60) return t('system:power.relativeTime.minutesAgo', { count: diffMinutes });
  if (diffHours < 24) return t('system:power.relativeTime.hoursAgo', { count: diffHours });
  return formatTimestamp(ts);
};

// Profile color classes
const getPropertyColorClasses = (property: ServicePowerProperty): string => {
  const colors: Record<ServicePowerProperty, string> = {
    idle: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200',
    low: 'border-blue-500/30 bg-blue-500/10 text-blue-200',
    medium: 'border-yellow-500/30 bg-yellow-500/10 text-yellow-200',
    surge: 'border-red-500/30 bg-red-500/10 text-red-200',
  };
  return colors[property] || 'border-slate-600/50 bg-slate-800/60 text-slate-300';
};

// Preset color classes
const getPresetColorClasses = (presetName: string, isActive: boolean): string => {
  if (!isActive) return 'border-slate-700/50 bg-slate-800/50 hover:border-slate-600 hover:bg-slate-800';

  if (presetName.includes('Energy') || presetName.includes('Saver')) {
    return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200 ring-2 ring-emerald-500/50 ring-offset-2 ring-offset-slate-900';
  }
  if (presetName.includes('Performance')) {
    return 'border-red-500/30 bg-red-500/10 text-red-200 ring-2 ring-red-500/50 ring-offset-2 ring-offset-slate-900';
  }
  return 'border-blue-500/30 bg-blue-500/10 text-blue-200 ring-2 ring-blue-500/50 ring-offset-2 ring-offset-slate-900';
};

// Get preset icon
const getPresetIcon = (presetName: string): string => {
  if (presetName.includes('Energy') || presetName.includes('Saver')) return '🌱';
  if (presetName.includes('Performance')) return '🚀';
  if (presetName.includes('Balanced')) return '⚖️';
  return '⚙️';
};

// Property badge component
function PropertyBadge({ property, size = 'md' }: { property: ServicePowerProperty; size?: 'sm' | 'md' | 'lg' }) {
  const info = PROPERTY_INFO[property];
  const sizeClasses = {
    sm: 'px-2 py-0.5 text-xs',
    md: 'px-3 py-1 text-sm',
    lg: 'px-4 py-2 text-base',
  };

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border font-medium ${getPropertyColorClasses(property)} ${sizeClasses[size]}`}
    >
      <span>{info.icon}</span>
      <span>{info.name}</span>
    </span>
  );
}

// Stat card component
interface StatCardProps {
  label: string;
  value: string | number;
  subValue?: string;
  icon: React.ReactNode;
  color?: string;
}

function StatCard({ label, value, subValue, icon, color = 'slate' }: StatCardProps) {
  return (
    <div
      className={`card border-${color}-500/20 bg-gradient-to-br from-${color}-500/10 to-transparent p-3 sm:p-5`}
    >
      <div className="flex items-center justify-between">
        <div className="min-w-0 flex-1">
          <p className="text-[10px] sm:text-xs font-medium uppercase tracking-wider text-slate-400 truncate">{label}</p>
          <p className="mt-1 sm:mt-2 text-lg sm:text-2xl font-semibold text-white truncate">{value}</p>
          {subValue && <p className="mt-0.5 sm:mt-1 text-xs sm:text-sm text-slate-400 truncate">{subValue}</p>}
        </div>
        <div className={`rounded-full bg-${color}-500/20 p-2 sm:p-3 flex-shrink-0 ml-2`}>{icon}</div>
      </div>
    </div>
  );
}

// Preset selector component
interface PresetSelectorProps {
  presets: PowerPreset[];
  activePresetId?: number;
  onSelect: (presetId: number) => void;
  disabled?: boolean;
  t: (key: string, options?: Record<string, unknown>) => string;
}

function PresetSelector({ presets, activePresetId, onSelect, disabled, t }: PresetSelectorProps) {
  // Order: system presets first (Energy Saver, Balanced, Performance), then custom
  const systemPresets = presets.filter(p => p.is_system_preset);
  const customPresets = presets.filter(p => !p.is_system_preset);
  const orderedPresets = [...systemPresets, ...customPresets];

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      {orderedPresets.map((preset) => {
        const isActive = preset.id === activePresetId;
        const icon = getPresetIcon(preset.name);

        return (
          <button
            key={preset.id}
            onClick={() => onSelect(preset.id)}
            disabled={disabled || isActive}
            className={`flex flex-col items-center rounded-lg border p-4 transition-all touch-manipulation active:scale-95 min-h-[140px] ${
              getPresetColorClasses(preset.name, isActive)
            } ${disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}`}
          >
            <span className="text-3xl">{icon}</span>
            <span className="mt-2 text-base font-medium text-white">{preset.name}</span>
            {preset.description && (
              <span className="mt-1 text-xs text-slate-400 text-center line-clamp-2">{preset.description}</span>
            )}
            {!preset.is_system_preset && (
              <span className="mt-1 px-2 py-0.5 text-[10px] bg-slate-700/50 rounded-full text-slate-400">{t('system:power.custom')}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}

// Preset clock visualization
interface PresetClockVisualizationProps {
  preset: PowerPreset;
  currentProperty?: ServicePowerProperty;
  t: (key: string, options?: Record<string, unknown>) => string;
}

function PresetClockVisualization({ preset, currentProperty, t }: PresetClockVisualizationProps) {
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

// Service Intensity List component
interface ServiceIntensityListProps {
  services: ServiceIntensityInfo[];
  t: (key: string, options?: Record<string, unknown>) => string;
}

function ServiceIntensityList({ services, t }: ServiceIntensityListProps) {
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

// Demand list component
interface DemandListProps {
  demands: PowerDemandInfo[];
  onUnregister: (source: string) => void;
  isAdmin: boolean;
  t: (key: string, options?: Record<string, unknown>) => string;
}

function DemandList({ demands, onUnregister, isAdmin, t }: DemandListProps) {
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

// History table component
interface HistoryTableProps {
  entries: PowerHistoryEntry[];
  t: (key: string, options?: Record<string, unknown>) => string;
}

function HistoryTable({ entries, t }: HistoryTableProps) {
  if (entries.length === 0) {
    return (
      <div className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-4 sm:p-6 text-center text-sm text-slate-400">
        {t('system:power.noHistory')}
      </div>
    );
  }

  return (
    <>
      {/* Desktop Table */}
      <div className="hidden lg:block overflow-hidden rounded-lg border border-slate-700/50">
        <table className="min-w-full divide-y divide-slate-700/50">
          <thead className="bg-slate-800/50">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-400">
                {t('system:power.tableHeaders.timestamp')}
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-400">
                {t('system:power.tableHeaders.property')}
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-400">
                {t('system:power.tableHeaders.reason')}
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-400">
                {t('system:power.tableHeaders.frequency')}
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-700/30 bg-slate-900/30">
            {entries.map((entry, idx) => (
              <tr key={`${entry.timestamp}-${idx}`} className="hover:bg-slate-800/30">
                <td className="whitespace-nowrap px-4 py-3 text-sm text-slate-300">
                  {formatTimestamp(entry.timestamp)}
                </td>
                <td className="whitespace-nowrap px-4 py-3">
                  <PropertyBadge property={entry.profile as ServicePowerProperty} size="sm" />
                </td>
                <td className="px-4 py-3 text-sm text-slate-300">
                  <span className="font-mono text-xs">{entry.reason}</span>
                  {entry.source && (
                    <span className="ml-2 text-slate-500">({entry.source})</span>
                  )}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-sm text-slate-400">
                  {entry.frequency_mhz ? formatClockSpeed(entry.frequency_mhz) : '-'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile Card View */}
      <div className="lg:hidden space-y-2">
        {entries.map((entry, idx) => (
          <div
            key={`${entry.timestamp}-${idx}`}
            className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-3"
          >
            <div className="flex items-center justify-between gap-2 mb-2">
              <PropertyBadge property={entry.profile as ServicePowerProperty} size="sm" />
              <span className="text-xs text-slate-400">{formatTimestamp(entry.timestamp)}</span>
            </div>
            <div className="space-y-1">
              <p className="text-xs text-slate-300 font-mono truncate">{entry.reason}</p>
              <div className="flex items-center justify-between text-xs">
                {entry.source && <span className="text-slate-500">({entry.source})</span>}
                <span className="text-slate-400 font-medium">
                  {entry.frequency_mhz ? formatClockSpeed(entry.frequency_mhz) : '-'}
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

// Custom preset editor modal
interface PresetEditorProps {
  preset?: PowerPreset;
  onSave: (data: CreatePresetRequest) => void;
  onClose: () => void;
  onDelete?: () => void;
  t: (key: string, options?: Record<string, unknown>) => string;
}

function PresetEditor({ preset, onSave, onClose, onDelete, t }: PresetEditorProps) {
  const [name, setName] = useState(preset?.name || '');
  const [description, setDescription] = useState(preset?.description || '');
  const [idleClock, setIdleClock] = useState(preset?.idle_clock_mhz || 800);
  const [lowClock, setLowClock] = useState(preset?.low_clock_mhz || 1200);
  const [mediumClock, setMediumClock] = useState(preset?.medium_clock_mhz || 2500);
  const [surgeClock, setSurgeClock] = useState(preset?.surge_clock_mhz || 4200);

  const handleSave = () => {
    onSave({
      name,
      description: description || undefined,
      idle_clock_mhz: idleClock,
      low_clock_mhz: lowClock,
      medium_clock_mhz: mediumClock,
      surge_clock_mhz: surgeClock,
      base_clock_mhz: Math.round((idleClock + lowClock + mediumClock + surgeClock) / 4),
    });
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-lg w-full max-w-md max-h-[90vh] overflow-y-auto">
        <div className="p-4 border-b border-slate-700 flex items-center justify-between">
          <h3 className="text-lg font-medium text-white">
            {preset ? t('system:power.presetEditor.editPreset') : t('system:power.presetEditor.createPreset')}
          </h3>
          <button onClick={onClose} className="text-slate-400 hover:text-white">
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="p-4 space-y-4">
          {/* Name */}
          <div>
            <label className="block text-sm font-medium text-slate-400 mb-1">{t('system:power.presetEditor.name')}</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={preset?.is_system_preset}
              className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
              placeholder={t('system:power.presetEditor.namePlaceholder')}
            />
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-slate-400 mb-1">{t('system:power.presetEditor.description')}</label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={preset?.is_system_preset}
              className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
              placeholder={t('system:power.presetEditor.descriptionPlaceholder')}
            />
          </div>

          {/* Clock sliders */}
          <div className="space-y-4">
            <div>
              <div className="flex justify-between mb-1">
                <label className="text-sm font-medium text-emerald-400">IDLE</label>
                <span className="text-sm text-slate-400">{formatClockSpeed(idleClock)}</span>
              </div>
              <input
                type="range"
                min="400"
                max="2000"
                step="100"
                value={idleClock}
                onChange={(e) => setIdleClock(Number(e.target.value))}
                className="w-full accent-emerald-500"
              />
            </div>

            <div>
              <div className="flex justify-between mb-1">
                <label className="text-sm font-medium text-blue-400">LOW</label>
                <span className="text-sm text-slate-400">{formatClockSpeed(lowClock)}</span>
              </div>
              <input
                type="range"
                min="600"
                max="3000"
                step="100"
                value={lowClock}
                onChange={(e) => setLowClock(Number(e.target.value))}
                className="w-full accent-blue-500"
              />
            </div>

            <div>
              <div className="flex justify-between mb-1">
                <label className="text-sm font-medium text-yellow-400">MEDIUM</label>
                <span className="text-sm text-slate-400">{formatClockSpeed(mediumClock)}</span>
              </div>
              <input
                type="range"
                min="1000"
                max="4500"
                step="100"
                value={mediumClock}
                onChange={(e) => setMediumClock(Number(e.target.value))}
                className="w-full accent-yellow-500"
              />
            </div>

            <div>
              <div className="flex justify-between mb-1">
                <label className="text-sm font-medium text-red-400">SURGE</label>
                <span className="text-sm text-slate-400">{formatClockSpeed(surgeClock)}</span>
              </div>
              <input
                type="range"
                min="2000"
                max="5500"
                step="100"
                value={surgeClock}
                onChange={(e) => setSurgeClock(Number(e.target.value))}
                className="w-full accent-red-500"
              />
            </div>
          </div>
        </div>

        <div className="p-4 border-t border-slate-700 flex gap-2">
          {onDelete && !preset?.is_system_preset && (
            <button
              onClick={onDelete}
              className="px-4 py-2 bg-red-500/20 text-red-300 rounded-lg hover:bg-red-500/30"
            >
              {t('system:power.presetEditor.delete')}
            </button>
          )}
          <div className="flex-1" />
          <button
            onClick={onClose}
            className="px-4 py-2 bg-slate-700 text-white rounded-lg hover:bg-slate-600"
          >
            {t('system:power.presetEditor.cancel')}
          </button>
          <button
            onClick={handleSave}
            disabled={!name.trim()}
            className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:opacity-50"
          >
            {t('system:power.presetEditor.save')}
          </button>
        </div>
      </div>
    </div>
  );
}

// Main component
export default function PowerManagement() {
  const { t } = useTranslation(['system', 'common']);
  const [status, setStatus] = useState<PowerStatusResponse | null>(null);
  const [presets, setPresets] = useState<PowerPreset[]>([]);
  const [demands, setDemands] = useState<PowerDemandInfo[]>([]);
  const [intensities, setIntensities] = useState<ServiceIntensityInfo[]>([]);
  const [history, setHistory] = useState<PowerHistoryEntry[]>([]);
  const [autoScaling, setAutoScaling] = useState<AutoScalingConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [editorPreset, setEditorPreset] = useState<PowerPreset | null | 'new'>(null);

  // TODO: Get actual admin status from auth context
  const isAdmin = true;

  const loadData = useCallback(async (showSuccess = false) => {
    try {
      const [statusRes, presetsRes, demandsRes, intensitiesRes, historyRes, autoScalingRes] = await Promise.all([
        getPowerStatus(),
        listPresets(),
        getPowerDemands(),
        getServiceIntensities(),
        getPowerMgmtHistory(50),
        getAutoScalingConfig(),
      ]);

      setStatus(statusRes);
      setPresets(presetsRes.presets);
      setDemands(demandsRes);
      setIntensities(intensitiesRes.services);
      setHistory(historyRes.entries);
      setAutoScaling(autoScalingRes.config);
      setError(null);
      setLastUpdated(new Date());

      if (showSuccess) {
        toast.success(t('system:power.toasts.statusUpdated'));
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : t('system:power.toasts.loadFailed');
      setError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void loadData();
    const interval = setInterval(() => void loadData(), REFRESH_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [loadData]);

  const handlePresetSelect = async (presetId: number) => {
    if (busy) return;

    setBusy(true);
    try {
      const result = await activatePreset(presetId);
      toast.success(result.message);
      await loadData();
    } catch (err) {
      const message = err instanceof Error ? err.message : t('system:power.toasts.presetActivateFailed');
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  const handleUnregisterDemand = async (source: string) => {
    if (busy) return;

    setBusy(true);
    try {
      await unregisterPowerDemand({ source });
      toast.success(t('system:power.toasts.demandRemoved'));
      await loadData();
    } catch (err) {
      const message = err instanceof Error ? err.message : t('system:power.toasts.demandRemoveFailed');
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  const handleToggleAutoScaling = async () => {
    if (!autoScaling || busy) return;

    setBusy(true);
    try {
      const newConfig = { ...autoScaling, enabled: !autoScaling.enabled };
      await updateAutoScalingConfig(newConfig);
      setAutoScaling(newConfig);
      toast.success(newConfig.enabled ? t('system:power.toasts.autoScalingEnabled') : t('system:power.toasts.autoScalingDisabled'));
    } catch (err) {
      const message = err instanceof Error ? err.message : t('system:power.toasts.settingChangeFailed');
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  const handleSwitchBackend = async () => {
    if (!status || busy) return;

    const useLinux = !status.is_using_linux_backend;

    setBusy(true);
    try {
      const result = await switchPowerBackend(useLinux);
      toast.success(result.message);
      await loadData();
    } catch (err) {
      const message = err instanceof Error ? err.message : t('system:power.toasts.backendSwitchFailed');
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  const handleSavePreset = async (data: CreatePresetRequest) => {
    setBusy(true);
    try {
      if (editorPreset === 'new') {
        await createPreset(data);
        toast.success(t('system:power.toasts.presetCreated'));
      } else if (editorPreset) {
        await updatePreset(editorPreset.id, data);
        toast.success(t('system:power.toasts.presetUpdated'));
      }
      setEditorPreset(null);
      await loadData();
    } catch (err) {
      const message = err instanceof Error ? err.message : t('system:power.toasts.saveFailed');
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  const handleDeletePreset = async () => {
    if (!editorPreset || editorPreset === 'new') return;

    setBusy(true);
    try {
      await deletePreset(editorPreset.id);
      toast.success(t('system:power.toasts.presetDeleted'));
      setEditorPreset(null);
      await loadData();
    } catch (err) {
      const message = err instanceof Error ? err.message : t('system:power.toasts.deleteFailed');
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-[400px] items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-500 border-t-transparent" />
      </div>
    );
  }

  if (error && !status) {
    return (
      <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-6 text-center text-red-200">
        <p className="font-medium">{t('system:power.errors.loadingTitle')}</p>
        <p className="mt-1 text-sm">{error}</p>
        <button
          onClick={() => loadData(true)}
          className="mt-4 rounded bg-red-500/20 px-4 py-2 hover:bg-red-500/30"
        >
          {t('system:power.errors.retryButton')}
        </button>
      </div>
    );
  }

  const activePreset = presets.find(p => p.is_active);
  const currentProperty = status?.current_property || status?.current_profile as ServicePowerProperty;

  return (
    <div className="space-y-4 sm:space-y-6 p-4 sm:p-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-semibold text-white">{t('system:power.title')}</h1>
          <p className="mt-1 text-xs sm:text-sm text-slate-400">{t('system:power.subtitle')}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2 sm:gap-3">
          {/* Backend indicator - only show in dev mode */}
          {status?.is_dev_mode && (
            status?.is_using_linux_backend ? (
              <span className="rounded-full bg-emerald-500/20 px-2 sm:px-3 py-1 text-xs sm:text-sm text-emerald-300">
                <span className="hidden sm:inline">{t('system:power.backend.linux')}</span>
                <span className="sm:hidden">{t('system:power.backend.linuxShort')}</span>
              </span>
            ) : (
              <span className="rounded-full bg-amber-500/20 px-2 sm:px-3 py-1 text-xs sm:text-sm text-amber-300">
                <span className="hidden sm:inline">{t('system:power.backend.dev')}</span>
                <span className="sm:hidden">{t('system:power.backend.devShort')}</span>
              </span>
            )
          )}
          {/* Backend switch button - only show in dev mode if can switch */}
          {status?.is_dev_mode && isAdmin && status?.can_switch_backend && (
            <button
              onClick={handleSwitchBackend}
              disabled={busy}
              className={`flex items-center gap-1.5 rounded-lg px-2.5 sm:px-3 py-1.5 text-xs sm:text-sm transition-colors touch-manipulation active:scale-95 min-h-[36px] ${
                status.is_using_linux_backend
                  ? 'bg-amber-500/20 text-amber-300 hover:bg-amber-500/30'
                  : 'bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30'
              }`}
              title={status.is_using_linux_backend ? t('system:power.backend.switchToDev') : t('system:power.backend.switchToLinux')}
            >
              {status.is_using_linux_backend ? '-> Dev' : '-> Linux'}
              <AdminBadge />
            </button>
          )}
          <button
            onClick={() => loadData(true)}
            disabled={busy}
            className="rounded-lg border border-slate-700 bg-slate-800 px-3 sm:px-4 py-2 text-xs sm:text-sm text-white hover:bg-slate-700 touch-manipulation active:scale-95 min-h-[36px]"
          >
            <span className="hidden sm:inline">{t('system:power.buttons.refresh')}</span>
            <span className="sm:hidden">&#x21bb;</span>
          </button>
        </div>
      </div>

      {/* Status Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label={t('system:power.statusCards.activePreset')}
          value={activePreset?.name || '-'}
          subValue={activePreset?.description}
          color={activePreset?.name.includes('Performance') ? 'red' : activePreset?.name.includes('Energy') ? 'emerald' : 'blue'}
          icon={<span className="text-2xl">{activePreset ? getPresetIcon(activePreset.name) : '⚡'}</span>}
        />
        <StatCard
          label={t('system:power.statusCards.currentProperty')}
          value={currentProperty ? PROPERTY_INFO[currentProperty].name : '-'}
          subValue={status?.target_frequency_range}
          color={PROFILE_INFO[currentProperty || 'idle']?.color || 'slate'}
          icon={<span className="text-2xl">{currentProperty ? PROPERTY_INFO[currentProperty].icon : '⚡'}</span>}
        />
        <StatCard
          label={t('system:power.statusCards.cpuFrequency')}
          value={status?.current_frequency_mhz ? formatClockSpeed(status.current_frequency_mhz) : '-'}
          subValue={lastUpdated ? `${t('system:power.statusCards.updated')}: ${lastUpdated.toLocaleTimeString()}` : undefined}
          color="blue"
          icon={
            <svg className="h-6 w-6 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          }
        />
        <StatCard
          label={t('system:power.statusCards.activeDemands')}
          value={demands.length}
          subValue={demands.length > 0 ? `${t('system:power.statusCards.highest')}: ${PROPERTY_INFO[(demands.reduce((a, b) =>
            ['surge', 'medium', 'low', 'idle'].indexOf((a.power_property || a.level) as string) <
            ['surge', 'medium', 'low', 'idle'].indexOf((b.power_property || b.level) as string) ? a : b
          ).power_property || demands[0].level) as ServicePowerProperty].name}` : t('system:power.statusCards.none')}
          color="purple"
          icon={
            <svg className="h-6 w-6 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
          }
        />
      </div>

      {/* Preset Selection */}
      <div className="card border-slate-700/50 p-4 sm:p-6">
        <div className="mb-3 sm:mb-4 flex flex-col sm:flex-row sm:items-center justify-between gap-2 sm:gap-4">
          <h2 className="text-base sm:text-lg font-medium text-white">{t('system:power.presetSection.selectPreset')}</h2>
          {isAdmin && (
            <div className="flex gap-2">
              <button
                onClick={() => setEditorPreset('new')}
                disabled={busy}
                className="rounded-lg px-3 py-2 text-xs sm:text-sm bg-slate-700 text-slate-300 hover:bg-slate-600 flex items-center gap-1"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                </svg>
                {t('system:power.buttons.customPreset')}
              </button>
              <button
                onClick={handleToggleAutoScaling}
                disabled={busy}
                className={`rounded-lg px-3 sm:px-4 py-2 text-xs sm:text-sm transition-colors touch-manipulation active:scale-95 min-h-[40px] ${
                  autoScaling?.enabled
                    ? 'bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30'
                    : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                }`}
              >
                {autoScaling?.enabled ? t('system:power.presetSection.autoScalingActive') : t('system:power.presetSection.autoScalingOff')}
              </button>
            </div>
          )}
        </div>
        <PresetSelector
          presets={presets}
          activePresetId={activePreset?.id}
          onSelect={handlePresetSelect}
          disabled={busy || !isAdmin}
          t={t}
        />
        {!isAdmin && (
          <p className="mt-3 text-sm text-slate-500">
            {t('system:power.presetSection.adminOnlyChange')}
          </p>
        )}
      </div>

      {/* Preset Details */}
      {activePreset && (
        <div className="card border-slate-700/50 p-4 sm:p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-base sm:text-lg font-medium text-white">
              {t('system:power.presetSection.preset')}: {activePreset.name}
            </h2>
            {isAdmin && (
              <button
                onClick={() => setEditorPreset(activePreset)}
                className="text-xs text-slate-400 hover:text-white flex items-center gap-1"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                </svg>
                {t('system:power.buttons.edit')}
              </button>
            )}
          </div>
          <PresetClockVisualization preset={activePreset} currentProperty={currentProperty} t={t} />
        </div>
      )}

      {/* Service Intensity */}
      <div className="card border-slate-700/50 p-4 sm:p-6">
        <div className="mb-3 sm:mb-4 flex items-center justify-between">
          <h2 className="text-base sm:text-lg font-medium text-white">{t('system:power.serviceIntensity.title')}</h2>
          <span className="text-xs text-slate-400">
            {t('system:power.serviceIntensity.services', { count: intensities.length })}
          </span>
        </div>
        <ServiceIntensityList services={intensities} t={t} />
      </div>

      {/* Active Demands */}
      <div className="card border-slate-700/50 p-4 sm:p-6">
        <h2 className="mb-3 sm:mb-4 text-base sm:text-lg font-medium text-white">{t('system:power.demands.title')}</h2>
        <DemandList demands={demands} onUnregister={handleUnregisterDemand} isAdmin={isAdmin} t={t} />
      </div>

      {/* History */}
      <div className="card border-slate-700/50 p-4 sm:p-6">
        <h2 className="mb-3 sm:mb-4 text-base sm:text-lg font-medium text-white">{t('system:power.history.title')}</h2>
        <HistoryTable entries={history} t={t} />
      </div>

      {/* Auto-Scaling Config (Admin only) */}
      {isAdmin && autoScaling && (
        <div className="card border-slate-700/50 p-4 sm:p-6">
          <h2 className="mb-3 sm:mb-4 text-base sm:text-lg font-medium text-white flex items-center gap-2">
            {t('system:power.autoScaling.title')}
            <AdminBadge />
          </h2>
          <div className="grid grid-cols-3 gap-2 sm:gap-4">
            <div className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-2 sm:p-4">
              <p className="text-[10px] sm:text-sm text-slate-400">{t('system:power.autoScaling.surge')}</p>
              <p className="text-sm sm:text-xl font-semibold text-red-300">&gt;{autoScaling.cpu_surge_threshold}%</p>
            </div>
            <div className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-2 sm:p-4">
              <p className="text-[10px] sm:text-sm text-slate-400">{t('system:power.autoScaling.medium')}</p>
              <p className="text-sm sm:text-xl font-semibold text-yellow-300">&gt;{autoScaling.cpu_medium_threshold}%</p>
            </div>
            <div className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-2 sm:p-4">
              <p className="text-[10px] sm:text-sm text-slate-400">{t('system:power.autoScaling.low')}</p>
              <p className="text-sm sm:text-xl font-semibold text-blue-300">&gt;{autoScaling.cpu_low_threshold}%</p>
            </div>
          </div>
          <p className="mt-2 sm:mt-3 text-xs sm:text-sm text-slate-500">
            {t('system:power.autoScaling.cooldown')}: {autoScaling.cooldown_seconds}s &bull; {t('system:power.autoScaling.cpuMonitor')}:{' '}
            {autoScaling.use_cpu_monitoring ? t('system:power.autoScaling.active') : t('system:power.autoScaling.inactive')}
          </p>
        </div>
      )}

      {/* Permission Warning Banner */}
      {status?.is_using_linux_backend && status.permission_status && !status.permission_status.has_write_access && (
        <div className="mb-4 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-4">
          <div className="flex items-start gap-3">
            <AlertTriangle className="h-5 w-5 text-amber-400 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <h3 className="font-semibold text-amber-200">
                {t('system:power.permissions.warningTitle')}
              </h3>
              <p className="text-sm text-amber-300 mt-1">
                {t('system:power.permissions.warningMessage')}
              </p>
              <div className="mt-3 text-sm text-amber-300/80">
                <p className="font-medium mb-1">{t('system:power.permissions.suggestions')}</p>
                <ul className="list-disc list-inside space-y-1 font-mono text-xs">
                  <li>sudo systemctl start baluhost-backend</li>
                  <li>sudo usermod -aG cpufreq $USER</li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Permission Status (Linux backend only) */}
      {status?.is_using_linux_backend && status.permission_status && (
        <div className="card border-slate-700/50 p-4 sm:p-6">
          <h2 className="mb-3 sm:mb-4 text-base sm:text-lg font-medium text-white">{t('system:power.permissions.title')}</h2>
          <div className="grid grid-cols-2 gap-2 sm:gap-4 lg:grid-cols-4">
            {/* Write Access Status */}
            <div className={`rounded-lg border p-2 sm:p-4 ${
              status.permission_status.has_write_access
                ? 'border-emerald-500/30 bg-emerald-500/10'
                : 'border-red-500/30 bg-red-500/10'
            }`}>
              <p className="text-[10px] sm:text-sm text-slate-400">{t('system:power.permissions.writeAccess')}</p>
              <p className={`text-sm sm:text-xl font-semibold ${
                status.permission_status.has_write_access ? 'text-emerald-300' : 'text-red-300'
              }`}>
                {status.permission_status.has_write_access ? t('system:power.permissions.ok') : t('system:power.permissions.no')}
              </p>
            </div>

            {/* User Info */}
            <div className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-2 sm:p-4">
              <p className="text-[10px] sm:text-sm text-slate-400">{t('system:power.permissions.user')}</p>
              <p className="text-sm sm:text-xl font-semibold text-white truncate">{status.permission_status.user}</p>
            </div>

            {/* cpufreq Group Status */}
            <div className={`rounded-lg border p-2 sm:p-4 ${
              status.permission_status.in_cpufreq_group
                ? 'border-emerald-500/30 bg-emerald-500/10'
                : 'border-amber-500/30 bg-amber-500/10'
            }`}>
              <p className="text-[10px] sm:text-sm text-slate-400">{t('system:power.permissions.cpufreq')}</p>
              <p className={`text-sm sm:text-xl font-semibold ${
                status.permission_status.in_cpufreq_group ? 'text-emerald-300' : 'text-amber-300'
              }`}>
                {status.permission_status.in_cpufreq_group ? t('system:power.permissions.ok') : t('system:power.permissions.no')}
              </p>
            </div>

            {/* Sudo Status */}
            <div className={`rounded-lg border p-2 sm:p-4 ${
              status.permission_status.sudo_available
                ? 'border-emerald-500/30 bg-emerald-500/10'
                : 'border-slate-700/50 bg-slate-800/30'
            }`}>
              <p className="text-[10px] sm:text-sm text-slate-400">{t('system:power.permissions.sudo')}</p>
              <p className={`text-sm sm:text-xl font-semibold ${
                status.permission_status.sudo_available ? 'text-emerald-300' : 'text-slate-400'
              }`}>
                {status.permission_status.sudo_available ? t('system:power.permissions.ok') : t('system:power.permissions.no')}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Preset Editor Modal */}
      {editorPreset && (
        <PresetEditor
          preset={editorPreset === 'new' ? undefined : editorPreset}
          onSave={handleSavePreset}
          onClose={() => setEditorPreset(null)}
          onDelete={editorPreset !== 'new' && !editorPreset.is_system_preset ? handleDeletePreset : undefined}
          t={t}
        />
      )}
    </div>
  );
}
