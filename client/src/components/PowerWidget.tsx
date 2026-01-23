/**
 * Power monitoring widget for Dashboard
 *
 * Displays current NAS power consumption matching Dashboard design style.
 */

import React from 'react';
import { Zap } from 'lucide-react';
import { usePowerMonitoring } from '../hooks/usePowerMonitoring';

const PowerWidget: React.FC = () => {
  const { data, loading, error } = usePowerMonitoring();

  // Calculate current total power and trend
  const currentPower = data?.total_current_power || 0;
  const devices = data?.devices || [];

  // Get all samples from all devices for trend calculation
  const allSamples = devices.flatMap(d => d.samples);

  // Sort by timestamp and take last samples
  const recentSamples = allSamples
    .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
    .slice(-30);

  // Calculate trend (compare last 5 samples vs previous 5)
  let trendDelta = 0;
  if (recentSamples.length >= 10) {
    const recent5 = recentSamples.slice(-5);
    const previous5 = recentSamples.slice(-10, -5);
    const recentAvg = recent5.reduce((sum, s) => sum + s.watts, 0) / recent5.length;
    const previousAvg = previous5.reduce((sum, s) => sum + s.watts, 0) / previous5.length;
    trendDelta = recentAvg - previousAvg;
  }

  // Calculate total energy today (sum of all devices)
  const totalEnergyToday = devices.reduce((sum, device) => {
    const latest = device.latest_sample;
    return sum + (latest?.energy_today || 0);
  }, 0);

  // Format trend delta
  const formatDelta = () => {
    if (Math.abs(trendDelta) < 1) {
      return { label: 'Stable', tone: 'steady' };
    }
    if (trendDelta > 0) {
      return { label: `+${trendDelta.toFixed(1)}W`, tone: 'increase' };
    }
    return { label: `${trendDelta.toFixed(1)}W`, tone: 'decrease' };
  };

  const delta = formatDelta();
  const deltaToneClass = delta.tone === 'decrease'
    ? 'text-emerald-400'
    : delta.tone === 'increase'
      ? 'text-rose-300'
      : 'text-slate-400';

  // Calculate progress (percentage of typical max power)
  // Assume max 150W for a typical NAS
  const maxPower = 150;
  const progress = Math.min((currentPower / maxPower) * 100, 100);

  // Handle loading/error/no-devices states
  if (loading) {
    return (
      <div className="card border-slate-800/40 bg-slate-900/60">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-xs uppercase tracking-[0.28em] text-slate-500">Power</p>
            <p className="mt-2 text-2xl sm:text-3xl font-semibold text-slate-400">Loading...</p>
          </div>
          <div className="flex h-11 w-11 sm:h-12 sm:w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-amber-500 to-orange-500 text-white shadow-[0_12px_38px_rgba(251,146,60,0.35)]">
            <Zap className="h-6 w-6" />
          </div>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="card border-slate-800/40 bg-slate-900/60">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-xs uppercase tracking-[0.28em] text-slate-500">Power</p>
            <p className="mt-2 text-2xl sm:text-3xl font-semibold text-slate-400">Offline</p>
          </div>
          <div className="flex h-11 w-11 sm:h-12 sm:w-12 shrink-0 items-center justify-center rounded-2xl bg-slate-800 text-slate-500">
            <Zap className="h-6 w-6" />
          </div>
        </div>
        <div className="mt-3 sm:mt-4 flex items-center justify-between gap-2 text-xs text-slate-400">
          <span className="truncate">No devices configured</span>
        </div>
      </div>
    );
  }

  if (devices.length === 0) {
    return (
      <div className="card border-slate-800/40 bg-slate-900/60">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-xs uppercase tracking-[0.28em] text-slate-500">Power</p>
            <p className="mt-2 text-2xl sm:text-3xl font-semibold text-slate-400">—</p>
          </div>
          <div className="flex h-11 w-11 sm:h-12 sm:w-12 shrink-0 items-center justify-center rounded-2xl bg-slate-800 text-slate-500">
            <Zap className="h-6 w-6" />
          </div>
        </div>
        <div className="mt-3 sm:mt-4 flex items-center justify-between gap-2 text-xs text-slate-400">
          <span className="truncate">Configure in Settings</span>
        </div>
      </div>
    );
  }

  return (
    <div className="card border-slate-800/40 bg-slate-900/60 transition-all duration-200 hover:border-slate-700/60 hover:bg-slate-900/80 hover:shadow-[0_14px_44px_rgba(251,146,60,0.15)] active:scale-[0.98] touch-manipulation">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-xs uppercase tracking-[0.28em] text-slate-500">Power</p>
          <p className="mt-2 text-2xl sm:text-3xl font-semibold text-white truncate">
            {currentPower.toFixed(1)} W
          </p>
        </div>
        <div className="flex h-11 w-11 sm:h-12 sm:w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-amber-500 to-orange-500 text-white shadow-[0_12px_38px_rgba(251,146,60,0.35)]">
          <Zap className="h-6 w-6" />
        </div>
      </div>
      <div className="mt-3 sm:mt-4 flex flex-col gap-1">
        <div className="flex items-center justify-between gap-2 text-xs text-slate-400">
          <span className="truncate flex-1 min-w-0">
            Energy today: {totalEnergyToday.toFixed(2)} kWh
          </span>
          <span className={`${deltaToneClass} shrink-0`}>{delta.label}</span>
        </div>
        <div className="text-xs text-slate-500 truncate">
          {devices.length} {devices.length === 1 ? 'device' : 'devices'} monitored
        </div>
      </div>
      <div className="mt-4 sm:mt-5 h-2 w-full overflow-hidden rounded-full bg-slate-800">
        <div
          className="h-full rounded-full bg-gradient-to-r from-amber-500 to-orange-500 transition-all duration-500"
          style={{ width: `${Math.min(Math.max(progress, 0), 100)}%` }}
        />
      </div>
    </div>
  );
};

export default PowerWidget;
