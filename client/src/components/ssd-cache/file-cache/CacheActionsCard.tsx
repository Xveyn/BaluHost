import { Trash2, RefreshCw } from 'lucide-react';

export function CacheActionsCard(props: {
  actionLoading: boolean;
  onTriggerEviction: () => void;
  onClearCache: () => void;
  onRefresh: () => void;
}) {
  const { actionLoading, onTriggerEviction, onClearCache, onRefresh } = props;
  return (
    <div className="card border-slate-800/60 bg-slate-900/55">
      <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
        <RefreshCw className="w-5 h-5 text-sky-400" />
        Actions
      </h3>
      <div className="flex flex-wrap gap-3">
        <button
          onClick={onTriggerEviction}
          disabled={actionLoading}
          className="px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white rounded-lg transition-colors disabled:opacity-50 flex items-center gap-2 text-sm"
        >
          <RefreshCw className={`w-4 h-4 ${actionLoading ? 'animate-spin' : ''}`} />
          Trigger Eviction
        </button>
        <button
          onClick={onClearCache}
          disabled={actionLoading}
          className="px-4 py-2 bg-red-500 hover:bg-red-600 text-white rounded-lg transition-colors disabled:opacity-50 flex items-center gap-2 text-sm"
        >
          <Trash2 className="w-4 h-4" />
          Clear Cache
        </button>
        <button
          onClick={onRefresh}
          disabled={actionLoading}
          className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-lg transition-colors disabled:opacity-50 flex items-center gap-2 text-sm"
        >
          <RefreshCw className={`w-4 h-4 ${actionLoading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>
    </div>
  );
}
