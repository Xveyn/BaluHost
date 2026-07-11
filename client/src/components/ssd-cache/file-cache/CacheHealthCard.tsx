import { Check, X, Heart } from 'lucide-react';
import { formatBytes } from '../../../lib/formatters';
import type { CacheHealthResponse } from '../../../api/ssd-file-cache';

export function CacheHealthCard({ health }: { health: CacheHealthResponse }) {
  return (
    <div className="card border-slate-800/60 bg-slate-900/55">
      <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
        <Heart className="w-5 h-5 text-sky-400" />
        SSD Health
      </h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 text-sm">
        <div>
          <p className="text-slate-400">SSD Mount</p>
          <p className={`font-semibold mt-1 flex items-center gap-1 ${health.is_mounted ? 'text-emerald-400' : 'text-red-400'}`}>
            {health.is_mounted ? <Check className="w-4 h-4" /> : <X className="w-4 h-4" />}
            {health.is_mounted ? 'Mounted' : 'Not Mounted'}
          </p>
        </div>
        <div>
          <p className="text-slate-400">Disk Free</p>
          <p className="text-white font-semibold mt-1">{formatBytes(health.ssd_available_bytes)}</p>
        </div>
        <div>
          <p className="text-slate-400">Disk Used</p>
          <p className="text-white font-semibold mt-1">{health.ssd_used_percent.toFixed(1)}% of {formatBytes(health.ssd_total_bytes)}</p>
        </div>
        <div>
          <p className="text-slate-400">Cache Directory</p>
          <p className={`font-semibold mt-1 flex items-center gap-1 ${health.cache_dir_exists ? 'text-emerald-400' : 'text-red-400'}`}>
            {health.cache_dir_exists ? <Check className="w-4 h-4" /> : <X className="w-4 h-4" />}
            {health.cache_dir_exists ? 'Exists' : 'Missing'}
          </p>
        </div>
      </div>
    </div>
  );
}
