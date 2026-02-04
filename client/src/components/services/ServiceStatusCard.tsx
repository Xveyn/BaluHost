import { AlertTriangle, CheckCircle, XCircle, Clock } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { ServiceStatus } from '../../api/service-status';
import { ServiceState, formatUptime, getStateBgColor } from '../../api/service-status';

interface ServiceStatusCardProps {
  service: ServiceStatus;
}

/**
 * Read-only service status card without control buttons.
 * Used in SystemMonitor for non-admin view of service status.
 */
export default function ServiceStatusCard({ service }: ServiceStatusCardProps) {
  const { t } = useTranslation(['system', 'common']);

  const getStateIcon = () => {
    switch (service.state) {
      case ServiceState.RUNNING:
        return <CheckCircle className="w-5 h-5 text-green-500" />;
      case ServiceState.STOPPED:
        return <XCircle className="w-5 h-5 text-gray-500" />;
      case ServiceState.ERROR:
        return <AlertTriangle className="w-5 h-5 text-red-500" />;
      case ServiceState.DISABLED:
        return <XCircle className="w-5 h-5 text-yellow-500" />;
      default:
        return <Clock className="w-5 h-5 text-gray-500" />;
    }
  };

  return (
    <div className="card border-slate-800/40">
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          {getStateIcon()}
          <div>
            <h3 className="font-semibold text-white">{service.display_name}</h3>
            <p className="text-xs text-slate-400">{service.name}</p>
          </div>
        </div>
        <span className={`px-2 py-1 rounded-full text-xs font-medium ${getStateBgColor(service.state)}`}>
          {service.state.toUpperCase()}
        </span>
      </div>

      {/* Metrics Grid */}
      <div className="grid grid-cols-2 gap-3 mb-3">
        <div>
          <p className="text-xs text-slate-400">{t('system:services.card.uptime')}</p>
          <p className="text-sm font-medium text-white">
            {formatUptime(service.uptime_seconds)}
          </p>
        </div>
        <div>
          <p className="text-xs text-slate-400">{t('system:services.card.samples')}</p>
          <p className="text-sm font-medium text-white">
            {service.sample_count?.toLocaleString() ?? '-'}
          </p>
        </div>
      </div>

      {/* Error Info */}
      {service.error_count > 0 && (
        <div className="mb-3 p-2 bg-red-500/10 border border-red-500/20 rounded-lg">
          <div className="flex items-center gap-2 text-red-400 text-sm">
            <AlertTriangle className="w-4 h-4" />
            <span>{t('system:services.card.errors', { count: service.error_count })}</span>
          </div>
          {service.last_error && (
            <p className="text-xs text-red-300 mt-1 truncate" title={service.last_error}>
              {service.last_error}
            </p>
          )}
        </div>
      )}

      {/* Interval */}
      {service.interval_seconds && (
        <div>
          <p className="text-xs text-slate-400">{t('system:services.card.interval')}</p>
          <p className="text-sm font-medium text-white">
            {service.interval_seconds >= 60
              ? `${Math.round(service.interval_seconds / 60)}m`
              : `${service.interval_seconds}s`}
          </p>
        </div>
      )}

      {/* Config Disabled Warning */}
      {!service.config_enabled && (
        <div className="mt-3 p-2 bg-yellow-500/10 border border-yellow-500/20 rounded-lg">
          <p className="text-xs text-yellow-400">
            {t('system:services.card.disabledInConfig')}
          </p>
        </div>
      )}
    </div>
  );
}
