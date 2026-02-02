import { Activity, Clock, AlertCircle, Server, Database, Layers } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { ApplicationMetrics } from '../../api/service-status';
import { formatUptime, formatBytes } from '../../api/service-status';

interface AppMetricsProps {
  metrics: ApplicationMetrics;
}

export default function AppMetrics({ metrics }: AppMetricsProps) {
  const { t } = useTranslation(['system', 'common']);
  
  return (
    <div className="space-y-4">
      {/* Main Metrics */}
      <div className="card border-slate-800/40">
        <h3 className="font-semibold text-white mb-4 flex items-center gap-2">
          <Activity className="w-5 h-5 text-slate-400" />
          {t('system:services.metrics.title')}
        </h3>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {/* Server Uptime */}
          <div className="p-3 bg-slate-800/50 rounded-lg">
            <div className="flex items-center gap-2 text-slate-400 mb-1">
              <Clock className="w-4 h-4" />
              <span className="text-xs">{t('system:services.metrics.serverUptime')}</span>
            </div>
            <p className="text-lg font-bold text-white">
              {formatUptime(metrics.server_uptime_seconds)}
            </p>
          </div>

          {/* Active Tasks */}
          <div className="p-3 bg-slate-800/50 rounded-lg">
            <div className="flex items-center gap-2 text-slate-400 mb-1">
              <Layers className="w-4 h-4" />
              <span className="text-xs">{t('system:services.metrics.activeTasks')}</span>
            </div>
            <p className="text-lg font-bold text-white">
              {metrics.active_tasks}
            </p>
          </div>

          {/* Memory Usage */}
          <div className="p-3 bg-slate-800/50 rounded-lg">
            <div className="flex items-center gap-2 text-slate-400 mb-1">
              <Server className="w-4 h-4" />
              <span className="text-xs">{t('system:services.metrics.memory')}</span>
            </div>
            <p className="text-lg font-bold text-white">
              {formatBytes(metrics.memory_bytes)}
            </p>
            <p className="text-xs text-slate-400">
              {metrics.memory_percent.toFixed(1)}%
            </p>
          </div>

          {/* Error Count */}
          <div className="p-3 bg-slate-800/50 rounded-lg">
            <div className="flex items-center gap-2 text-slate-400 mb-1">
              <AlertCircle className="w-4 h-4" />
              <span className="text-xs">{t('system:services.metrics.apiErrors')}</span>
            </div>
            <div className="flex items-baseline gap-2">
              <p className={`text-lg font-bold ${metrics.error_count_5xx > 0 ? 'text-red-400' : 'text-white'}`}>
                {metrics.error_count_5xx}
                <span className="text-xs text-slate-400 ml-1">5xx</span>
              </p>
              <p className={`text-lg font-bold ${metrics.error_count_4xx > 0 ? 'text-yellow-400' : 'text-white'}`}>
                {metrics.error_count_4xx}
                <span className="text-xs text-slate-400 ml-1">4xx</span>
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* DB Pool Status */}
      {metrics.db_pool_status && (
        <div className="card border-slate-800/40">
          <h3 className="font-semibold text-white mb-4 flex items-center gap-2">
            <Database className="w-5 h-5 text-slate-400" />
            {t('system:services.metrics.dbPool')}
          </h3>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="p-3 bg-slate-800/50 rounded-lg">
              <p className="text-xs text-slate-400 mb-1">{t('system:services.metrics.poolSize')}</p>
              <p className="text-lg font-bold text-white">
                {metrics.db_pool_status.pool_size}
              </p>
            </div>
            <div className="p-3 bg-slate-800/50 rounded-lg">
              <p className="text-xs text-slate-400 mb-1">{t('system:services.metrics.available')}</p>
              <p className="text-lg font-bold text-green-400">
                {metrics.db_pool_status.checked_in}
              </p>
            </div>
            <div className="p-3 bg-slate-800/50 rounded-lg">
              <p className="text-xs text-slate-400 mb-1">{t('system:services.metrics.inUse')}</p>
              <p className={`text-lg font-bold ${metrics.db_pool_status.checked_out > 0 ? 'text-yellow-400' : 'text-white'}`}>
                {metrics.db_pool_status.checked_out}
              </p>
            </div>
            <div className="p-3 bg-slate-800/50 rounded-lg">
              <p className="text-xs text-slate-400 mb-1">{t('system:services.metrics.overflow')}</p>
              <p className={`text-lg font-bold ${metrics.db_pool_status.overflow > 0 ? 'text-red-400' : 'text-white'}`}>
                {metrics.db_pool_status.overflow}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Cache Stats */}
      {metrics.cache_stats.length > 0 && (
        <div className="card border-slate-800/40">
          <h3 className="font-semibold text-white mb-4 flex items-center gap-2">
            <Layers className="w-5 h-5 text-slate-400" />
            {t('system:services.metrics.cache')}
          </h3>

          <div className="space-y-3">
            {metrics.cache_stats.map((cache) => {
              const hitRate = cache.hits + cache.misses > 0
                ? (cache.hits / (cache.hits + cache.misses) * 100).toFixed(1)
                : '0.0';

              return (
                <div key={cache.name} className="p-3 bg-slate-800/50 rounded-lg">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-medium text-white">{cache.name}</span>
                    <span className="text-sm text-green-400">{hitRate}% {t('system:services.metrics.hitRate')}</span>
                  </div>
                  <div className="grid grid-cols-4 gap-2 text-sm">
                    <div>
                      <p className="text-xs text-slate-400">{t('system:services.metrics.hits')}</p>
                      <p className="text-white">{cache.hits.toLocaleString()}</p>
                    </div>
                    <div>
                      <p className="text-xs text-slate-400">{t('system:services.metrics.misses')}</p>
                      <p className="text-white">{cache.misses.toLocaleString()}</p>
                    </div>
                    <div>
                      <p className="text-xs text-slate-400">{t('system:services.metrics.size')}</p>
                      <p className="text-white">{cache.size}</p>
                    </div>
                    <div>
                      <p className="text-xs text-slate-400">{t('system:services.metrics.maxSize')}</p>
                      <p className="text-white">{cache.max_size ?? '-'}</p>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
