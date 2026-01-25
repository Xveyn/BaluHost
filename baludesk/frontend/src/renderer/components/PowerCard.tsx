import React, { useState, useEffect } from 'react';
import { Zap } from 'lucide-react';

interface PowerData {
  currentPower: number;
  energyToday: number;
  trendDelta: number;
  deviceCount: number;
  maxPower: number;
  dev_mode?: boolean;
}

export const PowerCard: React.FC = () => {
  const [powerData, setPowerData] = useState<PowerData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchPowerData();

    // Poll every 5 seconds
    const interval = setInterval(() => {
      fetchPowerData();
    }, 5000);

    return () => clearInterval(interval);
  }, []);

  const fetchPowerData = async () => {
    try {
      const response = await window.electronAPI.sendBackendCommand({
        type: 'get_power_monitoring',
      });

      if (response?.success) {
        setPowerData(response.data);
        setLoading(false);
      }
    } catch (error) {
      console.error('Failed to fetch power data:', error);
      setLoading(false);
    }
  };

  if (loading || !powerData) {
    return (
      <div className="rounded-xl border border-white/10 bg-gradient-to-br from-amber-500/10 to-orange-600/10 p-4 backdrop-blur-sm">
        <div className="flex items-center space-x-2">
          <div className="rounded-lg bg-amber-500/20 p-1.5">
            <Zap className="h-4 w-4 text-amber-400" />
          </div>
          <h3 className="text-sm font-medium text-slate-300">Power</h3>
        </div>
        <p className="mt-3 text-sm text-slate-400">Loading...</p>
      </div>
    );
  }

  const progress = Math.min((powerData.currentPower / powerData.maxPower) * 100, 100);

  const getTrendIcon = () => {
    if (powerData.trendDelta > 1) return '↗';
    if (powerData.trendDelta < -1) return '↘';
    return '→';
  };

  const getTrendColor = () => {
    if (powerData.trendDelta > 1) return 'text-rose-400';
    if (powerData.trendDelta < -1) return 'text-emerald-400';
    return 'text-slate-400';
  };

  return (
    <div className="rounded-xl border border-white/10 bg-gradient-to-br from-amber-500/10 to-orange-600/10 p-4 backdrop-blur-sm hover:border-amber-500/30 hover:shadow-lg hover:shadow-amber-500/20 transition-all">
      <div className="flex items-center space-x-2">
        <div className="rounded-lg bg-gradient-to-br from-amber-500/20 to-orange-500/20 p-1.5">
          <Zap className="h-4 w-4 text-amber-400" />
        </div>
        <h3 className="text-sm font-medium text-slate-300">Power</h3>
      </div>

      {/* Current Power */}
      <div className="mt-3">
        <p className="text-3xl font-bold text-white">
          {powerData.currentPower.toFixed(1)}
          <span className="ml-1 text-lg font-normal text-slate-400">W</span>
        </p>
        <p className="mt-1 text-xs text-slate-400">
          {powerData.deviceCount} device{powerData.deviceCount !== 1 ? 's' : ''} monitored
        </p>
      </div>

      {/* Energy Today */}
      <div className="mt-2 flex items-center justify-between text-xs">
        <span className="text-slate-400">Today</span>
        <span className="font-medium text-white">
          {powerData.energyToday.toFixed(2)} kWh
        </span>
      </div>

      {/* Trend */}
      <div className="mt-1.5 flex items-center justify-between text-xs">
        <span className="text-slate-400">Trend</span>
        <span className={`font-medium ${getTrendColor()}`}>
          {getTrendIcon()} {Math.abs(powerData.trendDelta).toFixed(1)}W
        </span>
      </div>

      {/* Progress Bar */}
      <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
        <div
          className="h-full rounded-full bg-gradient-to-r from-amber-500 to-orange-500 transition-all duration-500"
          style={{ width: `${Math.max(0, Math.min(100, progress))}%` }}
        />
      </div>
      <p className="mt-1 text-xs text-slate-400 text-right">
        {progress.toFixed(0)}% of {powerData.maxPower}W
      </p>
    </div>
  );
};
