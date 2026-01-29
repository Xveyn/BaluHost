import { useState, useCallback } from 'react';
import { Calendar, Clock, History, Settings, Wrench, RefreshCw, Loader2, BarChart3 } from 'lucide-react';
import { useSchedulers, useSchedulerHistory } from '../hooks/useSchedulers';
import { SchedulerCard } from '../components/scheduler/SchedulerCard';
import { SchedulerConfigModal } from '../components/scheduler/SchedulerConfigModal';
import { ExecutionHistoryTable } from '../components/scheduler/ExecutionHistoryTable';
import { MaintenancePanel } from '../components/scheduler/MaintenancePanel';
import { SchedulerTimeline } from '../components/scheduler/SchedulerTimeline';
import type { SchedulerStatus, SchedulerConfigUpdate, SchedulerExecStatus } from '../api/schedulers';
import { retryExecution } from '../api/schedulers';
import { toast } from 'react-hot-toast';

type TabId = 'overview' | 'timeline' | 'sync' | 'maintenance' | 'history';

interface Tab {
  id: TabId;
  label: string;
  icon: React.ReactNode;
}

const tabs: Tab[] = [
  { id: 'overview', label: 'Overview', icon: <Clock className="h-4 w-4" /> },
  { id: 'timeline', label: 'Timeline', icon: <BarChart3 className="h-4 w-4" /> },
  { id: 'sync', label: 'Sync Schedules', icon: <Calendar className="h-4 w-4" /> },
  { id: 'maintenance', label: 'Maintenance', icon: <Wrench className="h-4 w-4" /> },
  { id: 'history', label: 'History', icon: <History className="h-4 w-4" /> },
];

