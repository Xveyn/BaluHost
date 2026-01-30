/**
 * Alert Banner for Dashboard
 * Shows critical warnings at the top of the dashboard
 */
import React, { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle,
  AlertCircle,
  XCircle,
  ChevronDown,
  ChevronUp,
  HardDrive,
  Server,
  Clock,
  X,
} from 'lucide-react';

export interface Alert {
  id: string;
  type: 'critical' | 'warning' | 'info';
  title: string;
  message: string;
  link?: string;
  linkText?: string;
  source: 'smart' | 'raid' | 'scheduler' | 'service';
}

interface AlertBannerProps {
  alerts: Alert[];
  onDismiss?: (id: string) => void;
}

export const AlertBanner: React.FC<AlertBannerProps> = ({ alerts, onDismiss }) => {
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState(false);
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());

  const visibleAlerts = useMemo(() => {
    return alerts.filter((a) => !dismissed.has(a.id));
  }, [alerts, dismissed]);

  const handleDismiss = (id: string) => {
    setDismissed((prev) => new Set([...prev, id]));
    onDismiss?.(id);
  };

  const handleNavigate = (link: string) => {
    navigate(link);
  };

  if (visibleAlerts.length === 0) {
    return null;
  }

  const criticalCount = visibleAlerts.filter((a) => a.type === 'critical').length;
  const warningCount = visibleAlerts.filter((a) => a.type === 'warning').length;

  // Get icon for alert source
  const getSourceIcon = (source: Alert['source']) => {
    switch (source) {
      case 'smart':
        return <HardDrive className="h-4 w-4" />;
      case 'raid':
        return <Server className="h-4 w-4" />;
      case 'scheduler':
        return <Clock className="h-4 w-4" />;
      case 'service':
        return <Server className="h-4 w-4" />;
      default:
        return <AlertCircle className="h-4 w-4" />;
    }
  };

  // Get type-based styling
  const getTypeStyles = (type: Alert['type']) => {
    switch (type) {
      case 'critical':
        return {
          bg: 'bg-rose-500/20',
          border: 'border-rose-500/40',
          text: 'text-rose-200',
          icon: <XCircle className="h-4 w-4 text-rose-400" />,
        };
      case 'warning':
        return {
          bg: 'bg-amber-500/20',
          border: 'border-amber-500/40',
          text: 'text-amber-200',
          icon: <AlertTriangle className="h-4 w-4 text-amber-400" />,
        };
      default:
        return {
          bg: 'bg-sky-500/20',
          border: 'border-sky-500/40',
          text: 'text-sky-200',
          icon: <AlertCircle className="h-4 w-4 text-sky-400" />,
        };
    }
  };

  const primaryAlert = visibleAlerts[0];
  const primaryStyles = getTypeStyles(primaryAlert.type);

  return (
    <div
      className={`rounded-xl border ${primaryStyles.border} ${primaryStyles.bg} overflow-hidden`}
    >
      {/* Header / collapsed view */}
      <div
        className="flex items-center justify-between px-4 py-3 cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-3">
          {primaryStyles.icon}
          <div>
            <p className={`text-sm font-medium ${primaryStyles.text}`}>
              {visibleAlerts.length === 1
                ? primaryAlert.title
                : `${visibleAlerts.length} System Alerts`}
            </p>
            {visibleAlerts.length === 1 && (
              <p className="text-xs text-slate-400 mt-0.5">{primaryAlert.message}</p>
            )}
            {visibleAlerts.length > 1 && (
              <p className="text-xs text-slate-400 mt-0.5">
                {criticalCount > 0 && `${criticalCount} critical`}
                {criticalCount > 0 && warningCount > 0 && ', '}
                {warningCount > 0 && `${warningCount} warning${warningCount > 1 ? 's' : ''}`}
              </p>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          {visibleAlerts.length === 1 && primaryAlert.link && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                handleNavigate(primaryAlert.link!);
              }}
              className="rounded-full border border-slate-700/70 px-3 py-1 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white"
            >
              {primaryAlert.linkText || 'View'}
            </button>
          )}

          {visibleAlerts.length > 1 && (
            <button className="flex items-center gap-1 text-xs text-slate-400 hover:text-white">
              {expanded ? (
                <>
                  <span>Collapse</span>
                  <ChevronUp className="h-4 w-4" />
                </>
              ) : (
                <>
                  <span>Expand</span>
                  <ChevronDown className="h-4 w-4" />
                </>
              )}
            </button>
          )}

          {visibleAlerts.length === 1 && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                handleDismiss(primaryAlert.id);
              }}
              className="p-1 text-slate-400 hover:text-white transition"
              title="Dismiss"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>

      {/* Expanded list */}
      {expanded && visibleAlerts.length > 1 && (
        <div className="border-t border-slate-800/50 px-4 py-2 space-y-2">
          {visibleAlerts.map((alert) => {
            const styles = getTypeStyles(alert.type);
            return (
              <div
                key={alert.id}
                className={`flex items-center justify-between rounded-lg ${styles.bg} px-3 py-2`}
              >
                <div className="flex items-center gap-3">
                  {getSourceIcon(alert.source)}
                  <div>
                    <p className={`text-sm font-medium ${styles.text}`}>{alert.title}</p>
                    <p className="text-xs text-slate-400">{alert.message}</p>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  {alert.link && (
                    <button
                      onClick={() => handleNavigate(alert.link!)}
                      className="rounded-full border border-slate-700/70 px-2 py-0.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white"
                    >
                      {alert.linkText || 'View'}
                    </button>
                  )}
                  <button
                    onClick={() => handleDismiss(alert.id)}
                    className="p-1 text-slate-400 hover:text-white transition"
                    title="Dismiss"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default AlertBanner;
