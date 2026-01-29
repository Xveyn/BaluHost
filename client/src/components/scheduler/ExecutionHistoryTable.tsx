import { useState } from 'react';
import { ChevronDown, ChevronRight, ChevronLeft, Filter, RefreshCw, Loader2 } from 'lucide-react';
import type { SchedulerExecution, SchedulerHistoryResponse, SchedulerExecStatus } from '../../api/schedulers';
import {
  getStatusBadgeClasses,
  getSchedulerIcon,
  parseResultSummary,
  SchedulerExecStatus as StatusEnum,
} from '../../api/schedulers';

interface ExecutionHistoryTableProps {
  history: SchedulerHistoryResponse | null;
  loading: boolean;
  error: string | null;
  onPageChange: (page: number) => void;
  onStatusFilterChange: (filter: SchedulerExecStatus | undefined) => void;
  onRefresh: () => void;
  statusFilter?: SchedulerExecStatus;
}

function ExecutionRow({ execution }: { execution: SchedulerExecution }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const result = parseResultSummary(execution.result_summary);

  return (
    <>
      <tr
        className="border-b border-slate-800 hover:bg-slate-800/30 cursor-pointer transition-colors"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <td className="px-4 py-3">
          <button className="text-slate-400 hover:text-white">
            {isExpanded ? (
              <ChevronDown className="h-4 w-4" />
            ) : (
              <ChevronRight className="h-4 w-4" />
            )}
          </button>
        </td>
        <td className="px-4 py-3">
          <div className="flex items-center gap-2">
            <span className="text-lg">{getSchedulerIcon(execution.scheduler_name)}</span>
            <span className="text-sm text-slate-200">
              {execution.scheduler_name.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
            </span>
          </div>
        </td>
        <td className="px-4 py-3 text-sm text-slate-400">
          {new Date(execution.started_at).toLocaleString()}
        </td>
        <td className="px-4 py-3">
          <span className="text-sm text-slate-400">
            {execution.duration_display || '-'}
          </span>
        </td>
        <td className="px-4 py-3">
          <span className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${getStatusBadgeClasses(execution.status)}`}>
            {execution.status}
          </span>
        </td>
        <td className="px-4 py-3">
          <span className={`inline-flex items-center rounded px-2 py-0.5 text-xs ${
            execution.trigger_type === 'manual'
              ? 'bg-purple-900/50 text-purple-300'
              : 'bg-slate-800 text-slate-400'
          }`}>
            {execution.trigger_type}
          </span>
        </td>
      </tr>
      {isExpanded && (
        <tr className="bg-slate-800/20">
          <td colSpan={6} className="px-4 py-3">
            <div className="ml-8 space-y-2">
              {/* Result summary */}
              {result && (
                <div>
                  <span className="text-xs text-slate-500">Result:</span>
                  <pre className="mt-1 text-xs text-slate-300 bg-slate-900/50 rounded p-2 overflow-x-auto">
                    {JSON.stringify(result, null, 2)}
                  </pre>
                </div>
              )}
              {/* Error message */}
              {execution.error_message && (
                <div>
                  <span className="text-xs text-slate-500">Error:</span>
                  <div className="mt-1 text-xs text-red-400 bg-red-900/20 rounded p-2">
                    {execution.error_message}
                  </div>
                </div>
              )}
              {/* Job ID */}
              {execution.job_id && (
                <div className="text-xs text-slate-500">
                  Job ID: <span className="text-slate-400">{execution.job_id}</span>
                </div>
              )}
              {/* User ID for manual runs */}
              {execution.user_id && (
                <div className="text-xs text-slate-500">
                  Triggered by User ID: <span className="text-slate-400">{execution.user_id}</span>
                </div>
              )}
              {/* Completed at */}
              {execution.completed_at && (
                <div className="text-xs text-slate-500">
                  Completed: <span className="text-slate-400">{new Date(execution.completed_at).toLocaleString()}</span>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export function ExecutionHistoryTable({
  history,
  loading,
  error,
  onPageChange,
  onStatusFilterChange,
  onRefresh,
  statusFilter,
}: ExecutionHistoryTableProps) {
  const [filterOpen, setFilterOpen] = useState(false);

  const statusOptions: Array<{ value: SchedulerExecStatus | undefined; label: string }> = [
    { value: undefined, label: 'All' },
    { value: StatusEnum.COMPLETED, label: 'Completed' },
    { value: StatusEnum.FAILED, label: 'Failed' },
    { value: StatusEnum.RUNNING, label: 'Running' },
    { value: StatusEnum.CANCELLED, label: 'Cancelled' },
  ];

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/60 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800">
        <h3 className="font-medium text-white">Execution History</h3>
        <div className="flex items-center gap-2">
          {/* Status filter */}
          <div className="relative">
            <button
              onClick={() => setFilterOpen(!filterOpen)}
              className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm transition-colors ${
                statusFilter
                  ? 'bg-sky-600 text-white'
                  : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
              }`}
            >
              <Filter className="h-4 w-4" />
              {statusFilter || 'Filter'}
            </button>
            {filterOpen && (
              <>
                <div
                  className="fixed inset-0 z-10"
                  onClick={() => setFilterOpen(false)}
                />
                <div className="absolute right-0 mt-1 z-20 w-40 rounded-md border border-slate-700 bg-slate-800 shadow-lg">
                  {statusOptions.map((option) => (
                    <button
                      key={option.label}
                      onClick={() => {
                        onStatusFilterChange(option.value);
                        setFilterOpen(false);
                      }}
                      className={`w-full px-3 py-2 text-left text-sm transition-colors ${
                        statusFilter === option.value
                          ? 'bg-sky-600 text-white'
                          : 'text-slate-300 hover:bg-slate-700'
                      }`}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
          {/* Refresh button */}
          <button
            onClick={onRefresh}
            disabled={loading}
            className="inline-flex items-center gap-1.5 rounded-md bg-slate-800 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-700 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="px-4 py-3 bg-red-900/20 border-b border-red-800">
          <p className="text-sm text-red-400">{error}</p>
        </div>
      )}

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-slate-800 bg-slate-800/30">
              <th className="w-10 px-4 py-2"></th>
              <th className="px-4 py-2 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">
                Scheduler
              </th>
              <th className="px-4 py-2 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">
                Started
              </th>
              <th className="px-4 py-2 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">
                Duration
              </th>
              <th className="px-4 py-2 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">
                Status
              </th>
              <th className="px-4 py-2 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">
                Trigger
              </th>
            </tr>
          </thead>
          <tbody>
            {loading && !history ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center">
                  <Loader2 className="h-6 w-6 animate-spin mx-auto text-slate-400" />
                </td>
              </tr>
            ) : history?.executions.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-slate-400">
                  No executions found
                </td>
              </tr>
            ) : (
              history?.executions.map((execution) => (
                <ExecutionRow key={execution.id} execution={execution} />
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {history && history.total_pages > 1 && (
        <div className="flex items-center justify-between px-4 py-3 border-t border-slate-800">
          <div className="text-sm text-slate-400">
            Page {history.page} of {history.total_pages} ({history.total} total)
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => onPageChange(history.page - 1)}
              disabled={history.page <= 1}
              className="inline-flex items-center gap-1 rounded-md bg-slate-800 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <ChevronLeft className="h-4 w-4" />
              Previous
            </button>
            <button
              onClick={() => onPageChange(history.page + 1)}
              disabled={history.page >= history.total_pages}
              className="inline-flex items-center gap-1 rounded-md bg-slate-800 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Next
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
