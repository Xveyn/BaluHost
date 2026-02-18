/**
 * Connected Devices Widget for Dashboard
 * Shows mobile and desktop device counts
 */
import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { getAllDevices, type Device } from '../../api/devices';
import { Smartphone, Monitor, Wifi, WifiOff } from 'lucide-react';

interface DeviceSummary {
  mobile: number;
  desktop: number;
  total: number;
  activeRecently: number;
}

interface ConnectedDevicesWidgetProps {
  className?: string;
}

export const ConnectedDevicesWidget: React.FC<ConnectedDevicesWidgetProps> = ({ className = '' }) => {
  const { t } = useTranslation(['dashboard', 'common']);
  const navigate = useNavigate();
  const [devices, setDevices] = useState<Device[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      const response = await getAllDevices();
      setDevices(response);
      setError(null);
    } catch (err: unknown) {
      // Don't show error for 403 (user may not have permission)
      const msg = err instanceof Error ? err.message : '';
      if (msg.includes('403') || msg.includes('Forbidden')) {
        setDevices([]);
        setError(null);
        return;
      }
      setError(msg || 'Failed to load devices');
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    loadData().finally(() => setLoading(false));

    // Refresh every 60 seconds
    const interval = setInterval(loadData, 60000);
    return () => clearInterval(interval);
  }, [loadData]);

  const handleViewDevices = () => {
    navigate('/sync-prototype');
  };

  // Calculate summary
  const summary: DeviceSummary = React.useMemo(() => {
    const now = new Date();
    const recentThreshold = 5 * 60 * 1000; // 5 minutes

    const activeDevices = devices.filter((d) => {
      if (!d.last_seen) return false;
      const lastSeen = new Date(d.last_seen);
      return now.getTime() - lastSeen.getTime() < recentThreshold;
    });

    return {
      mobile: devices.filter((d) => d.type === 'mobile').length,
      desktop: devices.filter((d) => d.type === 'desktop').length,
      total: devices.length,
      activeRecently: activeDevices.length,
    };
  }, [devices]);

  if (loading) {
    return (
      <div className={`rounded-xl border border-slate-800/50 bg-slate-900/55 p-4 ${className}`}>
        <p className="text-xs uppercase tracking-[0.28em] text-slate-500">{t('dashboard:devices.title')}</p>
        <div className="mt-3 flex items-center gap-4">
          <div className="h-6 w-16 rounded bg-slate-800 animate-pulse" />
          <div className="h-6 w-16 rounded bg-slate-800 animate-pulse" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={`rounded-xl border border-slate-800/50 bg-slate-900/55 p-4 ${className}`}>
        <p className="text-xs uppercase tracking-[0.28em] text-slate-500">{t('dashboard:devices.title')}</p>
        <div className="mt-3 flex items-center gap-2 text-sm text-slate-500">
          <WifiOff className="h-4 w-4" />
          <span>{t('dashboard:devices.unableToLoad')}</span>
        </div>
      </div>
    );
  }

  if (summary.total === 0) {
    return (
      <div
        className={`rounded-xl border border-slate-800/50 bg-slate-900/55 p-4 cursor-pointer transition hover:border-slate-700/60 hover:bg-slate-900/70 ${className}`}
        onClick={handleViewDevices}
      >
        <p className="text-xs uppercase tracking-[0.28em] text-slate-500">{t('dashboard:devices.title')}</p>
        <div className="mt-3 flex items-center gap-2 text-sm text-slate-500">
          <Wifi className="h-4 w-4" />
          <span>{t('dashboard:devices.noDevicesRegistered')}</span>
        </div>
        <p className="mt-2 text-xs text-slate-600">{t('dashboard:devices.clickToAddDevice')}</p>
      </div>
    );
  }

  return (
    <div
      className={`rounded-xl border border-slate-800/50 bg-slate-900/55 p-4 cursor-pointer transition hover:border-slate-700/60 hover:bg-slate-900/70 ${className}`}
      onClick={handleViewDevices}
    >
      <div className="flex items-center justify-between">
        <p className="text-xs uppercase tracking-[0.28em] text-slate-500">{t('dashboard:devices.title')}</p>
        {summary.activeRecently > 0 && (
          <div className="flex items-center gap-1">
            <span className="inline-flex h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-xs text-emerald-400">{t('dashboard:devices.online', { count: summary.activeRecently })}</span>
          </div>
        )}
      </div>

      <div className="mt-3 flex items-center gap-4">
        {/* Mobile count */}
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-violet-500/20">
            <Smartphone className="h-4 w-4 text-violet-400" />
          </div>
          <div>
            <p className="text-lg font-semibold text-white">{summary.mobile}</p>
            <p className="text-xs text-slate-500">{t('dashboard:devices.mobile')}</p>
          </div>
        </div>

        {/* Desktop count */}
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-sky-500/20">
            <Monitor className="h-4 w-4 text-sky-400" />
          </div>
          <div>
            <p className="text-lg font-semibold text-white">{summary.desktop}</p>
            <p className="text-xs text-slate-500">{t('dashboard:devices.desktop')}</p>
          </div>
        </div>
      </div>

      <p className="mt-3 text-xs text-slate-600">{t('dashboard:devices.clickToManage')}</p>
    </div>
  );
};

export default ConnectedDevicesWidget;
