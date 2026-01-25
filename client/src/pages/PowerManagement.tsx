/**
 * Power Management Page
 *
 * Provides CPU frequency scaling controls with:
 * - Current power profile status
 * - Manual profile selection
 * - Active power demands list
 * - Profile change history
 * - Auto-scaling configuration
 */

import { useEffect, useState, useCallback } from 'react';
import toast from 'react-hot-toast';
import {
  getPowerStatus,
  getPowerProfiles,
  setPowerProfile,
  getPowerDemands,
  unregisterPowerDemand,
  getPowerMgmtHistory,
  getAutoScalingConfig,
  updateAutoScalingConfig,
  switchPowerBackend,
  PROFILE_INFO,
  type PowerStatusResponse,
  type PowerProfileConfig,
  type PowerDemandInfo,
  type PowerHistoryEntry,
  type PowerProfile,
  type AutoScalingConfig,
} from '../api/power-management';

const REFRESH_INTERVAL_MS = 5000;

// Format frequency for display
const formatFrequency = (mhz: number | undefined | null): string => {
  if (mhz === undefined || mhz === null) return '-';
  if (mhz >= 1000) return `${(mhz / 1000).toFixed(2)} GHz`;
  return `${Math.round(mhz)} MHz`;
};

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
const getProfileColorClasses = (profile: PowerProfile): string => {
  const colors: Record<PowerProfile, string> = {
    idle: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200',
    low: 'border-blue-500/30 bg-blue-500/10 text-blue-200',
    medium: 'border-yellow-500/30 bg-yellow-500/10 text-yellow-200',
    surge: 'border-red-500/30 bg-red-500/10 text-red-200',
  };
  return colors[profile] || 'border-slate-600/50 bg-slate-800/60 text-slate-300';
};

