import { RefreshCw, Server, AlertTriangle, CheckCircle, StopCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import ServiceCard from './ServiceCard';
import DependencyList from './DependencyList';
import AppMetrics from './AppMetrics';
import { ServiceState } from '../../api/service-status';
import { useDebugSnapshot, useServiceControls } from '../../hooks/useServiceStatus';

interface ServicesTabProps {
  isAdmin: boolean;
}

export default function ServicesTab({ isAdmin }: ServicesTabProps) {
  const { t } = useTranslation(['system', 'common']);
  // Query-backed (#299): shares the `services.debugSnapshot()` cache/poll with
  // the read-only ServicesStatusTab (fetch gated on admin). Control actions are
  // `useMutation`s that invalidate the `services` domain on settle.
  const { snapshot, isLoading, isFetching, error, lastUpdated: lastRefresh, refetch } =
    useDebugSnapshot({ enabled: isAdmin });
  const { restart: handleRestartService, stop: handleStopService, start: handleStartService } =
    useServiceControls();

  const handleRefresh = () => {
    void refetch();
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
    <div className="space-y-6 min-w-0">
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
          disabled={isFetching}
          className="px-4 py-2 flex items-center gap-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${isFetching ? 'animate-spin' : ''}`} />
          {t('system:services.refresh')}
        </button>
      </div>

      {/* Summary Bar */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-2 sm:gap-4">
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
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4">
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
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6">
        {/* Dependencies */}
        <DependencyList dependencies={snapshot.dependencies} />

        {/* App Metrics */}
        <AppMetrics metrics={snapshot.metrics} />
      </div>
    </div>
  );
}
