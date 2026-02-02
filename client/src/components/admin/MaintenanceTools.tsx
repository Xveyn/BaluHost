import { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { getDatabaseHealth } from '../../lib/api'
import type { DatabaseHealthResponse } from '../../lib/api'
import { triggerCleanup } from '../../api/monitoring'
import {
  CheckCircle,
  XCircle,
  AlertTriangle,
  Database,
  RefreshCw,
  Trash2,
  Server,
  Activity,
  Shield
} from 'lucide-react'

interface CleanupResult {
  message: string
  deleted: Record<string, number>
  total: number
}

export default function MaintenanceTools() {
  const { t } = useTranslation(['admin', 'common'])
  const [health, setHealth] = useState<DatabaseHealthResponse | null>(null)
  const [healthLoading, setHealthLoading] = useState(true)
  const [healthError, setHealthError] = useState<string | null>(null)

  const [cleanupLoading, setCleanupLoading] = useState(false)
  const [cleanupResult, setCleanupResult] = useState<CleanupResult | null>(null)
  const [cleanupError, setCleanupError] = useState<string | null>(null)
  const [showConfirm, setShowConfirm] = useState(false)

  const fetchHealth = useCallback(async () => {
    try {
      setHealthError(null)
      const data = await getDatabaseHealth()
      setHealth(data)
    } catch (err: any) {
      setHealthError(err?.message || 'Failed to load health status')
    } finally {
      setHealthLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchHealth()
  }, [fetchHealth])

  const handleCleanup = async () => {
    setShowConfirm(false)
    setCleanupLoading(true)
    setCleanupError(null)
    setCleanupResult(null)

    try {
      const result = await triggerCleanup()
      setCleanupResult(result)
    } catch (err: any) {
      setCleanupError(err?.message || 'Cleanup failed')
    } finally {
      setCleanupLoading(false)
    }
  }

  const getStatusColor = (isHealthy: boolean) => {
    return isHealthy
      ? { bg: 'from-emerald-500/20 to-emerald-600/10', text: 'text-emerald-400', border: 'border-emerald-500/30' }
      : { bg: 'from-red-500/20 to-red-600/10', text: 'text-red-400', border: 'border-red-500/30' }
  }

  const getIntegrityColor = (status?: string) => {
    if (!status) return { bg: 'from-slate-500/20 to-slate-600/10', text: 'text-slate-400', border: 'border-slate-500/30' }
    if (status === 'ok') return { bg: 'from-emerald-500/20 to-emerald-600/10', text: 'text-emerald-400', border: 'border-emerald-500/30' }
    return { bg: 'from-amber-500/20 to-amber-600/10', text: 'text-amber-400', border: 'border-amber-500/30' }
  }

  if (healthLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <RefreshCw className="w-8 h-8 text-blue-400 animate-spin mb-4" />
        <p className="text-slate-400">{t('admin:maintenance.loading')}</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-white">{t('admin:maintenance.title')}</h3>
          <p className="text-xs text-slate-400 mt-1">
            {t('admin:maintenance.subtitle')}
          </p>
        </div>
        <button
          onClick={fetchHealth}
          disabled={healthLoading}
          className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-slate-700/40 text-slate-300 hover:bg-slate-700/60 hover:text-white transition-colors text-sm border border-slate-600/50"
        >
          <RefreshCw className={`w-4 h-4 ${healthLoading ? 'animate-spin' : ''}`} />
          {t('common:refresh')}
        </button>
      </div>

      {healthError && (
        <div className="bg-gradient-to-r from-red-500/10 to-red-600/5 border border-red-500/30 rounded-xl px-5 py-4 backdrop-blur-sm">
          <p className="text-red-400 text-sm font-medium">{healthError}</p>
        </div>
      )}

      {/* Health Status Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Connection Status */}
        <div className="group relative bg-gradient-to-br from-slate-800/40 via-slate-800/30 to-slate-900/20 backdrop-blur-xl border border-slate-700/50 rounded-xl p-4 hover:border-slate-600/50 transition-all duration-300">
          <div className="flex items-center gap-3 mb-3">
            <div className={`w-10 h-10 bg-gradient-to-br ${health?.is_healthy ? getStatusColor(true).bg : getStatusColor(false).bg} rounded-lg flex items-center justify-center`}>
              {health?.is_healthy ? (
                <CheckCircle className="w-5 h-5 text-emerald-400" />
              ) : (
                <XCircle className="w-5 h-5 text-red-400" />
              )}
            </div>
            <div>
              <p className="text-xs text-slate-400">{t('admin:maintenance.connection')}</p>
              <p className={`text-sm font-semibold ${health?.is_healthy ? 'text-emerald-400' : 'text-red-400'}`}>
                {health?.connection_status || t('common:unknown')}
              </p>
            </div>
          </div>
        </div>

        {/* Database Type */}
        <div className="group relative bg-gradient-to-br from-slate-800/40 via-slate-800/30 to-slate-900/20 backdrop-blur-xl border border-slate-700/50 rounded-xl p-4 hover:border-slate-600/50 transition-all duration-300">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 bg-gradient-to-br from-blue-500/20 to-blue-600/10 rounded-lg flex items-center justify-center">
              <Database className="w-5 h-5 text-blue-400" />
            </div>
            <div>
              <p className="text-xs text-slate-400">{t('admin:maintenance.databaseType')}</p>
              <p className="text-sm font-semibold text-white capitalize">
                {health?.database_type || t('common:unknown')}
              </p>
            </div>
          </div>
        </div>

        {/* Integrity Check (SQLite) or Pool Status (PostgreSQL) */}
        {health?.database_type === 'sqlite' ? (
          <div className="group relative bg-gradient-to-br from-slate-800/40 via-slate-800/30 to-slate-900/20 backdrop-blur-xl border border-slate-700/50 rounded-xl p-4 hover:border-slate-600/50 transition-all duration-300">
            <div className="flex items-center gap-3 mb-3">
              <div className={`w-10 h-10 bg-gradient-to-br ${getIntegrityColor(health.integrity_check).bg} rounded-lg flex items-center justify-center`}>
                <Shield className={`w-5 h-5 ${getIntegrityColor(health.integrity_check).text}`} />
              </div>
              <div>
                <p className="text-xs text-slate-400">{t('admin:maintenance.integrityCheck')}</p>
                <p className={`text-sm font-semibold ${getIntegrityColor(health.integrity_check).text}`}>
                  {health.integrity_check || t('common:notAvailable')}
                </p>
              </div>
            </div>
          </div>
        ) : health?.database_type === 'postgresql' ? (
          <div className="group relative bg-gradient-to-br from-slate-800/40 via-slate-800/30 to-slate-900/20 backdrop-blur-xl border border-slate-700/50 rounded-xl p-4 hover:border-slate-600/50 transition-all duration-300">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 bg-gradient-to-br from-purple-500/20 to-purple-600/10 rounded-lg flex items-center justify-center">
                <Server className="w-5 h-5 text-purple-400" />
              </div>
              <div>
                <p className="text-xs text-slate-400">{t('admin:maintenance.poolSize')}</p>
                <p className="text-sm font-semibold text-white">
                  {health.pool_size ?? t('common:notAvailable')}
                </p>
              </div>
            </div>
          </div>
        ) : (
          <div className="group relative bg-gradient-to-br from-slate-800/40 via-slate-800/30 to-slate-900/20 backdrop-blur-xl border border-slate-700/50 rounded-xl p-4 hover:border-slate-600/50 transition-all duration-300">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 bg-gradient-to-br from-slate-500/20 to-slate-600/10 rounded-lg flex items-center justify-center">
                <Activity className="w-5 h-5 text-slate-400" />
              </div>
              <div>
                <p className="text-xs text-slate-400">{t('admin:users.fields.status')}</p>
                <p className="text-sm font-semibold text-slate-400">{t('common:notAvailable')}</p>
              </div>
            </div>
          </div>
        )}

        {/* Health Summary */}
        <div className={`group relative bg-gradient-to-br ${health?.is_healthy ? 'from-emerald-900/20' : 'from-red-900/20'} via-slate-800/30 to-slate-900/20 backdrop-blur-xl border ${health?.is_healthy ? 'border-emerald-500/30' : 'border-red-500/30'} rounded-xl p-4 transition-all duration-300`}>
          <div className="flex items-center gap-3 mb-3">
            <div className={`w-10 h-10 bg-gradient-to-br ${health?.is_healthy ? getStatusColor(true).bg : getStatusColor(false).bg} rounded-lg flex items-center justify-center`}>
              {health?.is_healthy ? (
                <CheckCircle className="w-5 h-5 text-emerald-400" />
              ) : (
                <AlertTriangle className="w-5 h-5 text-red-400" />
              )}
            </div>
            <div>
              <p className="text-xs text-slate-400">{t('admin:maintenance.overallHealth')}</p>
              <p className={`text-sm font-semibold ${health?.is_healthy ? 'text-emerald-400' : 'text-red-400'}`}>
                {health?.is_healthy ? t('admin:maintenance.healthy') : t('admin:maintenance.issuesDetected')}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* PostgreSQL Pool Details */}
      {health?.database_type === 'postgresql' && health.pool_size !== undefined && (
        <div className="bg-gradient-to-br from-slate-800/40 via-slate-800/30 to-slate-900/20 backdrop-blur-xl border border-slate-700/50 rounded-xl p-4">
          <h4 className="text-sm font-semibold text-white mb-3">{t('admin:maintenance.poolDetails.title')}</h4>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
            <div>
              <p className="text-slate-400 text-xs">{t('admin:maintenance.poolDetails.size')}</p>
              <p className="text-white font-medium">{health.pool_size}</p>
            </div>
            <div>
              <p className="text-slate-400 text-xs">{t('admin:maintenance.poolDetails.checkedIn')}</p>
              <p className="text-emerald-400 font-medium">{health.pool_checked_in ?? t('common:notAvailable')}</p>
            </div>
            <div>
              <p className="text-slate-400 text-xs">{t('admin:maintenance.poolDetails.checkedOut')}</p>
              <p className="text-blue-400 font-medium">{health.pool_checked_out ?? t('common:notAvailable')}</p>
            </div>
            <div>
              <p className="text-slate-400 text-xs">{t('admin:maintenance.poolDetails.overflow')}</p>
              <p className="text-amber-400 font-medium">{health.pool_overflow ?? t('common:notAvailable')}</p>
            </div>
          </div>
        </div>
      )}

      {/* Cleanup Section */}
      <div className="bg-gradient-to-br from-slate-800/40 via-slate-800/30 to-slate-900/20 backdrop-blur-xl border border-slate-700/50 rounded-xl p-4 sm:p-6">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h4 className="text-sm font-semibold text-white mb-1 flex items-center gap-2">
              <Trash2 className="w-4 h-4 text-amber-400" />
              {t('admin:maintenance.cleanup.title')}
            </h4>
            <p className="text-xs text-slate-400 max-w-lg">
              {t('admin:maintenance.cleanup.description')}
            </p>
          </div>

          {!showConfirm ? (
            <button
              onClick={() => setShowConfirm(true)}
              disabled={cleanupLoading}
              className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-amber-500/20 to-amber-600/10 text-amber-300 border border-amber-500/30 hover:from-amber-500/30 hover:to-amber-600/20 transition-all text-sm font-medium"
            >
              <Trash2 className="w-4 h-4" />
              {t('admin:maintenance.cleanup.runCleanup')}
            </button>
          ) : (
            <div className="flex items-center gap-2">
              <button
                onClick={handleCleanup}
                disabled={cleanupLoading}
                className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-red-500 to-red-600 text-white hover:from-red-600 hover:to-red-700 transition-all text-sm font-medium shadow-lg shadow-red-500/30"
              >
                {cleanupLoading ? (
                  <RefreshCw className="w-4 h-4 animate-spin" />
                ) : (
                  <Trash2 className="w-4 h-4" />
                )}
                {t('admin:maintenance.cleanup.confirm')}
              </button>
              <button
                onClick={() => setShowConfirm(false)}
                disabled={cleanupLoading}
                className="px-4 py-2.5 rounded-xl bg-slate-700/40 text-slate-300 hover:bg-slate-700/60 transition-all text-sm font-medium border border-slate-600/50"
              >
                {t('common:cancel')}
              </button>
            </div>
          )}
        </div>

        {cleanupError && (
          <div className="mt-4 bg-gradient-to-r from-red-500/10 to-red-600/5 border border-red-500/30 rounded-lg px-4 py-3">
            <p className="text-red-400 text-sm">{cleanupError}</p>
          </div>
        )}

        {cleanupResult && (
          <div className="mt-4 bg-gradient-to-r from-emerald-500/10 to-emerald-600/5 border border-emerald-500/30 rounded-lg px-4 py-3">
            <p className="text-emerald-400 text-sm font-medium mb-2">{cleanupResult.message}</p>
            {cleanupResult.total > 0 ? (
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3 mt-3">
                {Object.entries(cleanupResult.deleted).map(([metric, count]) => (
                  <div key={metric} className="bg-slate-800/40 rounded-lg px-3 py-2">
                    <p className="text-xs text-slate-400 capitalize">{metric.replace('_', ' ')}</p>
                    <p className="text-sm font-semibold text-white">{count.toLocaleString()}</p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-slate-400">{t('admin:maintenance.cleanup.noSamplesDeleted')}</p>
            )}
            <p className="text-xs text-slate-400 mt-3">
              {t('admin:maintenance.cleanup.totalDeleted', { count: cleanupResult.total, formatted: cleanupResult.total.toLocaleString() })}
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