// Profile badge component
function ProfileBadge({ profile, size = 'md' }: { profile: PowerProfile; size?: 'sm' | 'md' | 'lg' }) {
  const info = PROFILE_INFO[profile];
  const sizeClasses = {
    sm: 'px-2 py-0.5 text-xs',
    md: 'px-3 py-1 text-sm',
    lg: 'px-4 py-2 text-base',
  };

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border font-medium ${getProfileColorClasses(profile)} ${sizeClasses[size]}`}
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

// Profile selector component
interface ProfileSelectorProps {
  profiles: PowerProfileConfig[];
  currentProfile: PowerProfile;
  onSelect: (profile: PowerProfile) => void;
  disabled?: boolean;
}

function ProfileSelector({ profiles, currentProfile, onSelect, disabled }: ProfileSelectorProps) {
  const profileOrder: PowerProfile[] = ['idle', 'low', 'medium', 'surge'];
  const sortedProfiles = profileOrder
    .map((p) => profiles.find((cfg) => cfg.profile === p))
    .filter(Boolean) as PowerProfileConfig[];

  return (
    <div className="grid grid-cols-2 gap-2 sm:gap-3 lg:grid-cols-4">
      {sortedProfiles.map((cfg) => {
        const info = PROFILE_INFO[cfg.profile];
        const isActive = cfg.profile === currentProfile;

        return (
          <button
            key={cfg.profile}
            onClick={() => onSelect(cfg.profile)}
            disabled={disabled || isActive}
            className={`flex flex-col items-center rounded-lg border p-3 sm:p-4 transition-all touch-manipulation active:scale-95 min-h-[100px] sm:min-h-[120px] ${
              isActive
                ? `${getProfileColorClasses(cfg.profile)} ring-2 ring-offset-2 ring-offset-slate-900`
                : 'border-slate-700/50 bg-slate-800/50 hover:border-slate-600 hover:bg-slate-800'
            } ${disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}`}
          >
            <span className="text-2xl sm:text-3xl">{info.icon}</span>
            <span className="mt-1 sm:mt-2 text-sm sm:text-base font-medium text-white">{info.name}</span>
            <span className="mt-0.5 sm:mt-1 text-[10px] sm:text-xs text-slate-400 text-center line-clamp-2">{cfg.description}</span>
            {cfg.min_freq_mhz && cfg.max_freq_mhz && (
              <span className="mt-0.5 sm:mt-1 text-[10px] sm:text-xs text-slate-500">
                {formatFrequency(cfg.min_freq_mhz)} - {formatFrequency(cfg.max_freq_mhz)}
              </span>
            )}
            {!cfg.min_freq_mhz && !cfg.max_freq_mhz && (
              <span className="mt-0.5 sm:mt-1 text-[10px] sm:text-xs text-slate-500">Full Boost</span>
            )}
          </button>
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
      {demands.map((demand) => (
        <div
          key={demand.source}
          className={`flex flex-col sm:flex-row sm:items-center justify-between rounded-lg border p-3 gap-2 sm:gap-3 ${getProfileColorClasses(demand.level)}`}
        >
          <div className="flex items-start sm:items-center gap-2 sm:gap-3 flex-1 min-w-0">
            <span className="text-lg sm:text-xl flex-shrink-0">{PROFILE_INFO[demand.level].icon}</span>
            <div className="min-w-0 flex-1">
              <p className="font-medium text-sm sm:text-base truncate">{demand.source}</p>
              {demand.description && <p className="text-xs sm:text-sm opacity-80 truncate">{demand.description}</p>}
              <p className="text-[10px] sm:text-xs opacity-60">
                Registriert: {formatRelativeTime(demand.registered_at)}
                {demand.expires_at && <span className="hidden sm:inline"> • Läuft ab: {formatTimestamp(demand.expires_at)}</span>}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 self-end sm:self-auto">
            <ProfileBadge profile={demand.level} size="sm" />
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
      ))}
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
                Profil
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
                  <ProfileBadge profile={entry.profile} size="sm" />
                </td>
                <td className="px-4 py-3 text-sm text-slate-300">
                  <span className="font-mono text-xs">{entry.reason}</span>
                  {entry.source && (
                    <span className="ml-2 text-slate-500">({entry.source})</span>
                  )}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-sm text-slate-400">
                  {formatFrequency(entry.frequency_mhz)}
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
              <ProfileBadge profile={entry.profile} size="sm" />
              <span className="text-xs text-slate-400">{formatTimestamp(entry.timestamp)}</span>
            </div>
            <div className="space-y-1">
              <p className="text-xs text-slate-300 font-mono truncate">{entry.reason}</p>
              <div className="flex items-center justify-between text-xs">
                {entry.source && <span className="text-slate-500">({entry.source})</span>}
                <span className="text-slate-400 font-medium">{formatFrequency(entry.frequency_mhz)}</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

// Main component
export default function PowerManagement() {
  const [status, setStatus] = useState<PowerStatusResponse | null>(null);
  const [profiles, setProfiles] = useState<PowerProfileConfig[]>([]);
  const [demands, setDemands] = useState<PowerDemandInfo[]>([]);
  const [history, setHistory] = useState<PowerHistoryEntry[]>([]);
  const [autoScaling, setAutoScaling] = useState<AutoScalingConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  // TODO: Get actual admin status from auth context
  const isAdmin = true;

  const loadData = useCallback(async (showSuccess = false) => {
    try {
      const [statusRes, profilesRes, demandsRes, historyRes, autoScalingRes] = await Promise.all([
        getPowerStatus(),
        getPowerProfiles(),
        getPowerDemands(),
        getPowerMgmtHistory(50),
        getAutoScalingConfig(),
      ]);

      setStatus(statusRes);
      setProfiles(profilesRes.profiles);
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

  const handleProfileSelect = async (profile: PowerProfile) => {
    if (busy) return;

    setBusy(true);
    try {
      await setPowerProfile({
        profile,
        reason: 'Manuelle Auswahl via UI',
      });
      toast.success(`Profil auf ${PROFILE_INFO[profile].name} gesetzt`);
      await loadData();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Profil konnte nicht gesetzt werden';
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
      const message = err instanceof Error ? err.message : 'Einstellung konnte nicht geändert werden';
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

  return (
    <div className="space-y-4 sm:space-y-6 p-4 sm:p-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-semibold text-white">Power Management</h1>
          <p className="mt-1 text-xs sm:text-sm text-slate-400">CPU-Frequenzskalierung und Energieverwaltung</p>
        </div>
        <div className="flex flex-wrap items-center gap-2 sm:gap-3">
          {/* Backend indicator and switch */}
          {status?.is_using_linux_backend ? (
            <span className="rounded-full bg-emerald-500/20 px-2 sm:px-3 py-1 text-xs sm:text-sm text-emerald-300">
              <span className="hidden sm:inline">Linux Backend (echte CPU-Steuerung)</span>
              <span className="sm:hidden">Linux</span>
            </span>
          ) : (
            <span className="rounded-full bg-amber-500/20 px-2 sm:px-3 py-1 text-xs sm:text-sm text-amber-300">
              <span className="hidden sm:inline">Dev Backend (simuliert)</span>
              <span className="sm:hidden">Dev</span>
            </span>
          )}
          {/* Backend switch button - only show if can switch */}
          {isAdmin && status?.can_switch_backend && (
            <button
              onClick={handleSwitchBackend}
              disabled={busy}
              className={`rounded-lg px-2.5 sm:px-3 py-1.5 text-xs sm:text-sm transition-colors touch-manipulation active:scale-95 min-h-[36px] ${
                status.is_using_linux_backend
                  ? 'bg-amber-500/20 text-amber-300 hover:bg-amber-500/30'
                  : 'bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30'
              }`}
              title={status.is_using_linux_backend ? 'Zu Dev-Backend wechseln' : 'Zu Linux-Backend wechseln'}
            >
              {status.is_using_linux_backend ? '→ Dev' : '→ Linux'}
            </button>
          )}
          <button
            onClick={() => loadData(true)}
            disabled={busy}
            className="rounded-lg border border-slate-700 bg-slate-800 px-3 sm:px-4 py-2 text-xs sm:text-sm text-white hover:bg-slate-700 touch-manipulation active:scale-95 min-h-[36px]"
          >
            <span className="hidden sm:inline">Aktualisieren</span>
            <span className="sm:hidden">↻</span>
          </button>
        </div>
      </div>

      {/* Status Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Aktuelles Profil"
          value={status ? PROFILE_INFO[status.current_profile].name : '-'}
          subValue={status?.target_frequency_range}
          color={status ? PROFILE_INFO[status.current_profile].color : 'slate'}
          icon={<span className="text-2xl">{status ? PROFILE_INFO[status.current_profile].icon : '⚡'}</span>}
        />
        <StatCard
          label="CPU-Frequenz"
          value={formatFrequency(status?.current_frequency_mhz)}
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
          subValue={demands.length > 0 ? `Höchste: ${PROFILE_INFO[demands.reduce((a, b) =>
            ['surge', 'medium', 'low', 'idle'].indexOf(a.level) <
            ['surge', 'medium', 'low', 'idle'].indexOf(b.level) ? a : b
          ).level].name}` : 'Keine'}
          color="purple"
          icon={
            <svg className="h-6 w-6 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
          }
        />
        <StatCard
          label="Auto-Scaling"
          value={autoScaling?.enabled ? 'Aktiv' : 'Deaktiviert'}
          subValue={
            status?.cooldown_remaining_seconds
              ? `Cooldown: ${status.cooldown_remaining_seconds}s`
              : undefined
          }
          color={autoScaling?.enabled ? 'emerald' : 'slate'}
          icon={
            <svg className="h-6 w-6 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          }
        />
      </div>

      {/* Profile Selection */}
      <div className="card border-slate-700/50 p-4 sm:p-6">
        <div className="mb-3 sm:mb-4 flex flex-col sm:flex-row sm:items-center justify-between gap-2 sm:gap-4">
          <h2 className="text-base sm:text-lg font-medium text-white">Profil auswählen</h2>
          {isAdmin && (
            <button
              onClick={handleToggleAutoScaling}
              disabled={busy}
              className={`rounded-lg px-3 sm:px-4 py-2 text-xs sm:text-sm transition-colors touch-manipulation active:scale-95 min-h-[40px] ${
                autoScaling?.enabled
                  ? 'bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30'
                  : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
              }`}
            >
              {autoScaling?.enabled ? 'Auto-Scaling deaktivieren' : 'Auto-Scaling aktivieren'}
            </button>
          )}
        </div>
        <ProfileSelector
          profiles={profiles}
          currentProfile={status?.current_profile || 'idle'}
          onSelect={handleProfileSelect}
          disabled={busy || !isAdmin}
        />
        {!isAdmin && (
          <p className="mt-3 text-sm text-slate-500">
            Nur Administratoren können das Profil manuell ändern.
          </p>
        )}
      </div>

      {/* Active Demands */}
      <div className="card border-slate-700/50 p-4 sm:p-6">
        <h2 className="mb-3 sm:mb-4 text-base sm:text-lg font-medium text-white">Aktive Power-Anforderungen</h2>
        <DemandList demands={demands} onUnregister={handleUnregisterDemand} isAdmin={isAdmin} />
      </div>

      {/* History */}
      <div className="card border-slate-700/50 p-4 sm:p-6">
        <h2 className="mb-3 sm:mb-4 text-base sm:text-lg font-medium text-white">Profil-Historie</h2>
        <HistoryTable entries={history} />
      </div>

      {/* Auto-Scaling Config (Admin only) */}
      {isAdmin && autoScaling && (
        <div className="card border-slate-700/50 p-4 sm:p-6">
          <h2 className="mb-3 sm:mb-4 text-base sm:text-lg font-medium text-white">Auto-Scaling Konfiguration</h2>
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
            Cooldown: {autoScaling.cooldown_seconds}s • CPU-Monitor:{' '}
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
              <p className="mt-0.5 sm:mt-1 text-[10px] sm:text-xs text-slate-500">
                {status.permission_status.sudo_available ? 'sudo' : 'direkt'}
              </p>
            </div>

            {/* User Info */}
            <div className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-2 sm:p-4">
              <p className="text-[10px] sm:text-sm text-slate-400">Benutzer</p>
              <p className="text-sm sm:text-xl font-semibold text-white truncate">{status.permission_status.user}</p>
              <p className="mt-0.5 sm:mt-1 text-[10px] sm:text-xs text-slate-500 truncate" title={status.permission_status.groups.join(', ')}>
                <span className="hidden sm:inline">Gruppen: </span>{status.permission_status.groups.slice(0, 2).join(', ')}
                {status.permission_status.groups.length > 2 && '...'}
              </p>
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

          {/* File Permissions */}
          <div className="mt-4">
            <p className="mb-2 text-sm font-medium text-slate-400">Datei-Berechtigungen</p>
            <div className="flex flex-wrap gap-2">
              {Object.entries(status.permission_status.files).map(([file, writable]) => (
                <span
                  key={file}
                  className={`rounded-full px-3 py-1 text-xs font-medium ${
                    writable === true
                      ? 'bg-emerald-500/20 text-emerald-300'
                      : writable === false
                      ? 'bg-red-500/20 text-red-300'
                      : 'bg-slate-700 text-slate-400'
                  }`}
                  title={writable === true ? 'Schreibbar' : writable === false ? 'Nicht schreibbar' : 'Nicht vorhanden'}
                >
                  {file}: {writable === true ? 'OK' : writable === false ? 'Denied' : 'N/A'}
                </span>
              ))}
            </div>
          </div>

          {/* Errors */}
          {status.permission_status.errors.length > 0 && (
            <div className="mt-4">
              <p className="mb-2 text-sm font-medium text-red-400">Letzte Fehler</p>
              <div className="space-y-1">
                {status.permission_status.errors.slice(-5).map((err, idx) => (
                  <p key={idx} className="rounded bg-red-500/10 px-3 py-1 text-xs text-red-300 font-mono">
                    {err}
                  </p>
                ))}
              </div>
            </div>
          )}

          {/* Help text if no write access */}
          {!status.permission_status.has_write_access && (
            <div className="mt-4 rounded-lg border border-amber-500/30 bg-amber-500/10 p-4">
              <p className="text-sm font-medium text-amber-300">Schreibzugriff einrichten</p>
              <p className="mt-1 text-xs text-amber-200/80">
                Option 1: Benutzer zur cpufreq-Gruppe hinzufügen:
              </p>
              <code className="mt-1 block rounded bg-slate-900/50 px-2 py-1 text-xs text-slate-300">
                sudo usermod -aG cpufreq {status.permission_status.user}
              </code>
              <p className="mt-2 text-xs text-amber-200/80">
                Option 2: Passwordless sudo für tee erlauben in /etc/sudoers:
              </p>
              <code className="mt-1 block rounded bg-slate-900/50 px-2 py-1 text-xs text-slate-300">
                {status.permission_status.user} ALL=(ALL) NOPASSWD: /usr/bin/tee /sys/devices/system/cpu/*
              </code>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
