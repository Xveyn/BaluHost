/**
 * Service Summary Widget for Dashboard (Admin Only)
 * Shows compact service health overview
 */
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useServicesSummary } from '../../hooks/useServicesSummary';
import { Server, CheckCircle2, XCircle, AlertCircle, MinusCircle } from 'lucide-react';

interface ServiceSummaryWidgetProps {
  isAdmin: boolean;
}

export const ServiceSummaryWidget: React.FC<ServiceSummaryWidgetProps> = ({ isAdmin }) => {
  const { t } = useTranslation(['dashboard', 'common']);
  const navigate = useNavigate();
  const { summary, services, loading, error } = useServicesSummary({
    enabled: isAdmin,
  });

  // Don't render for non-admins
  if (!isAdmin) {
    return null;
  }

  const handleViewHealth = () => {
    navigate('/health');
  };

  if (loading) {
    return (
      <div className="rounded-xl border border-slate-800/50 bg-slate-900/55 px-4 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Server className="h-4 w-4 text-slate-500" />
            <span className="text-sm text-slate-400">{t('dashboard:services.loadingServices')}</span>
          </div>
          <div className="h-5 w-32 rounded bg-slate-800 animate-pulse" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <AlertCircle className="h-4 w-4 text-rose-400" />
            <span className="text-sm text-rose-300">{t('dashboard:services.failedToLoad')}</span>
          </div>
        </div>
      </div>
    );
  }

  if (summary.total === 0) {
    return null;
  }

  const hasErrors = summary.error > 0;
  const hasStopped = summary.stopped > 0;

  return (
    <div
      className={`rounded-xl border px-4 py-3 transition cursor-pointer hover:bg-slate-900/70 ${
        hasErrors
          ? 'border-rose-500/30 bg-rose-500/10'
          : hasStopped
          ? 'border-amber-500/30 bg-amber-500/10'
          : 'border-slate-800/50 bg-slate-900/55'
      }`}
      onClick={handleViewHealth}
    >
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Server className={`h-4 w-4 ${hasErrors ? 'text-rose-400' : 'text-slate-400'}`} />
          <span className="text-sm text-slate-300">{t('dashboard:services.backendServices')}</span>
        </div>

        <div className="flex items-center gap-3">
          {summary.running > 0 && (
            <div className="flex items-center gap-1.5" title={`${summary.running} running`}>
              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
              <span className="text-xs text-emerald-300">{summary.running}</span>
            </div>
          )}

          {summary.stopped > 0 && (
            <div className="flex items-center gap-1.5" title={`${summary.stopped} stopped`}>
              <MinusCircle className="h-3.5 w-3.5 text-slate-400" />
              <span className="text-xs text-slate-400">{summary.stopped}</span>
            </div>
          )}

          {summary.error > 0 && (
            <div className="flex items-center gap-1.5" title={`${summary.error} with errors`}>
              <XCircle className="h-3.5 w-3.5 text-rose-400" />
              <span className="text-xs text-rose-300">{summary.error}</span>
            </div>
          )}

          {summary.disabled > 0 && (
            <div className="flex items-center gap-1.5" title={`${summary.disabled} disabled`}>
              <span className="text-xs text-slate-500">{summary.disabled} off</span>
            </div>
          )}

          <span className="text-xs text-slate-600">|</span>
          <span className="text-xs text-slate-400">{summary.total} total</span>
        </div>
      </div>

      {/* Show error details if any */}
      {hasErrors && services.filter(s => s.state === 'error').length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {services
            .filter(s => s.state === 'error')
            .slice(0, 3)
            .map((s) => (
              <span
                key={s.name}
                className="inline-flex items-center gap-1 rounded-full bg-rose-500/20 px-2 py-0.5 text-xs text-rose-300"
              >
                {s.display_name}
              </span>
            ))}
          {services.filter(s => s.state === 'error').length > 3 && (
            <span className="text-xs text-rose-400">
              +{services.filter(s => s.state === 'error').length - 3} more
            </span>
          )}
        </div>
      )}
    </div>
  );
};

export default ServiceSummaryWidget;
