import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { HardDrive, GitBranch, Database, Layers } from 'lucide-react';
import { formatBytes } from '../../lib/formatters';
import { getStorageBreakdown } from '../../api/system';
import type { StorageBreakdownResponse } from '../../api/system';
import { getUserQuota } from '../../api/vcl';
import { getCacheOverview } from '../../api/ssd-file-cache';
import StorageBreakdownRing from './StorageBreakdownRing';
import type { QuotaInfo } from '../../types/vcl';
import type { SSDCacheStats } from '../../api/ssd-file-cache';
import { apiClient } from '../../lib/api';

interface StorageQuota {
  used_bytes: number;
  limit_bytes: number | null;
  available_bytes: number | null;
  percent_used: number | null;
}

interface StorageTabProps {
  isAdmin: boolean;
  onNavigateToVcl: () => void;
}

function getUsageColor(percent: number): string {
  if (percent > 90) return '#ef4444';
  if (percent > 75) return '#f59e0b';
  return '#22c55e';
}

export default function StorageTab({ isAdmin, onNavigateToVcl }: StorageTabProps) {
  const { t } = useTranslation('settings');
  const navigate = useNavigate();

  const [storageQuota, setStorageQuota] = useState<StorageQuota | null>(null);
  const [storageBreakdown, setStorageBreakdown] = useState<StorageBreakdownResponse | null>(null);
  const [vclQuota, setVclQuota] = useState<QuotaInfo | null>(null);
  const [cacheOverview, setCacheOverview] = useState<SSDCacheStats[] | null>(null);

  useEffect(() => {
    loadStorageQuota();
    loadStorageBreakdown();
    loadVclQuota();
    loadCacheOverview();
  }, []);

  const loadStorageQuota = async () => {
    try {
      const response = await apiClient.get('/api/system/quota');
      setStorageQuota(response.data);
    } catch {
      // Failed to load storage quota
    }
  };

  const loadStorageBreakdown = async () => {
    try {
      const data = await getStorageBreakdown();
      setStorageBreakdown(data);
    } catch {
      // Failed to load storage breakdown
    }
  };

  const loadVclQuota = async () => {
    try {
      const data = await getUserQuota();
      setVclQuota(data);
    } catch {
      // VCL not available
    }
  };

  const loadCacheOverview = async () => {
    try {
      const data = await getCacheOverview();
      setCacheOverview(data);
    } catch {
      setCacheOverview([]);
    }
  };

  return (
    <>
      {/* System Storage Overview */}
      <div className="card border-slate-800/60 bg-slate-900/55 shadow-[0_4px_24px_rgba(56,189,248,0.06)] hover:shadow-[0_8px_32px_rgba(56,189,248,0.12)] transition-shadow">
        <h3 className="text-base sm:text-lg font-semibold mb-4 flex items-center">
          <Database className="w-4 h-4 sm:w-5 sm:h-5 mr-2 text-sky-400" />
          {t('storage.systemStorage')}
        </h3>
        {storageBreakdown ? (
          <div className="flex flex-col sm:flex-row items-center gap-6 sm:gap-8">
            <StorageBreakdownRing
              entries={storageBreakdown.entries}
              totalCapacity={storageBreakdown.total_capacity}
              totalUsePercent={storageBreakdown.total_use_percent}
              size={140}
              strokeWidth={12}
            />
            <div className="flex-1 space-y-3 w-full">
              <div className="text-center sm:text-left">
                <p className="text-xs text-slate-400 mb-0.5">{t('storage.totalCapacity')}</p>
                <p className="text-2xl font-bold">{formatBytes(storageBreakdown.total_capacity)}</p>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="px-3 py-2.5 rounded-lg bg-slate-800/40 border border-slate-700/30">
                  <p className="text-xs text-slate-400 mb-0.5">{t('storage.used')}</p>
                  <p className="text-sm font-semibold">{formatBytes(storageBreakdown.total_used)}</p>
                </div>
                <div className="px-3 py-2.5 rounded-lg bg-slate-800/40 border border-slate-700/30">
                  <p className="text-xs text-slate-400 mb-0.5">{t('storage.available')}</p>
                  <p className="text-sm font-semibold">{formatBytes(storageBreakdown.total_available)}</p>
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="flex flex-col sm:flex-row items-center gap-6 animate-pulse">
            <div className="w-[140px] h-[140px] rounded-full bg-slate-800/50" />
            <div className="flex-1 space-y-3 w-full">
              <div className="h-5 w-24 rounded bg-slate-700/50" />
              <div className="h-8 w-32 rounded bg-slate-700/50" />
              <div className="grid grid-cols-2 gap-3">
                <div className="h-14 rounded-lg bg-slate-700/30" />
                <div className="h-14 rounded-lg bg-slate-700/30" />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* My Arrays + VCL side by side */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6">
        {/* My Arrays — admin can click to RAID settings */}
        <div
          className={`card border-slate-800/60 bg-slate-900/55 shadow-[0_4px_24px_rgba(52,211,153,0.06)] hover:shadow-[0_8px_32px_rgba(52,211,153,0.12)] transition-all ${isAdmin ? 'cursor-pointer hover:border-emerald-500/30' : ''}`}
          {...(isAdmin ? { onClick: () => navigate('/admin/system-control?tab=raid') } : {})}
        >
          <h3 className="text-base sm:text-lg font-semibold mb-4 flex items-center">
            <HardDrive className="w-4 h-4 sm:w-5 sm:h-5 mr-2 text-emerald-400" />
            {t('storage.myArrays')}
          </h3>
          {storageQuota ? (
            <div className="space-y-3">
              <div className="flex justify-between text-sm">
                <span className="text-slate-400">{t('storage.used')}</span>
                <span className="font-semibold">
                  {formatBytes(storageQuota.used_bytes)}
                  {storageQuota.limit_bytes && ` / ${formatBytes(storageQuota.limit_bytes)}`}
                </span>
              </div>
              {storageQuota.limit_bytes && storageQuota.percent_used != null ? (
                <>
                  <div className="w-full h-3 rounded-full overflow-hidden bg-slate-800/60">
                    <div
                      className="h-full rounded-full transition-all duration-700"
                      style={{
                        width: `${Math.min(storageQuota.percent_used, 100)}%`,
                        backgroundColor: getUsageColor(storageQuota.percent_used)
                      }}
                    />
                  </div>
                  <p className="text-sm text-slate-400">
                    {formatBytes(storageQuota.available_bytes ?? 0)} {t('storage.remaining')}
                  </p>
                </>
              ) : (
                <p className="text-sm text-slate-400">{t('storage.noLimit')}</p>
              )}
            </div>
          ) : (
            <div className="space-y-3 animate-pulse">
              <div className="flex justify-between">
                <div className="h-4 w-16 rounded bg-slate-700/50" />
                <div className="h-4 w-28 rounded bg-slate-700/50" />
              </div>
              <div className="w-full h-3 rounded-full bg-slate-700/50" />
              <div className="h-3 w-24 rounded bg-slate-700/50" />
            </div>
          )}
        </div>

        {/* VCL Storage Quota — clickable to switch to VCL tab */}
        <div
          className="card border-slate-800/60 bg-slate-900/55 shadow-[0_4px_24px_rgba(139,92,246,0.06)] hover:shadow-[0_8px_32px_rgba(139,92,246,0.12)] hover:border-violet-500/30 transition-all cursor-pointer"
          onClick={onNavigateToVcl}
          title={t('storage.vclClickHint')}
        >
          <h3 className="text-base sm:text-lg font-semibold mb-4 flex items-center">
            <GitBranch className="w-4 h-4 sm:w-5 sm:h-5 mr-2 text-violet-400" />
            {t('storage.vclTitle')}
          </h3>
          {vclQuota ? (
            vclQuota.is_enabled ? (
              <div className="space-y-3">
                <div className="flex justify-between text-sm">
                  <span className="text-slate-400">{t('storage.used')}</span>
                  <span className="font-semibold">
                    {formatBytes(vclQuota.current_usage_bytes)} / {formatBytes(vclQuota.max_size_bytes)}
                  </span>
                </div>
                <div className="w-full h-3 rounded-full overflow-hidden bg-slate-800/60">
                  <div
                    className="h-full rounded-full transition-all duration-700"
                    style={{
                      width: `${Math.min(vclQuota.usage_percent, 100)}%`,
                      backgroundColor: getUsageColor(vclQuota.usage_percent)
                    }}
                  />
                </div>
                <p className="text-sm text-slate-400">
                  {formatBytes(vclQuota.available_bytes)} {t('storage.remaining')}
                </p>
                <div className="grid grid-cols-3 gap-2 pt-3 border-t border-slate-700/40">
                  <div className="text-center px-2 py-1.5 rounded-lg bg-slate-800/40">
                    <p className="text-[10px] text-slate-500 uppercase tracking-wider">{t('storage.compression')}</p>
                    <p className={`text-xs font-medium mt-0.5 ${vclQuota.compression_enabled ? 'text-emerald-400' : 'text-slate-500'}`}>
                      {vclQuota.compression_enabled ? t('storage.enabled') : t('storage.disabled')}
                    </p>
                  </div>
                  <div className="text-center px-2 py-1.5 rounded-lg bg-slate-800/40">
                    <p className="text-[10px] text-slate-500 uppercase tracking-wider">{t('storage.deduplication')}</p>
                    <p className={`text-xs font-medium mt-0.5 ${vclQuota.dedupe_enabled ? 'text-emerald-400' : 'text-slate-500'}`}>
                      {vclQuota.dedupe_enabled ? t('storage.enabled') : t('storage.disabled')}
                    </p>
                  </div>
                  <div className="text-center px-2 py-1.5 rounded-lg bg-slate-800/40">
                    <p className="text-[10px] text-slate-500 uppercase tracking-wider">{t('storage.depth')}</p>
                    <p className="text-xs font-medium mt-0.5">{vclQuota.depth}</p>
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-3 p-3 rounded-lg bg-slate-800/60 border border-slate-700/40">
                <GitBranch className="w-5 h-5 text-slate-500" />
                <p className="text-sm text-slate-400">{t('storage.vclDisabled')}</p>
              </div>
            )
          ) : (
            <div className="space-y-3 animate-pulse">
              <div className="flex justify-between">
                <div className="h-4 w-16 rounded bg-slate-700/50" />
                <div className="h-4 w-28 rounded bg-slate-700/50" />
              </div>
              <div className="w-full h-3 rounded-full bg-slate-700/50" />
              <div className="h-3 w-24 rounded bg-slate-700/50" />
            </div>
          )}
        </div>
      </div>

      {/* SSD Cache */}
      <div className="card border-slate-800/60 bg-slate-900/55 shadow-[0_4px_24px_rgba(245,158,11,0.06)] hover:shadow-[0_8px_32px_rgba(245,158,11,0.12)] transition-shadow">
        <h3 className="text-base sm:text-lg font-semibold mb-4 flex items-center">
          <Layers className="w-4 h-4 sm:w-5 sm:h-5 mr-2 text-amber-400" />
          {t('storage.cacheTitle')}
        </h3>
        {cacheOverview === null ? (
          <div className="space-y-3 animate-pulse">
            <div className="h-20 rounded-lg bg-slate-700/30" />
          </div>
        ) : cacheOverview.length === 0 ? (
          <div className="flex items-center gap-3 p-3 rounded-lg bg-slate-800/60 border border-slate-700/40">
            <Layers className="w-5 h-5 text-slate-500" />
            <p className="text-sm text-slate-400">{t('storage.noCacheConfigured')}</p>
          </div>
        ) : (
          <div className="space-y-4">
            {cacheOverview.map(cache => (
              <div key={cache.array_name} className="p-4 rounded-xl bg-slate-800/40 border border-slate-700/30">
                <div className="flex justify-between items-center mb-3">
                  <span className="font-medium text-sm">{t('storage.cacheFor', { array: cache.array_name })}</span>
                  <span className={`text-xs px-2 py-0.5 rounded-full ${
                    cache.is_enabled
                      ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                      : 'bg-slate-700/50 text-slate-400 border border-slate-600/30'
                  }`}>
                    {cache.is_enabled ? t('storage.enabled') : t('storage.disabled')}
                  </span>
                </div>
                {cache.ssd_total_bytes > 0 && (
                  <p className="text-xs text-slate-500 mb-2">
                    SSD {formatBytes(cache.ssd_total_bytes)} — {formatBytes(cache.ssd_available_bytes)} {t('storage.available').toLowerCase()}
                  </p>
                )}
                <div className="flex justify-between text-sm mb-2">
                  <span className="text-slate-400">{t('storage.used')}</span>
                  <span className="font-semibold">
                    {formatBytes(cache.current_size_bytes)} / {formatBytes(cache.max_size_bytes)}
                  </span>
                </div>
                <div className="w-full h-2.5 rounded-full overflow-hidden bg-slate-800/60 mb-4">
                  <div
                    className="h-full rounded-full transition-all duration-700"
                    style={{
                      width: `${Math.min(cache.usage_percent, 100)}%`,
                      backgroundColor: '#f59e0b'
                    }}
                  />
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <div className="text-center p-2 rounded-lg bg-slate-900/60">
                    <p className="text-[10px] text-slate-500 uppercase tracking-wider">{t('storage.hitRate')}</p>
                    <p className="text-sm font-semibold text-amber-400 mt-0.5">
                      {cache.hit_rate_percent.toFixed(1)}%
                    </p>
                  </div>
                  <div className="text-center p-2 rounded-lg bg-slate-900/60">
                    <p className="text-[10px] text-slate-500 uppercase tracking-wider">{t('storage.entries')}</p>
                    <p className="text-sm font-semibold mt-0.5">
                      {cache.valid_entries} / {cache.total_entries}
                    </p>
                  </div>
                  <div className="text-center p-2 rounded-lg bg-slate-900/60">
                    <p className="text-[10px] text-slate-500 uppercase tracking-wider">{t('storage.served')}</p>
                    <p className="text-sm font-semibold mt-0.5">
                      {formatBytes(cache.total_bytes_served)}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
