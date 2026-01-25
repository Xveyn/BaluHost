/**
 * Power Status Widget
 *
 * Compact widget for displaying power management status on the dashboard.
 * Shows current profile, frequency, and active demand count.
 */

import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import {
  getPowerStatus,
  PROFILE_INFO,
  type PowerStatusResponse,
  type PowerProfile,
} from '../api/power-management';

const REFRESH_INTERVAL_MS = 10000;

// Format frequency for display
const formatFrequency = (mhz: number | undefined | null): string => {
  if (mhz === undefined || mhz === null) return '-';
  if (mhz >= 1000) return `${(mhz / 1000).toFixed(1)} GHz`;
  return `${Math.round(mhz)} MHz`;
};

// Profile color classes
const getProfileBgClass = (profile: PowerProfile): string => {
  const colors: Record<PowerProfile, string> = {
    idle: 'bg-emerald-500/20',
    low: 'bg-blue-500/20',
    medium: 'bg-yellow-500/20',
    surge: 'bg-red-500/20',
  };
  return colors[profile] || 'bg-slate-500/20';
};

const getProfileTextClass = (profile: PowerProfile): string => {
  const colors: Record<PowerProfile, string> = {
    idle: 'text-emerald-300',
    low: 'text-blue-300',
    medium: 'text-yellow-300',
    surge: 'text-red-300',
  };
  return colors[profile] || 'text-slate-300';
};

interface PowerStatusWidgetProps {
  className?: string;
}

export default function PowerStatusWidget({ className = '' }: PowerStatusWidgetProps) {
  const [status, setStatus] = useState<PowerStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadStatus = async () => {
      try {
        const data = await getPowerStatus();
        setStatus(data);
        setError(null);
      } catch (err) {
        setError('Laden fehlgeschlagen');
      } finally {
        setLoading(false);
      }
    };

    void loadStatus();
    const interval = setInterval(() => void loadStatus(), REFRESH_INTERVAL_MS);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div className={`card border-slate-700/50 p-4 ${className}`}>
        <div className="flex items-center justify-center py-4">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
        </div>
      </div>
    );
  }

  if (error || !status) {
    return (
      <div className={`card border-slate-700/50 p-4 ${className}`}>
        <div className="text-center text-sm text-slate-500">
          Power-Status nicht verfügbar
        </div>
      </div>
    );
  }

  const profile = status.current_profile;
  const info = PROFILE_INFO[profile];

  return (
    <Link
      to="/power"
      className={`card block border-slate-700/50 p-4 transition-all hover:border-slate-600 hover:bg-slate-800/50 ${className}`}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          {/* Profile icon */}
          <div className={`rounded-full p-2 ${getProfileBgClass(profile)}`}>
            <span className="text-xl">{info.icon}</span>
          </div>

          {/* Profile info */}
          <div>
            <p className="text-xs font-medium uppercase tracking-wider text-slate-400">
              Power Profile
            </p>
            <p className={`text-lg font-semibold ${getProfileTextClass(profile)}`}>
              {info.name}
            </p>
          </div>
        </div>

        {/* Stats */}
        <div className="text-right">
          <p className="text-lg font-semibold text-white">
            {formatFrequency(status.current_frequency_mhz)}
          </p>
          <p className="text-xs text-slate-400">
            {status.active_demands.length > 0
              ? `${status.active_demands.length} Anforderung${status.active_demands.length !== 1 ? 'en' : ''}`
              : 'Keine Anforderungen'}
          </p>
        </div>
      </div>

      {/* Footer */}
      <div className="mt-3 flex items-center justify-between border-t border-slate-700/50 pt-3">
        <div className="flex items-center gap-2">
          {status.auto_scaling_enabled && (
            <span className="flex items-center gap-1 text-xs text-emerald-400">
              <svg className="h-3 w-3" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
              Auto-Scaling
            </span>
          )}
          {status.is_dev_mode && (
            <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-xs text-amber-300">
              Dev
            </span>
          )}
        </div>
        <span className="text-xs text-slate-500">
          {status.target_frequency_range || 'Dynamisch'}
        </span>
      </div>
    </Link>
  );
}
