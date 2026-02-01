/**
 * Services Panel for Dashboard (Admin Only)
 * Shows backend services status in Quick Stats style
 */
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useServicesSummary } from '../../hooks/useServicesSummary';
import { Server } from 'lucide-react';

interface ServicesPanelProps {
  isAdmin: boolean;
  className?: string;
}

export const ServicesPanel: React.FC<ServicesPanelProps> = ({ isAdmin, className = '' }) => {
  const navigate = useNavigate();
  const { summary, loading, error } = useServicesSummary({
    enabled: isAdmin,
  });

  // Don't render for non-admins
  if (!isAdmin) {
    return null;
  }

  const handleClick = () => {
    navigate('/health');
  };

  // Calculate percentage of running services
  const runningPercent = summary.total > 0
    ? (summary.running / summary.total) * 100
    : 0;

  // Determine status and colors
  const hasErrors = summary.error > 0;
  const hasStopped = summary.stopped > 0;

  // Color scheme based on status
  const accentGradient = hasErrors
    ? 'from-rose-500 to-red-500'
    : hasStopped
    ? 'from-amber-500 to-yellow-500'
    : 'from-emerald-500 to-teal-500';

  const shadowColor = hasErrors
    ? 'rgba(244,63,94,0.35)'
    : hasStopped
    ? 'rgba(245,158,11,0.35)'
    : 'rgba(16,185,129,0.35)';

  const hoverShadow = hasErrors
    ? 'hover:shadow-[0_14px_44px_rgba(244,63,94,0.15)]'
    : hasStopped
    ? 'hover:shadow-[0_14px_44px_rgba(245,158,11,0.15)]'
    : 'hover:shadow-[0_14px_44px_rgba(16,185,129,0.15)]';

  // Status text
  const getStatusText = () => {
    if (hasErrors) {
      return `${summary.error} error${summary.error > 1 ? 's' : ''}`;
    }
    if (hasStopped) {
      return `${summary.stopped} stopped`;
    }
    return 'All healthy';
  };

  const statusTextColor = hasErrors
    ? 'text-rose-400'
    : hasStopped
    ? 'text-amber-400'
    : 'text-emerald-400';

  if (loading) {
    return (
      <div className={`card border-slate-800/40 bg-slate-900/60 ${className}`}>
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-xs uppercase tracking-[0.28em] text-slate-500">Services</p>
            <p className="mt-2 text-2xl sm:text-3xl font-semibold text-slate-400">Loading...</p>
          </div>
          <div className="flex h-11 w-11 sm:h-12 sm:w-12 shrink-0 items-center justify-center rounded-2xl bg-slate-800 text-slate-500">
            <Server className="h-6 w-6" />
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
            <p className="text-xs uppercase tracking-[0.28em] text-slate-500">Services</p>
            <p className="mt-2 text-2xl sm:text-3xl font-semibold text-rose-300">Error</p>
          </div>
          <div className="flex h-11 w-11 sm:h-12 sm:w-12 shrink-0 items-center justify-center rounded-2xl bg-rose-500/20 text-rose-400">
            <Server className="h-6 w-6" />
          </div>
        </div>
        <div className="mt-3 sm:mt-4 text-xs text-rose-300">
          Failed to load service status
        </div>
      </div>
    );
  }

  if (summary.total === 0) {
    return null;
  }

  return (
    <div
      className={`card border-slate-800/40 bg-slate-900/60 transition-all duration-200 hover:border-slate-700/60 hover:bg-slate-900/80 ${hoverShadow} active:scale-[0.98] touch-manipulation cursor-pointer ${className}`}
      onClick={handleClick}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-xs uppercase tracking-[0.28em] text-slate-500">Services</p>
          <p className="mt-2 text-2xl sm:text-3xl font-semibold text-white truncate">
            {summary.running} Running
          </p>
        </div>
        <div
          className={`flex h-11 w-11 sm:h-12 sm:w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br ${accentGradient} text-white`}
          style={{ boxShadow: `0 12px 38px ${shadowColor}` }}
        >
          <Server className="h-6 w-6" />
        </div>
      </div>

      <div className="mt-3 sm:mt-4 flex flex-col gap-1">
        <div className="flex items-center justify-between gap-2 text-xs text-slate-400">
          <span className="truncate flex-1 min-w-0">
            of {summary.total} backend services
          </span>
          <span className={`shrink-0 ${statusTextColor}`}>
            {getStatusText()}
          </span>
        </div>
      </div>

      <div className="mt-4 sm:mt-5 h-2 w-full overflow-hidden rounded-full bg-slate-800">
        <div
          className={`h-full rounded-full bg-gradient-to-r ${accentGradient} transition-all duration-500`}
          style={{ width: `${Math.min(Math.max(runningPercent, 0), 100)}%` }}
        />
      </div>
    </div>
  );
};

export default ServicesPanel;
