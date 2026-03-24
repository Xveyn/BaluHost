import { useState, useEffect, useCallback } from 'react';
import { Search, Activity, RefreshCw } from 'lucide-react';
import toast from 'react-hot-toast';
import { getAdDiscoveryStatus, startAnalysis, type AdDiscoveryStatus } from '../../api/adDiscovery';
import SuspectsTable from './ad-discovery/SuspectsTable';
import PatternsPanel from './ad-discovery/PatternsPanel';
import ReferenceListsPanel from './ad-discovery/ReferenceListsPanel';
import CustomListsPanel from './ad-discovery/CustomListsPanel';

type SubTab = 'suspects' | 'patterns' | 'reference-lists' | 'custom-lists';

export default function AdDiscoveryTab() {
  const [status, setStatus] = useState<AdDiscoveryStatus | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [subTab, setSubTab] = useState<SubTab>('suspects');

  const fetchStatus = useCallback(async () => {
    try {
      const data = await getAdDiscoveryStatus();
      setStatus(data);
    } catch {
      // Silently fail — status bar just won't show data
    }
  }, []);

  useEffect(() => { fetchStatus(); }, [fetchStatus]);

  const handleAnalyze = async () => {
    setAnalyzing(true);
    try {
      const result = await startAnalysis();
      toast.success(`Analysis complete: ${result.new_suspects} new, ${result.updated_suspects} updated`);
      fetchStatus();
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      toast.error(e?.response?.data?.detail || 'Analysis failed');
    } finally {
      setAnalyzing(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Status Bar */}
      <div className="flex flex-wrap items-center gap-4 rounded-lg border border-slate-700/50 bg-slate-800/40 p-4">
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400">New suspects:</span>
          <span className="font-semibold text-white">{status?.suspects_new ?? '—'}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400">Last analysis:</span>
          <span className="text-sm text-slate-300">
            {status?.last_analysis_at ? new Date(status.last_analysis_at).toLocaleString() : 'Never'}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400">Background:</span>
          {status?.background_task_running
            ? <span className="flex items-center gap-1 text-xs text-green-400"><Activity className="h-3 w-3" /> Active</span>
            : <span className="text-xs text-slate-500">Inactive</span>
          }
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400">Reference lists:</span>
          <span className="text-sm text-slate-300">{status?.reference_lists_active ?? 0}/{status?.reference_lists_total ?? 0}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400">Custom lists:</span>
          <span className="text-sm text-slate-300">{status?.custom_lists_total ?? 0} ({status?.custom_lists_deployed ?? 0} deployed)</span>
        </div>
        <div className="flex-1" />
        <button onClick={handleAnalyze} disabled={analyzing}
          className="flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50">
          {analyzing ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
          {analyzing ? 'Analyzing...' : 'Start Analysis'}
        </button>
      </div>

      {/* Sub-Tab Navigation */}
      <div className="flex gap-1 rounded-lg border border-slate-700/50 bg-slate-800/40 p-1">
        {([
          { key: 'suspects', label: 'Suspects' },
          { key: 'patterns', label: 'Patterns' },
          { key: 'reference-lists', label: 'Reference Lists' },
          { key: 'custom-lists', label: 'Custom Lists' },
        ] as { key: SubTab; label: string }[]).map(tab => (
          <button key={tab.key} onClick={() => setSubTab(tab.key)}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              subTab === tab.key ? 'bg-slate-700/80 text-white' : 'text-slate-400 hover:text-slate-200'
            }`}>
            {tab.label}
          </button>
        ))}
      </div>

      {/* Sub-Tab Content */}
      {subTab === 'suspects' && <SuspectsTable />}
      {subTab === 'patterns' && <PatternsPanel />}
      {subTab === 'reference-lists' && <ReferenceListsPanel />}
      {subTab === 'custom-lists' && <CustomListsPanel />}
    </div>
  );
}
