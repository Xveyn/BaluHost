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
import toast from 'react-hot-toast';
import {
  getPowerStatus,
  getPowerDemands,
  unregisterPowerDemand,
  getPowerMgmtHistory,
  getAutoScalingConfig,
  updateAutoScalingConfig,
  switchPowerBackend,
  PROFILE_INFO,
  type PowerStatusResponse,
  type PowerDemandInfo,
  type PowerHistoryEntry,
  type AutoScalingConfig,
  type ServicePowerProperty,
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
const formatRelativeTime = (ts: string): string => {
  const now = new Date();
  const then = new Date(ts);
  const diffMs = now.getTime() - then.getTime();
  const diffSeconds = Math.floor(diffMs / 1000);
  const diffMinutes = Math.floor(diffSeconds / 60);
  const diffHours = Math.floor(diffMinutes / 60);

  if (diffSeconds < 60) return `vor ${diffSeconds}s`;
  if (diffMinutes < 60) return `vor ${diffMinutes}min`;
  if (diffHours < 24) return `vor ${diffHours}h`;
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
}

function PresetSelector({ presets, activePresetId, onSelect, disabled }: PresetSelectorProps) {
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
              <span className="mt-1 px-2 py-0.5 text-[10px] bg-slate-700/50 rounded-full text-slate-400">Custom</span>
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
}

function PresetClockVisualization({ preset, currentProperty }: PresetClockVisualizationProps) {
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
                  <span className="px-1.5 py-0.5 text-[10px] bg-emerald-500/20 text-emerald-300 rounded">AKTIV</span>
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

// Demand list component
interface DemandListProps {
  demands: PowerDemandInfo[];
  onUnregister: (source: string) => void;
  isAdmin: boolean;
}

function DemandList({ demands, onUnregister, isAdmin }: DemandListProps) {
  if (demands.length === 0) {
    return (
      <div className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-4 sm:p-6 text-center text-sm sm:text-base text-slate-400">
        Keine aktiven Power-Anforderungen
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
                  Registriert: {formatRelativeTime(demand.registered_at)}
                  {demand.expires_at && <span className="hidden sm:inline"> &bull; Lauft ab: {formatTimestamp(demand.expires_at)}</span>}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2 self-end sm:self-auto">
              <PropertyBadge property={property} size="sm" />
              {isAdmin && (
                <button
                  onClick={() => onUnregister(demand.source)}
                  className="rounded p-2 text-slate-400 hover:bg-slate-700 hover:text-white touch-manipulation active:scale-95 min-w-[36px] min-h-[36px] flex items-center justify-center"
                  title="Anforderung entfernen"
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
}

function HistoryTable({ entries }: HistoryTableProps) {
  if (entries.length === 0) {
    return (
      <div className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-4 sm:p-6 text-center text-sm text-slate-400">
        Keine Historie vorhanden
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
                Zeitpunkt
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-400">
                Property
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-400">
                Grund
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-400">
                Frequenz
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
}

function PresetEditor({ preset, onSave, onClose, onDelete }: PresetEditorProps) {
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
            {preset ? 'Preset bearbeiten' : 'Neues Preset erstellen'}
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
            <label className="block text-sm font-medium text-slate-400 mb-1">Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={preset?.is_system_preset}
              className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
              placeholder="Mein Preset"
            />
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-slate-400 mb-1">Beschreibung</label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={preset?.is_system_preset}
              className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
              placeholder="Beschreibung..."
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
              Loschen
            </button>
          )}
          <div className="flex-1" />
          <button
            onClick={onClose}
            className="px-4 py-2 bg-slate-700 text-white rounded-lg hover:bg-slate-600"
          >
            Abbrechen
          </button>
          <button
            onClick={handleSave}
            disabled={!name.trim()}
            className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:opacity-50"
          >
            Speichern
          </button>
        </div>
      </div>
    </div>
  );
}

// Main component
export default function PowerManagement() {
  const [status, setStatus] = useState<PowerStatusResponse | null>(null);
  const [presets, setPresets] = useState<PowerPreset[]>([]);
  const [demands, setDemands] = useState<PowerDemandInfo[]>([]);
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
      const [statusRes, presetsRes, demandsRes, historyRes, autoScalingRes] = await Promise.all([
        getPowerStatus(),
        listPresets(),
        getPowerDemands(),
        getPowerMgmtHistory(50),
        getAutoScalingConfig(),
      ]);

      setStatus(statusRes);
      setPresets(presetsRes.presets);
      setDemands(demandsRes);
      setHistory(historyRes.entries);
      setAutoScaling(autoScalingRes.config);
      setError(null);
      setLastUpdated(new Date());

      if (showSuccess) {
        toast.success('Status aktualisiert');
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Laden fehlgeschlagen';
      setError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, []);

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
      const message = err instanceof Error ? err.message : 'Preset konnte nicht aktiviert werden';
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
      toast.success('Anforderung entfernt');
      await loadData();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Anforderung konnte nicht entfernt werden';
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
      toast.success(newConfig.enabled ? 'Auto-Scaling aktiviert' : 'Auto-Scaling deaktiviert');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Einstellung konnte nicht geandert werden';
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
      const message = err instanceof Error ? err.message : 'Backend konnte nicht gewechselt werden';
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
        toast.success('Preset erstellt');
      } else if (editorPreset) {
        await updatePreset(editorPreset.id, data);
        toast.success('Preset aktualisiert');
      }
      setEditorPreset(null);
      await loadData();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Speichern fehlgeschlagen';
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
      toast.success('Preset geloscht');
      setEditorPreset(null);
      await loadData();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Loschen fehlgeschlagen';
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
        <p className="font-medium">Fehler beim Laden</p>
        <p className="mt-1 text-sm">{error}</p>
        <button
          onClick={() => loadData(true)}
          className="mt-4 rounded bg-red-500/20 px-4 py-2 hover:bg-red-500/30"
        >
          Erneut versuchen
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
          <h1 className="text-xl sm:text-2xl font-semibold text-white">Power Management</h1>
          <p className="mt-1 text-xs sm:text-sm text-slate-400">CPU-Frequenzskalierung und Energieverwaltung</p>
        </div>
        <div className="flex flex-wrap items-center gap-2 sm:gap-3">
          {/* Backend indicator - only show in dev mode */}
          {status?.is_dev_mode && (
            status?.is_using_linux_backend ? (
              <span className="rounded-full bg-emerald-500/20 px-2 sm:px-3 py-1 text-xs sm:text-sm text-emerald-300">
                <span className="hidden sm:inline">Linux Backend</span>
                <span className="sm:hidden">Linux</span>
              </span>
            ) : (
              <span className="rounded-full bg-amber-500/20 px-2 sm:px-3 py-1 text-xs sm:text-sm text-amber-300">
                <span className="hidden sm:inline">Dev Backend</span>
                <span className="sm:hidden">Dev</span>
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
              title={status.is_using_linux_backend ? 'Zu Dev-Backend wechseln' : 'Zu Linux-Backend wechseln'}
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
            <span className="hidden sm:inline">Aktualisieren</span>
            <span className="sm:hidden">&#x21bb;</span>
          </button>
        </div>
      </div>

      {/* Status Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Aktives Preset"
          value={activePreset?.name || '-'}
          subValue={activePreset?.description}
          color={activePreset?.name.includes('Performance') ? 'red' : activePreset?.name.includes('Energy') ? 'emerald' : 'blue'}
          icon={<span className="text-2xl">{activePreset ? getPresetIcon(activePreset.name) : '⚡'}</span>}
        />
        <StatCard
          label="Aktuelle Property"
          value={currentProperty ? PROPERTY_INFO[currentProperty].name : '-'}
          subValue={status?.target_frequency_range}
          color={PROFILE_INFO[currentProperty || 'idle']?.color || 'slate'}
          icon={<span className="text-2xl">{currentProperty ? PROPERTY_INFO[currentProperty].icon : '⚡'}</span>}
        />
        <StatCard
          label="CPU-Frequenz"
          value={status?.current_frequency_mhz ? formatClockSpeed(status.current_frequency_mhz) : '-'}
          subValue={lastUpdated ? `Aktualisiert: ${lastUpdated.toLocaleTimeString('de-DE')}` : undefined}
          color="blue"
          icon={
            <svg className="h-6 w-6 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          }
        />
        <StatCard
          label="Aktive Anforderungen"
          value={demands.length}
          subValue={demands.length > 0 ? `Hochste: ${PROPERTY_INFO[(demands.reduce((a, b) =>
            ['surge', 'medium', 'low', 'idle'].indexOf((a.power_property || a.level) as string) <
            ['surge', 'medium', 'low', 'idle'].indexOf((b.power_property || b.level) as string) ? a : b
          ).power_property || demands[0].level) as ServicePowerProperty].name}` : 'Keine'}
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
          <h2 className="text-base sm:text-lg font-medium text-white">Preset auswahlen</h2>
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
                Custom Preset
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
                {autoScaling?.enabled ? 'Auto-Scaling aktiv' : 'Auto-Scaling aus'}
              </button>
            </div>
          )}
        </div>
        <PresetSelector
          presets={presets}
          activePresetId={activePreset?.id}
          onSelect={handlePresetSelect}
          disabled={busy || !isAdmin}
        />
        {!isAdmin && (
          <p className="mt-3 text-sm text-slate-500">
            Nur Administratoren konnen das Preset andern.
          </p>
        )}
      </div>

      {/* Preset Details */}
      {activePreset && (
        <div className="card border-slate-700/50 p-4 sm:p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-base sm:text-lg font-medium text-white">
              Preset: {activePreset.name}
            </h2>
            {isAdmin && (
              <button
                onClick={() => setEditorPreset(activePreset)}
                className="text-xs text-slate-400 hover:text-white flex items-center gap-1"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                </svg>
                Bearbeiten
              </button>
            )}
          </div>
          <PresetClockVisualization preset={activePreset} currentProperty={currentProperty} />
        </div>
      )}

      {/* Active Demands */}
      <div className="card border-slate-700/50 p-4 sm:p-6">
        <h2 className="mb-3 sm:mb-4 text-base sm:text-lg font-medium text-white">Aktive Power-Anforderungen</h2>
        <DemandList demands={demands} onUnregister={handleUnregisterDemand} isAdmin={isAdmin} />
      </div>

      {/* History */}
      <div className="card border-slate-700/50 p-4 sm:p-6">
        <h2 className="mb-3 sm:mb-4 text-base sm:text-lg font-medium text-white">Property-Historie</h2>
        <HistoryTable entries={history} />
      </div>

      {/* Auto-Scaling Config (Admin only) */}
      {isAdmin && autoScaling && (
        <div className="card border-slate-700/50 p-4 sm:p-6">
          <h2 className="mb-3 sm:mb-4 text-base sm:text-lg font-medium text-white flex items-center gap-2">
            Auto-Scaling Konfiguration
            <AdminBadge />
          </h2>
          <div className="grid grid-cols-3 gap-2 sm:gap-4">
            <div className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-2 sm:p-4">
              <p className="text-[10px] sm:text-sm text-slate-400">SURGE</p>
              <p className="text-sm sm:text-xl font-semibold text-red-300">&gt;{autoScaling.cpu_surge_threshold}%</p>
            </div>
            <div className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-2 sm:p-4">
              <p className="text-[10px] sm:text-sm text-slate-400">MEDIUM</p>
              <p className="text-sm sm:text-xl font-semibold text-yellow-300">&gt;{autoScaling.cpu_medium_threshold}%</p>
            </div>
            <div className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-2 sm:p-4">
              <p className="text-[10px] sm:text-sm text-slate-400">LOW</p>
              <p className="text-sm sm:text-xl font-semibold text-blue-300">&gt;{autoScaling.cpu_low_threshold}%</p>
            </div>
          </div>
          <p className="mt-2 sm:mt-3 text-xs sm:text-sm text-slate-500">
            Cooldown: {autoScaling.cooldown_seconds}s &bull; CPU-Monitor:{' '}
            {autoScaling.use_cpu_monitoring ? 'Aktiv' : 'Inaktiv'}
          </p>
        </div>
      )}

      {/* Permission Status (Linux backend only) */}
      {status?.is_using_linux_backend && status.permission_status && (
        <div className="card border-slate-700/50 p-4 sm:p-6">
          <h2 className="mb-3 sm:mb-4 text-base sm:text-lg font-medium text-white">Berechtigungsstatus</h2>
          <div className="grid grid-cols-2 gap-2 sm:gap-4 lg:grid-cols-4">
            {/* Write Access Status */}
            <div className={`rounded-lg border p-2 sm:p-4 ${
              status.permission_status.has_write_access
                ? 'border-emerald-500/30 bg-emerald-500/10'
                : 'border-red-500/30 bg-red-500/10'
            }`}>
              <p className="text-[10px] sm:text-sm text-slate-400">Schreibzugriff</p>
              <p className={`text-sm sm:text-xl font-semibold ${
                status.permission_status.has_write_access ? 'text-emerald-300' : 'text-red-300'
              }`}>
                {status.permission_status.has_write_access ? 'OK' : 'Nein'}
              </p>
            </div>

            {/* User Info */}
            <div className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-2 sm:p-4">
              <p className="text-[10px] sm:text-sm text-slate-400">Benutzer</p>
              <p className="text-sm sm:text-xl font-semibold text-white truncate">{status.permission_status.user}</p>
            </div>

            {/* cpufreq Group Status */}
            <div className={`rounded-lg border p-2 sm:p-4 ${
              status.permission_status.in_cpufreq_group
                ? 'border-emerald-500/30 bg-emerald-500/10'
                : 'border-amber-500/30 bg-amber-500/10'
            }`}>
              <p className="text-[10px] sm:text-sm text-slate-400">cpufreq</p>
              <p className={`text-sm sm:text-xl font-semibold ${
                status.permission_status.in_cpufreq_group ? 'text-emerald-300' : 'text-amber-300'
              }`}>
                {status.permission_status.in_cpufreq_group ? 'OK' : 'Nein'}
              </p>
            </div>

            {/* Sudo Status */}
            <div className={`rounded-lg border p-2 sm:p-4 ${
              status.permission_status.sudo_available
                ? 'border-emerald-500/30 bg-emerald-500/10'
                : 'border-slate-700/50 bg-slate-800/30'
            }`}>
              <p className="text-[10px] sm:text-sm text-slate-400">Sudo</p>
              <p className={`text-sm sm:text-xl font-semibold ${
                status.permission_status.sudo_available ? 'text-emerald-300' : 'text-slate-400'
              }`}>
                {status.permission_status.sudo_available ? 'OK' : 'Nein'}
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
        />
      )}
    </div>
  );
}
