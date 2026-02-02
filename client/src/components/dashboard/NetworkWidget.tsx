/**
 * Network Widget for Dashboard
 * Shows current upload/download speeds
 */
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useNetworkStatus, formatNetworkSpeed } from '../../hooks/useNetworkStatus';
import { ArrowDown, ArrowUp, Wifi, WifiOff, Cable } from 'lucide-react';

interface NetworkWidgetProps {
  className?: string;
}

export const NetworkWidget: React.FC<NetworkWidgetProps> = ({ className = '' }) => {
  const { t } = useTranslation(['dashboard', 'common']);
  const navigate = useNavigate();
  const { status, loading, error } = useNetworkStatus({ refreshInterval: 3000 });

  const handleClick = () => navigate('/system?tab=network');

  if (loading) {
    return (
      <div className={`card border-slate-800/40 bg-slate-900/60 ${className}`}>
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-xs uppercase tracking-[0.28em] text-slate-500">{t('dashboard:network.title')}</p>
            <p className="mt-2 text-2xl sm:text-3xl font-semibold text-slate-400">{t('dashboard:network.loading')}</p>
          </div>
          <div className="flex h-11 w-11 sm:h-12 sm:w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-green-500 to-emerald-500 text-white shadow-[0_12px_38px_rgba(16,185,129,0.35)]">
            <Wifi className="h-6 w-6" />
          </div>
        </div>
      </div>
    );
  }

  if (error || !status) {
    return (
      <div className={`card border-slate-800/40 bg-slate-900/60 ${className}`}>
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-xs uppercase tracking-[0.28em] text-slate-500">{t('dashboard:network.title')}</p>
            <p className="mt-2 text-2xl sm:text-3xl font-semibold text-slate-400">{t('dashboard:network.offline')}</p>
          </div>
          <div className="flex h-11 w-11 sm:h-12 sm:w-12 shrink-0 items-center justify-center rounded-2xl bg-slate-800 text-slate-500">
            <WifiOff className="h-6 w-6" />
          </div>
        </div>
        <div className="mt-3 sm:mt-4 flex items-center justify-between gap-2 text-xs text-slate-400">
          <span className="truncate">{t('dashboard:network.monitoringUnavailable')}</span>
        </div>
      </div>
    );
  }

  const { downloadMbps, uploadMbps, interfaceType } = status;

  // Calculate combined speed for progress bar
  const totalMbps = downloadMbps + uploadMbps;
  const maxSpeed = 1000; // 1 Gbps as reference
  const progress = Math.min((totalMbps / maxSpeed) * 100, 100);

  // Determine activity level
  const isIdle = totalMbps < 0.1;
  const isActive = totalMbps > 1;

  // Choose icon based on interface type
  const NetworkIcon = interfaceType === 'ethernet' ? Cable : Wifi;

  return (
    <div
      onClick={handleClick}
      className={`card border-slate-800/40 bg-slate-900/60 transition-all duration-200 hover:border-slate-700/60 hover:bg-slate-900/80 hover:shadow-[0_14px_44px_rgba(16,185,129,0.15)] active:scale-[0.98] touch-manipulation cursor-pointer ${className}`}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-xs uppercase tracking-[0.28em] text-slate-500">{t('dashboard:network.title')}</p>
          <div className="mt-2 flex items-center gap-4">
            {/* Download */}
            <div className="flex items-center gap-1.5">
              <ArrowDown className={`h-4 w-4 ${isActive ? 'text-emerald-400' : 'text-slate-500'}`} />
              <span className="text-lg sm:text-xl font-semibold text-white">
                {formatNetworkSpeed(downloadMbps)}
              </span>
            </div>
            {/* Upload */}
            <div className="flex items-center gap-1.5">
              <ArrowUp className={`h-4 w-4 ${isActive ? 'text-sky-400' : 'text-slate-500'}`} />
              <span className="text-lg sm:text-xl font-semibold text-white">
                {formatNetworkSpeed(uploadMbps)}
              </span>
            </div>
          </div>
        </div>
        <div className={`flex h-11 w-11 sm:h-12 sm:w-12 shrink-0 items-center justify-center rounded-2xl text-white shadow-[0_12px_38px_rgba(16,185,129,0.35)] ${
          isIdle
            ? 'bg-slate-700'
            : 'bg-gradient-to-br from-green-500 to-emerald-500'
        }`}>
          <NetworkIcon className="h-6 w-6" />
        </div>
      </div>

      <div className="mt-3 sm:mt-4 flex flex-col gap-1">
        <div className="flex items-center justify-between gap-2 text-xs text-slate-400">
          <span className="truncate flex-1 min-w-0">
            {isIdle ? t('dashboard:network.idle') : isActive ? t('dashboard:network.active') : t('dashboard:network.lowActivity')}
          </span>
          <span className={`shrink-0 ${isActive ? 'text-emerald-400' : 'text-slate-500'}`}>
            {isIdle ? t('dashboard:network.standby') : t('dashboard:network.live')}
          </span>
        </div>
      </div>

      <div className="mt-4 sm:mt-5 h-2 w-full overflow-hidden rounded-full bg-slate-800">
        <div
          className={`h-full rounded-full transition-all duration-500 ${
            isIdle
              ? 'bg-slate-600'
              : 'bg-gradient-to-r from-green-500 to-emerald-500'
          }`}
          style={{ width: `${Math.max(progress, isIdle ? 0 : 2)}%` }}
        />
      </div>
    </div>
  );
};

export default NetworkWidget;
