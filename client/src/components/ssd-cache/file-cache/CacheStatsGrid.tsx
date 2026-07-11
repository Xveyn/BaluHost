import { Zap, HardDrive, BarChart3, Activity } from 'lucide-react';
import type { SSDCacheStats } from '../../../api/ssd-file-cache';
import { formatBytes } from '../../../lib/formatters';
import { cacheUsageBarColor } from './cacheUsageBarColor';

export function CacheStatsGrid({ stats }: { stats: SSDCacheStats }): JSX.Element {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      {/* Status */}
      <div className="card border-slate-800/60 bg-slate-900/55">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-slate-400 text-sm">Status</p>
            <div className="flex items-center gap-2 mt-1">
              <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                stats.is_enabled
                  ? 'bg-emerald-500/20 text-emerald-300'
                  : 'bg-red-500/20 text-red-300'
              }`}>
                {stats.is_enabled ? 'Enabled' : 'Disabled'}
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-1">{stats.total_entries} entries ({stats.valid_entries} valid)</p>
          </div>
          <Zap className="w-10 h-10 text-cyan-400 opacity-50" />
        </div>
      </div>

      {/* Cache Usage */}
      <div className="card border-slate-800/60 bg-slate-900/55">
        <div className="flex items-center justify-between">
          <div className="flex-1">
            <p className="text-slate-400 text-sm">Cache Usage</p>
            <p className="text-2xl font-bold text-white mt-1">{formatBytes(stats.current_size_bytes)}</p>
            <p className="text-xs text-slate-500 mt-1">of {formatBytes(stats.max_size_bytes)}</p>
            <div className="h-1.5 w-full mt-2 overflow-hidden rounded-full bg-slate-800">
              <div
                className={`h-full rounded-full transition-all ${cacheUsageBarColor(stats.usage_percent)}`}
                style={{ width: `${Math.min(stats.usage_percent, 100)}%` }}
              />
            </div>
          </div>
          <HardDrive className="w-10 h-10 text-violet-400 opacity-50 flex-shrink-0 ml-3" />
        </div>
      </div>

      {/* Hit Rate */}
      <div className="card border-slate-800/60 bg-slate-900/55">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-slate-400 text-sm">Hit Rate</p>
            <p className="text-2xl font-bold text-white mt-1">{stats.hit_rate_percent.toFixed(1)}%</p>
            <p className="text-xs text-slate-500 mt-1">
              {stats.total_hits.toLocaleString()} hits / {stats.total_misses.toLocaleString()} misses
            </p>
          </div>
          <BarChart3 className="w-10 h-10 text-green-400 opacity-50" />
        </div>
      </div>

      {/* Bytes Served */}
      <div className="card border-slate-800/60 bg-slate-900/55">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-slate-400 text-sm">Bytes Served</p>
            <p className="text-2xl font-bold text-white mt-1">{formatBytes(stats.total_bytes_served)}</p>
            <p className="text-xs text-slate-500 mt-1">from SSD cache</p>
          </div>
          <Activity className="w-10 h-10 text-amber-400 opacity-50" />
        </div>
      </div>
    </div>
  );
}
