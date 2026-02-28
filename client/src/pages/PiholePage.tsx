import { useState, useEffect, useCallback } from 'react';
import toast from 'react-hot-toast';
import {
  getPiholeStatus,
  getPiholeSummary,
  setBlocking,
  getTopDomains,
  getTopBlocked,
  getTopClients,
  getHistory,
  type PiholeStatus,
  type PiholeSummary,
  type DomainEntry,
  type ClientEntry,
  type HistoryEntry,
} from '../api/pihole';
import PiholeStatusBar from '../components/pihole/PiholeStatusBar';
import PiholeSummaryCards from '../components/pihole/PiholeSummaryCards';
import PiholeQueryTimeline from '../components/pihole/PiholeQueryTimeline';
import PiholeQueryLog from '../components/pihole/PiholeQueryLog';
import TopDomainsPanel from '../components/pihole/TopDomainsPanel';
import TopClientsPanel from '../components/pihole/TopClientsPanel';
import PiholeDomainManagement from '../components/pihole/PiholeDomainManagement';
import PiholeAdlistManagement from '../components/pihole/PiholeAdlistManagement';
import PiholeLocalDns from '../components/pihole/PiholeLocalDns';
import PiholeSettings from '../components/pihole/PiholeSettings';
import PiholeContainerActions from '../components/pihole/PiholeContainerActions';
import { AlertTriangle, WifiOff } from 'lucide-react';

type Tab = 'overview' | 'queries' | 'domains' | 'adlists' | 'dns' | 'settings' | 'container';

const TABS: { key: Tab; label: string }[] = [
  { key: 'overview', label: 'Overview' },
  { key: 'queries', label: 'Query Log' },
  { key: 'domains', label: 'Domains' },
  { key: 'adlists', label: 'Adlists' },
  { key: 'dns', label: 'Local DNS' },
  { key: 'settings', label: 'Settings' },
  { key: 'container', label: 'Container' },
];

export default function PiholePage() {
  const [activeTab, setActiveTab] = useState<Tab>('overview');
  const [status, setStatus] = useState<PiholeStatus | null>(null);
  const [summary, setSummary] = useState<PiholeSummary | null>(null);
  const [topPermitted, setTopPermitted] = useState<DomainEntry[]>([]);
  const [topBlocked, setTopBlocked] = useState<DomainEntry[]>([]);
  const [topClients, setTopClients] = useState<ClientEntry[]>([]);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState(false);

  const fetchOverview = useCallback(async () => {
    setLoading(true);
    try {
      // Fetch status first — if it fails with 503, show error state
      const statusData = await getPiholeStatus();
      setStatus(statusData);
      setFetchError(false);

      // If connected, fetch the rest of the overview data
      if (statusData.connected) {
        try {
          const [summaryData, domainsData, blockedData, clientsData, historyData] = await Promise.all([
            getPiholeSummary(),
            getTopDomains(10),
            getTopBlocked(10),
            getTopClients(10),
            getHistory(),
          ]);
          setSummary(summaryData);
          setTopPermitted(domainsData.top_permitted);
          setTopBlocked(blockedData.top_blocked);
          setTopClients(clientsData.top_clients);
          setHistory(historyData.history);
        } catch (err: any) {
          toast.error(err?.response?.data?.detail || 'Failed to load Pi-hole statistics');
        }
      }
    } catch (err: any) {
      setFetchError(true);
      toast.error(err?.response?.data?.detail || 'Failed to load Pi-hole data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchOverview();
    const interval = setInterval(fetchOverview, 30000);
    return () => clearInterval(interval);
  }, [fetchOverview]);

  const handleBlockingToggle = async (enabled: boolean) => {
    try {
      await setBlocking(enabled);
      setStatus((prev) => prev ? { ...prev, blocking_enabled: enabled } : prev);
      toast.success(enabled ? 'Blocking enabled' : 'Blocking disabled');
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to toggle blocking');
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-white">Pi-hole DNS</h1>
          <p className="mt-1 text-sm text-slate-400">
            Network-wide DNS filtering and ad blocking
          </p>
        </div>
      </div>

      {/* Disabled State */}
      {status && status.mode === 'disabled' && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-6">
          <div className="flex items-start gap-4">
            <AlertTriangle className="mt-0.5 h-6 w-6 flex-shrink-0 text-amber-400" />
            <div>
              <h3 className="text-lg font-medium text-amber-200">Pi-hole is not configured</h3>
              <p className="mt-1 text-sm text-slate-400">
                DNS filtering is currently disabled. Go to the{' '}
                <button
                  onClick={() => setActiveTab('settings')}
                  className="text-blue-400 underline hover:text-blue-300"
                >
                  Settings
                </button>{' '}
                tab to enable Docker or Remote mode.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Unreachable State */}
      {(fetchError || (status && !status.connected && status.mode !== 'disabled')) && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-6">
          <div className="flex items-start gap-4">
            <WifiOff className="mt-0.5 h-6 w-6 flex-shrink-0 text-red-400" />
            <div>
              <h3 className="text-lg font-medium text-red-200">Pi-hole is unreachable</h3>
              <p className="mt-1 text-sm text-slate-400">
                The {status?.mode ?? 'configured'} Pi-hole instance is not responding. Check that the{' '}
                {status?.mode === 'docker' ? 'Docker container is running' : 'remote server is online'}{' '}
                or update the configuration in{' '}
                <button
                  onClick={() => setActiveTab('settings')}
                  className="text-blue-400 underline hover:text-blue-300"
                >
                  Settings
                </button>.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Status Bar */}
      {status && status.mode !== 'disabled' && (
        <PiholeStatusBar
          status={status}
          onBlockingToggle={handleBlockingToggle}
          loading={loading}
        />
      )}

      {/* Tab Navigation */}
      <div className="flex gap-1 rounded-lg border border-slate-700/50 bg-slate-800/40 p-1">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`flex-1 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
              activeTab === tab.key
                ? 'bg-slate-700/80 text-white'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === 'overview' && (
        <div className="space-y-6">
          <PiholeSummaryCards summary={summary} loading={loading} />
          <PiholeQueryTimeline history={history} loading={loading} />
          <div className="grid gap-6 lg:grid-cols-2">
            <TopDomainsPanel topPermitted={topPermitted} topBlocked={topBlocked} loading={loading} />
            <TopClientsPanel clients={topClients} loading={loading} />
          </div>
        </div>
      )}

      {activeTab === 'queries' && (
        <PiholeQueryLog />
      )}

      {activeTab === 'domains' && (
        <PiholeDomainManagement />
      )}

      {activeTab === 'adlists' && (
        <PiholeAdlistManagement />
      )}

      {activeTab === 'dns' && (
        <PiholeLocalDns />
      )}

      {activeTab === 'settings' && (
        <PiholeSettings />
      )}

      {activeTab === 'container' && (
        <PiholeContainerActions />
      )}
    </div>
  );
}
