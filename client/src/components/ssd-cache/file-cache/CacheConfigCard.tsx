import { Settings, Check } from 'lucide-react';
import { ByteSizeInput } from '../../ui/ByteSizeInput';
import type { SSDCacheConfigUpdate, SSDCacheConfigResponse } from '../../../api/ssd-file-cache';

export function CacheConfigCard(props: {
  configForm: SSDCacheConfigUpdate;
  config: SSDCacheConfigResponse;
  configDirty: boolean;
  actionLoading: boolean;
  onConfigChange: (key: keyof SSDCacheConfigUpdate, value: unknown) => void;
  onSave: () => void;
  onReset: (cfg: SSDCacheConfigResponse) => void;
}) {
  const { configForm, config, configDirty, actionLoading, onConfigChange, onSave, onReset } = props;

  return (
    <div className="card border-slate-800/60 bg-slate-900/55">
      <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
        <Settings className="w-5 h-5 text-sky-400" />
        Configuration
      </h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {/* Enable/Disable */}
        <div>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={configForm.is_enabled ?? false}
              onChange={(e) => onConfigChange('is_enabled', e.target.checked)}
              className="w-4 h-4 rounded border-slate-700 bg-slate-800"
            />
            <span className="text-sm text-slate-300">Cache Enabled</span>
          </label>
        </div>

        {/* Max Size */}
        <div>
          <ByteSizeInput
            label="Max Size"
            value={configForm.max_size_bytes ?? 0}
            onChange={(bytes) => onConfigChange('max_size_bytes', bytes)}
          />
        </div>

        {/* Eviction Policy */}
        <div>
          <label className="block text-sm text-slate-400 mb-1">Eviction Policy</label>
          <select
            value={configForm.eviction_policy ?? 'lfru'}
            onChange={(e) => onConfigChange('eviction_policy', e.target.value)}
            className="w-full px-3 py-1.5 bg-slate-800 border border-slate-700 rounded-lg text-white text-sm"
          >
            <option value="lfru">LFRU (Least Frequently + Recently Used)</option>
            <option value="lru">LRU (Least Recently Used)</option>
            <option value="lfu">LFU (Least Frequently Used)</option>
          </select>
        </div>

        {/* Min File Size */}
        <div>
          <ByteSizeInput
            label="Min File Size"
            value={configForm.min_file_size_bytes ?? 0}
            onChange={(bytes) => onConfigChange('min_file_size_bytes', bytes)}
          />
        </div>

        {/* Max File Size */}
        <div>
          <ByteSizeInput
            label="Max File Size"
            value={configForm.max_file_size_bytes ?? 0}
            onChange={(bytes) => onConfigChange('max_file_size_bytes', bytes)}
          />
        </div>

        {/* Sequential Cutoff */}
        <div>
          <ByteSizeInput
            label="Sequential Cutoff"
            value={configForm.sequential_cutoff_bytes ?? 0}
            onChange={(bytes) => onConfigChange('sequential_cutoff_bytes', bytes)}
          />
        </div>
      </div>

      {/* Save / Reset */}
      <div className="flex gap-3 mt-4 pt-4 border-t border-slate-800/60">
        <button
          onClick={onSave}
          disabled={actionLoading || !configDirty}
          className="px-4 py-2 bg-sky-500 hover:bg-sky-600 text-white rounded-lg transition-colors disabled:opacity-50 flex items-center gap-2 text-sm"
        >
          <Check className="w-4 h-4" />
          Save Configuration
        </button>
        {configDirty && config && (
          <button
            onClick={() => onReset(config)}
            className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-lg transition-colors text-sm"
          >
            Reset
          </button>
        )}
      </div>
    </div>
  );
}
