import { useState } from 'react';
import { RefreshCw, AlertTriangle, CheckCircle, XCircle, Clock, Play, Square } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { ServiceStatus } from '../../api/service-status';
import { ServiceState, formatUptime, getStateBgColor } from '../../api/service-status';

interface ServiceCardProps {
  service: ServiceStatus;
  onRestart: (serviceName: string) => Promise<void>;
  onStop: (serviceName: string) => Promise<void>;
  onStart: (serviceName: string) => Promise<void>;
}

export default function ServiceCard({ service, onRestart, onStop, onStart }: ServiceCardProps) {
  const { t } = useTranslation(['system', 'common']);
  const [isRestarting, setIsRestarting] = useState(false);
  const [isStopping, setIsStopping] = useState(false);
  const [isStarting, setIsStarting] = useState(false);

  const handleRestart = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!service.restartable || isRestarting || isStopping || isStarting) return;

    setIsRestarting(true);
    try {
      await onRestart(service.name);
    } finally {
      setIsRestarting(false);
    }
  };

  const handleStop = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!service.restartable || isStopping || isRestarting || isStarting) return;

    // Confirmation dialog for destructive action
    const confirmed = window.confirm(
      `${t('system:services.confirm.stopTitle', { name: service.display_name })}\n\n${t('system:services.confirm.stopMessage')}`
    );
    if (!confirmed) return;

    setIsStopping(true);
    try {
      await onStop(service.name);
    } finally {
      setIsStopping(false);
    }
  };

  const handleStart = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!service.restartable || isStarting || isStopping || isRestarting) return;

    setIsStarting(true);
    try {
      await onStart(service.name);
    } finally {
      setIsStarting(false);
    }
  };

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

  // Determine which buttons to show based on service state
  const isAnyOperationInProgress = isRestarting || isStopping || isStarting;
  const canStart = service.state === ServiceState.STOPPED || service.state === ServiceState.ERROR;
  const canStop = service.state === ServiceState.RUNNING;
  const canRestart = service.state === ServiceState.RUNNING || service.state === ServiceState.ERROR;

  return (
    <div className="card border-slate-800/40 hover:border-slate-700/60 transition-all duration-200">
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
        <div className="mb-3">
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
        <div className="mb-3 p-2 bg-yellow-500/10 border border-yellow-500/20 rounded-lg">
          <p className="text-xs text-yellow-400">
            {t('system:services.card.disabledInConfig')}
          </p>
        </div>
      )}

      {/* Control Buttons */}
      {service.restartable && service.config_enabled && (
        <div className="grid grid-cols-3 gap-2 mt-2">
          {/* Start Button */}
          <button
            onClick={handleStart}
            disabled={isAnyOperationInProgress || !canStart}
            className="px-3 py-2 flex items-center justify-center gap-1.5 bg-green-700 hover:bg-green-600 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-green-700"
            title={canStart ? t('system:services.actions.startTooltip') : t('system:services.actions.alreadyRunning')}
          >
            {isStarting ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <Play className="w-4 h-4" />
            )}
            <span className="text-xs sm:text-sm">{t('system:services.actions.start')}</span>
          </button>

          {/* Stop Button */}
          <button
            onClick={handleStop}
            disabled={isAnyOperationInProgress || !canStop}
            className="px-3 py-2 flex items-center justify-center gap-1.5 bg-red-700 hover:bg-red-600 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-red-700"
            title={canStop ? t('system:services.actions.stopTooltip') : t('system:services.actions.notRunning')}
          >
            {isStopping ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <Square className="w-3.5 h-3.5" />
            )}
            <span className="text-xs sm:text-sm">{t('system:services.actions.stop')}</span>
          </button>

          {/* Restart Button */}
          <button
            onClick={handleRestart}
            disabled={isAnyOperationInProgress || !canRestart}
            className="px-3 py-2 flex items-center justify-center gap-1.5 bg-slate-700 hover:bg-slate-600 text-slate-200 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            title={canRestart ? t('system:services.actions.restartTooltip') : t('system:services.actions.mustBeRunning')}
          >
            {isRestarting ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <RefreshCw className="w-4 h-4" />
            )}
            <span className="text-xs sm:text-sm">{t('system:services.actions.restart')}</span>
          </button>
        </div>
      )}
    </div>
  );
}