export default function SchedulerDashboard() {
  const [activeTab, setActiveTab] = useState<TabId>('overview');
  const [configModalOpen, setConfigModalOpen] = useState(false);
  const [selectedScheduler, setSelectedScheduler] = useState<SchedulerStatus | null>(null);

  // Schedulers hook
  const {
    schedulers,
    totalRunning,
    totalEnabled,
    loading: schedulersLoading,
    error: schedulersError,
    refetch: refetchSchedulers,
    runNow,
    toggle,
    updateConfig,
  } = useSchedulers({ refreshInterval: 30000 });

  // History hook - fetch when history or timeline tab is active
  const [historyPage, setHistoryPage] = useState(1);
  const [historyStatusFilter, setHistoryStatusFilter] = useState<SchedulerExecStatus | undefined>();
  const {
    history,
    loading: historyLoading,
    error: historyError,
    refetch: refetchHistory,
  } = useSchedulerHistory({
    page: historyPage,
    pageSize: 50, // Larger for timeline view
    statusFilter: historyStatusFilter,
    enabled: activeTab === 'history' || activeTab === 'timeline',
  });

  // Toast wrapper for MaintenancePanel
  const addToast = useCallback((message: string, type: 'success' | 'error' | 'info') => {
    switch (type) {
      case 'success':
        toast.success(message);
        break;
      case 'error':
        toast.error(message);
        break;
      default:
        toast(message);
    }
  }, []);

  // Handlers
  const handleRunNow = async (name: string) => {
    try {
      const result = await runNow(name);
      if (result.success) {
        toast.success(result.message);
      } else {
        toast.error(result.message);
      }
    } catch (err: any) {
      toast.error(err.message || 'Failed to run scheduler');
    }
  };

  const handleConfigure = (scheduler: SchedulerStatus) => {
    setSelectedScheduler(scheduler);
    setConfigModalOpen(true);
  };

  const handleToggle = async (name: string, enabled: boolean) => {
    try {
      const result = await toggle(name, enabled);
      if (result.success) {
        toast.success(result.message);
      } else {
        toast.error(result.message);
      }
    } catch (err: any) {
      toast.error(err.message || 'Failed to toggle scheduler');
    }
  };

  const handleSaveConfig = async (name: string, config: SchedulerConfigUpdate): Promise<boolean> => {
    try {
      const success = await updateConfig(name, config);
      if (success) {
        toast.success('Configuration saved');
        return true;
      }
      return false;
    } catch (err: any) {
      toast.error(err.message || 'Failed to save configuration');
      return false;
    }
  };

  const handleRetry = async (schedulerName: string) => {
    try {
      const result = await retryExecution(schedulerName);
      if (result.success) {
        toast.success(`${schedulerName.replace(/_/g, ' ')} retried successfully`);
        refetchHistory();
      } else {
        toast.error(result.message || 'Retry failed');
      }
    } catch (err: any) {
      toast.error(err.message || 'Failed to retry scheduler');
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-semibold text-white">Scheduler Dashboard</h1>
          <p className="text-sm text-slate-400 mt-1">
            Manage system schedulers and view execution history
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* Stats badges */}
          <div className="flex items-center gap-2 text-sm">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-green-900/50 px-3 py-1 text-green-300">
              <span className="h-2 w-2 rounded-full bg-green-400 animate-pulse" />
              {totalRunning} Running
            </span>
            <span className="inline-flex items-center rounded-full bg-slate-800 px-3 py-1 text-slate-300">
              {totalEnabled} Enabled
            </span>
          </div>
          <button
            onClick={refetchSchedulers}
            disabled={schedulersLoading}
            className="inline-flex items-center gap-1.5 rounded-md bg-slate-800 px-3 py-2 text-sm text-slate-300 hover:bg-slate-700 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${schedulersLoading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-slate-800">
        <nav className="flex gap-1 -mb-px overflow-x-auto" aria-label="Tabs">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`inline-flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
                activeTab === tab.id
                  ? 'border-sky-500 text-sky-400'
                  : 'border-transparent text-slate-400 hover:text-slate-300 hover:border-slate-700'
              }`}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab content */}
      <div className="min-h-[400px]">
        {/* Overview Tab */}
        {activeTab === 'overview' && (
          <div>
            {schedulersError && (
              <div className="mb-4 rounded-lg bg-red-900/20 border border-red-800 px-4 py-3">
                <p className="text-sm text-red-400">{schedulersError}</p>
              </div>
            )}

            {schedulersLoading && schedulers.length === 0 ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                {schedulers.map((scheduler) => (
                  <SchedulerCard
                    key={scheduler.name}
                    scheduler={scheduler}
                    onRunNow={handleRunNow}
                    onConfigure={handleConfigure}
                    onToggle={handleToggle}
                  />
                ))}
              </div>
            )}
          </div>
        )}

        {/* Timeline Tab */}
        {activeTab === 'timeline' && (
          <SchedulerTimeline
            executions={history?.executions || []}
            loading={historyLoading}
          />
        )}

        {/* Sync Schedules Tab */}
        {activeTab === 'sync' && (
          <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-6">
            <div className="flex items-center gap-3 mb-4">
              <Calendar className="h-6 w-6 text-sky-400" />
              <h2 className="text-lg font-medium text-white">Sync Schedules</h2>
            </div>
            <p className="text-sm text-slate-400 mb-6">
              User-defined sync schedules can be configured in the Settings page under the Sync tab.
              This section will be enhanced with direct schedule management in a future update.
            </p>
            <a
              href="/settings"
              className="inline-flex items-center gap-2 rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-700 transition-colors"
            >
              <Settings className="h-4 w-4" />
              Go to Settings
            </a>
          </div>
        )}

        {/* Maintenance Tab */}
        {activeTab === 'maintenance' && (
          <MaintenancePanel addToast={addToast} />
        )}

        {/* History Tab */}
        {activeTab === 'history' && (
          <ExecutionHistoryTable
            history={history}
            loading={historyLoading}
            error={historyError}
            onPageChange={setHistoryPage}
            onStatusFilterChange={setHistoryStatusFilter}
            onRefresh={refetchHistory}
            onRetry={handleRetry}
            statusFilter={historyStatusFilter}
          />
        )}
      </div>

      {/* Config Modal */}
      <SchedulerConfigModal
        scheduler={selectedScheduler}
        isOpen={configModalOpen}
        onClose={() => {
          setConfigModalOpen(false);
          setSelectedScheduler(null);
        }}
        onSave={handleSaveConfig}
      />
    </div>
  );
}
