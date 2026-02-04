/**
 * Plugins Panel for Dashboard
 * Shows plugin status in Quick Stats style
 * Admins can click to navigate to /plugins, non-admins see read-only view
 */
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { usePluginsSummary } from '../../hooks/usePluginsSummary';
import { Plug } from 'lucide-react';

interface PluginsPanelProps {
  isAdmin: boolean;
  className?: string;
}

export const PluginsPanel: React.FC<PluginsPanelProps> = ({ isAdmin, className = '' }) => {
  const { t } = useTranslation(['dashboard', 'common']);
  const navigate = useNavigate();
  const { summary, loading, error } = usePluginsSummary({
    enabled: true,
  });

  const handleClick = () => {
    if (!isAdmin) return;
    navigate('/plugins');
  };

  // Calculate percentage of enabled plugins
  const enabledPercent = summary.total > 0
    ? (summary.enabled / summary.total) * 100
    : 0;

  // Determine status and colors
  const hasErrors = summary.withErrors > 0;
  const noneActive = summary.total > 0 && summary.enabled === 0;
  const someInactive = summary.disabled > 0 && summary.enabled > 0;

  // Color scheme based on status
  const accentGradient = hasErrors
    ? 'from-rose-500 to-red-500'
    : noneActive
    ? 'from-slate-500 to-slate-600'
    : someInactive
    ? 'from-amber-500 to-yellow-500'
    : 'from-violet-500 to-purple-500';

  const shadowColor = hasErrors
    ? 'rgba(244,63,94,0.35)'
    : noneActive
    ? 'rgba(100,116,139,0.35)'
    : someInactive
    ? 'rgba(245,158,11,0.35)'
    : 'rgba(139,92,246,0.35)';

  const hoverShadow = hasErrors
    ? 'hover:shadow-[0_14px_44px_rgba(244,63,94,0.15)]'
    : noneActive
    ? 'hover:shadow-[0_14px_44px_rgba(100,116,139,0.15)]'
    : someInactive
    ? 'hover:shadow-[0_14px_44px_rgba(245,158,11,0.15)]'
    : 'hover:shadow-[0_14px_44px_rgba(139,92,246,0.15)]';

  // Status text
  const getStatusText = () => {
    if (hasErrors) {
      return t('dashboard:plugins.errorsCount', { count: summary.withErrors });
    }
    if (noneActive) {
      return t('dashboard:plugins.noneActive');
    }
    if (someInactive) {
      return t('dashboard:plugins.inactive', { count: summary.disabled });
    }
    return t('dashboard:plugins.allActive');
  };

  const statusTextColor = hasErrors
    ? 'text-rose-400'
    : noneActive
    ? 'text-slate-400'
    : someInactive
    ? 'text-amber-400'
    : 'text-emerald-400';

  if (loading) {
    return (
      <div className={`card border-slate-800/40 bg-slate-900/60 ${className}`}>
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-xs uppercase tracking-[0.28em] text-slate-500">{t('dashboard:plugins.title')}</p>
            <p className="mt-2 text-2xl sm:text-3xl font-semibold text-slate-400">{t('dashboard:plugins.loading')}</p>
          </div>
          <div className="flex h-11 w-11 sm:h-12 sm:w-12 shrink-0 items-center justify-center rounded-2xl bg-slate-800 text-slate-500">
            <Plug className="h-6 w-6" />
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={`card border-rose-500/30 bg-rose-500/10 ${className}`}>
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-xs uppercase tracking-[0.28em] text-slate-500">{t('dashboard:plugins.title')}</p>
            <p className="mt-2 text-2xl sm:text-3xl font-semibold text-rose-300">{t('dashboard:plugins.error')}</p>
          </div>
          <div className="flex h-11 w-11 sm:h-12 sm:w-12 shrink-0 items-center justify-center rounded-2xl bg-rose-500/20 text-rose-400">
            <Plug className="h-6 w-6" />
          </div>
        </div>
        <div className="mt-3 sm:mt-4 text-xs text-rose-300">
          {t('dashboard:plugins.failedToLoad')}
        </div>
      </div>
    );
  }

  if (summary.total === 0) {
    return (
      <div
        className={`card border-slate-800/40 bg-slate-900/60 transition-all duration-200 ${isAdmin ? 'hover:border-slate-700/60 hover:bg-slate-900/80 hover:shadow-[0_14px_44px_rgba(139,92,246,0.15)] active:scale-[0.98] cursor-pointer' : 'cursor-default'} touch-manipulation ${className}`}
        onClick={isAdmin ? handleClick : undefined}
      >
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-xs uppercase tracking-[0.28em] text-slate-500">{t('dashboard:plugins.title')}</p>
            <p className="mt-2 text-2xl sm:text-3xl font-semibold text-slate-400">{t('dashboard:plugins.noPlugins')}</p>
          </div>
          <div className="flex h-11 w-11 sm:h-12 sm:w-12 shrink-0 items-center justify-center rounded-2xl bg-slate-800 text-slate-500">
            <Plug className="h-6 w-6" />
          </div>
        </div>
        {isAdmin && (
          <div className="mt-3 sm:mt-4 text-xs text-slate-500">
            {t('dashboard:plugins.browseAvailable')}
          </div>
        )}
      </div>
    );
  }

  return (
    <div
      className={`card border-slate-800/40 bg-slate-900/60 transition-all duration-200 ${isAdmin ? `hover:border-slate-700/60 hover:bg-slate-900/80 ${hoverShadow} active:scale-[0.98] cursor-pointer` : 'cursor-default'} touch-manipulation ${className}`}
      onClick={isAdmin ? handleClick : undefined}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-xs uppercase tracking-[0.28em] text-slate-500">{t('dashboard:plugins.title')}</p>
          <p className="mt-2 text-2xl sm:text-3xl font-semibold text-white truncate">
            {t('dashboard:plugins.active', { count: summary.enabled })}
          </p>
        </div>
        <div
          className={`flex h-11 w-11 sm:h-12 sm:w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br ${accentGradient} text-white`}
          style={{ boxShadow: `0 12px 38px ${shadowColor}` }}
        >
          <Plug className="h-6 w-6" />
        </div>
      </div>

      <div className="mt-3 sm:mt-4 flex flex-col gap-1">
        <div className="flex items-center justify-between gap-2 text-xs text-slate-400">
          <span className="truncate flex-1 min-w-0">
            {t('dashboard:plugins.ofInstalled', { total: summary.total, count: summary.total })}
          </span>
          <span className={`shrink-0 ${statusTextColor}`}>
            {getStatusText()}
          </span>
        </div>
      </div>

      <div className="mt-4 sm:mt-5 h-2 w-full overflow-hidden rounded-full bg-slate-800">
        <div
          className={`h-full rounded-full bg-gradient-to-r ${accentGradient} transition-all duration-500`}
          style={{ width: `${Math.min(Math.max(enabledPercent, 0), 100)}%` }}
        />
      </div>
    </div>
  );
};

export default PluginsPanel;
