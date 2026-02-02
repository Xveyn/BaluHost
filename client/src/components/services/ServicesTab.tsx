import { useState, useEffect, useCallback } from 'react';
import { RefreshCw, Server, AlertTriangle, CheckCircle, StopCircle } from 'lucide-react';
import toast from 'react-hot-toast';
import { useTranslation } from 'react-i18next';
import ServiceCard from './ServiceCard';
import DependencyList from './DependencyList';
import AppMetrics from './AppMetrics';
import {
  getDebugSnapshot,
  restartService,
  stopService,
  startService,
  ServiceState,
  type AdminDebugSnapshot,
} from '../../api/service-status';

interface ServicesTabProps {
  isAdmin: boolean;
}

export default function ServicesTab({ isAdmin }: ServicesTabProps) {
  const { t } = useTranslation(['system', 'common']);
  const [snapshot, setSnapshot] = useState<AdminDebugSnapshot | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

  const fetchData = useCallback(async () => {
    if (!isAdmin) {
      setError(t('system:services.adminRequired'));
      setIsLoading(false);
      return;
    }

    try {
      setError(null);
      const data = await getDebugSnapshot();
      setSnapshot(data);
      setLastRefresh(new Date());
    } catch (err: any) {
      console.error('Failed to fetch service status:', err);
      setError(err.response?.data?.detail || 'Failed to load service status');
    } finally {
      setIsLoading(false);
    }
  }, [isAdmin]);

  useEffect(() => {
    fetchData();

    // Refresh every 10 seconds
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleRefresh = async () => {
    setIsLoading(true);
    await fetchData();
  };

  const handleRestartService = async (serviceName: string) => {
    try {
      const result = await restartService(serviceName);
      if (result.success) {
        toast.success(t('system:services.toast.restartSuccess', { name: serviceName }));
      } else {
        toast.error(result.message || t('system:services.toast.restartFailed', { name: serviceName }));
      }
      // Refresh data after restart
      await fetchData();
    } catch (err: any) {
      console.error('Failed to restart service:', err);
      toast.error(err.response?.data?.detail || t('system:services.toast.restartFailed', { name: serviceName }));
    }
  };

  const handleStopService = async (serviceName: string) => {
    try {
      const result = await stopService(serviceName);
      if (result.success) {
        toast.success(t('system:services.toast.stopSuccess', { name: serviceName }));
      } else {
        toast.error(result.message || t('system:services.toast.stopFailed', { name: serviceName }));
      }
      // Refresh data after stop
      await fetchData();
    } catch (err: any) {
      console.error('Failed to stop service:', err);
      toast.error(err.response?.data?.detail || t('system:services.toast.stopFailed', { name: serviceName }));
    }
  };

  const handleStartService = async (serviceName: string) => {
    try {
      const result = await startService(serviceName);
      if (result.success) {
        toast.success(t('system:services.toast.startSuccess', { name: serviceName }));
      } else {
        toast.error(result.message || t('system:services.toast.startFailed', { name: serviceName }));
      }
      // Refresh data after start
      await fetchData();
    } catch (err: any) {
      console.error('Failed to start service:', err);
      toast.error(err.response?.data?.detail || t('system:services.toast.startFailed', { name: serviceName }));
    }
  };

  if (!isAdmin) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <AlertTriangle className="w-12 h-12 text-yellow-500 mx-auto mb-4" />
          <p className="text-slate-300">{t('system:services.adminRequired')}</p>
        </div>
      </div>
    );
  }

  if (isLoading && !snapshot) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-8 h-8 text-sky-500 animate-spin" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <AlertTriangle className="w-12 h-12 text-red-500 mx-auto mb-4" />
          <p className="text-red-400">{error}</p>
          <button
            onClick={handleRefresh}
            className="mt-4 px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg transition-colors"
          >
            {t('system:services.retry')}
          </button>
        </div>
      </div>
    );
  }

  if (!snapshot) {
    return null;
  }

  // Calculate summary stats
  const runningCount = snapshot.services.filter(s => s.state === ServiceState.RUNNING).length;
  const stoppedCount = snapshot.services.filter(s => s.state === ServiceState.STOPPED).length;
  const errorCount = snapshot.services.filter(s => s.state === ServiceState.ERROR).length;
  const disabledCount = snapshot.services.filter(s => s.state === ServiceState.DISABLED).length;
  const availableDeps = snapshot.dependencies.filter(d => d.available).length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <Server className="w-6 h-6 text-slate-400" />
            {t('system:services.title')}
          </h2>
          {lastRefresh && (
            <p className="text-xs text-slate-400 mt-1">
              {t('system:services.lastUpdated')}: {lastRefresh.toLocaleTimeString()}
            </p>
          )}
        </div>
        <button
          onClick={handleRefresh}
          disabled={isLoading}
          className="px-4 py-2 flex items-center gap-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          {t('system:services.refresh')}
        </button>
      </div>

      {/* Summary Bar */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
        <div className="card border-slate-800/40 flex items-center gap-3">
          <div className="p-2 bg-green-500/20 rounded-lg">
            <CheckCircle className="w-5 h-5 text-green-500" />
          </div>
          <div>
            <p className="text-2xl font-bold text-white">{runningCount}</p>
            <p className="text-xs text-slate-400">{t('system:services.summary.running')}</p>
          </div>
        </div>
        <div className="card border-slate-800/40 flex items-center gap-3">
          <div className="p-2 bg-slate-500/20 rounded-lg">
            <StopCircle className="w-5 h-5 text-slate-400" />
          </div>
          <div>
            <p className="text-2xl font-bold text-white">{stoppedCount}</p>
            <p className="text-xs text-slate-400">{t('system:services.summary.stopped')}</p>
          </div>
        </div>
        <div className="card border-slate-800/40 flex items-center gap-3">
          <div className="p-2 bg-red-500/20 rounded-lg">
            <AlertTriangle className="w-5 h-5 text-red-500" />
          </div>
          <div>
            <p className="text-2xl font-bold text-white">{errorCount}</p>
            <p className="text-xs text-slate-400">{t('system:services.summary.errors')}</p>
          </div>
        </div>
        <div className="card border-slate-800/40 flex items-center gap-3">
          <div className="p-2 bg-yellow-500/20 rounded-lg">
            <Server className="w-5 h-5 text-yellow-500" />
          </div>
          <div>
            <p className="text-2xl font-bold text-white">{disabledCount}</p>
            <p className="text-xs text-slate-400">{t('system:services.summary.disabled')}</p>
          </div>
        </div>
        <div className="card border-slate-800/40 flex items-center gap-3">
          <div className="p-2 bg-sky-500/20 rounded-lg">
            <Server className="w-5 h-5 text-sky-500" />
          </div>
          <div>
            <p className="text-2xl font-bold text-white">{availableDeps}/{snapshot.dependencies.length}</p>
            <p className="text-xs text-slate-400">{t('system:services.summary.dependencies')}</p>
          </div>
        </div>
      </div>

      {/* Services Grid */}
      <div>
        <h3 className="text-lg font-semibold text-white mb-4">{t('system:services.backgroundServices')}</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {snapshot.services.map((service) => (
            <ServiceCard
              key={service.name}
              service={service}
              onRestart={handleRestartService}
              onStop={handleStopService}
              onStart={handleStartService}
            />
          ))}
        </div>
      </div>

      {/* Two Column Layout: Dependencies & Metrics */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Dependencies */}
        <DependencyList dependencies={snapshot.dependencies} />

        {/* App Metrics */}
        <AppMetrics metrics={snapshot.metrics} />
      </div>
    </div>
  );
}
