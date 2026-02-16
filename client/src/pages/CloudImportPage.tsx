import { useState, useEffect, useCallback } from 'react';
import {
  Cloud, Plus, Download, RefreshCw, Loader2, XCircle, CheckCircle2,
  Clock, AlertCircle, FolderDown,
} from 'lucide-react';
import {
  getConnections, deleteConnection, getJobs, cancelJob,
  type CloudConnection, type CloudImportJob,
} from '../api/cloud-import';
import { formatBytes } from '../lib/formatters';
import { CloudProviderCard } from '../components/cloud/CloudProviderCard';
import { CloudFileBrowser } from '../components/cloud/CloudFileBrowser';
import { CloudImportDialog } from '../components/cloud/CloudImportDialog';
import { CloudConnectWizard } from '../components/cloud/CloudConnectWizard';
import { useConfirmDialog } from '../hooks/useConfirmDialog';
import { toast } from 'react-hot-toast';

const STATUS_CONFIG: Record<string, { icon: React.ReactNode; color: string; label: string }> = {
  pending:   { icon: <Clock className="h-4 w-4" />,        color: 'text-amber-400 bg-amber-400/10 border-amber-400/20', label: 'Pending' },
  running:   { icon: <Loader2 className="h-4 w-4 animate-spin" />, color: 'text-sky-400 bg-sky-400/10 border-sky-400/20', label: 'Running' },
  completed: { icon: <CheckCircle2 className="h-4 w-4" />, color: 'text-emerald-400 bg-emerald-400/10 border-emerald-400/20', label: 'Completed' },
  failed:    { icon: <XCircle className="h-4 w-4" />,      color: 'text-red-400 bg-red-400/10 border-red-400/20', label: 'Failed' },
  cancelled: { icon: <XCircle className="h-4 w-4" />,      color: 'text-slate-400 bg-slate-400/10 border-slate-400/20', label: 'Cancelled' },
};

export default function CloudImportPage() {
  const { confirm, dialog } = useConfirmDialog();

  // State
  const [connections, setConnections] = useState<CloudConnection[]>([]);
  const [selectedConnectionId, setSelectedConnectionId] = useState<number | null>(null);
  const [jobs, setJobs] = useState<CloudImportJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [showWizard, setShowWizard] = useState(false);
  const [showImportDialog, setShowImportDialog] = useState(false);
  const [selectedPaths, setSelectedPaths] = useState<Set<string>>(new Set());

  const loadData = useCallback(async () => {
    try {
      const [conns, jobList] = await Promise.all([getConnections(), getJobs()]);
      setConnections(conns);
      setJobs(jobList);
    } catch (err) {
      console.error('Failed to load cloud data:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();

    const params = new URLSearchParams(window.location.search);
    if (params.get('oauth') === 'success') {
      toast.success('Cloud provider connected successfully');
      window.history.replaceState({}, '', '/cloud-import');
    } else if (params.get('oauth_error')) {
      toast.error(`OAuth failed: ${params.get('oauth_error')}`);
      window.history.replaceState({}, '', '/cloud-import');
    }
  }, [loadData]);

  // Poll running jobs
  useEffect(() => {
    const hasRunning = jobs.some(j => j.status === 'running' || j.status === 'pending');
    if (!hasRunning) return;

    const timer = setInterval(async () => {
      try {
        const jobList = await getJobs();
        setJobs(jobList);
      } catch {
        // ignore
      }
    }, 3000);

    return () => clearInterval(timer);
  }, [jobs]);

  const handleDeleteConnection = async (conn: CloudConnection) => {
    const confirmed = await confirm(
      `Remove "${conn.display_name}"? Active import jobs will not be affected.`,
      { title: 'Delete Connection', confirmLabel: 'Delete', variant: 'danger' }
    );
    if (!confirmed) return;

    try {
      await deleteConnection(conn.id);
      toast.success('Connection deleted');
      if (selectedConnectionId === conn.id) setSelectedConnectionId(null);
      loadData();
    } catch {
      toast.error('Failed to delete connection');
    }
  };

  const handleCancelJob = async (job: CloudImportJob) => {
    try {
      await cancelJob(job.id);
      toast.success('Job cancelled');
      loadData();
    } catch {
      toast.error('Failed to cancel job');
    }
  };

  const handleTogglePath = (path: string, _isDirectory: boolean) => {
    setSelectedPaths(prev => {
      const next = new Set(prev);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  };

  const selectedConnection = connections.find(c => c.id === selectedConnectionId) || null;

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-slate-500" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6">
      {dialog}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-sky-500 to-violet-600">
            <Cloud className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-slate-100">Cloud Import</h1>
            <p className="text-sm text-slate-500">
              Import files from Google Drive, OneDrive, or iCloud
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={loadData}
            className="rounded-lg border border-slate-700/50 p-2 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
            title="Refresh"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
          <button
            onClick={() => setShowWizard(true)}
            className="flex items-center gap-2 rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500"
          >
            <Plus className="h-4 w-4" />
            Add Connection
          </button>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Left column: Connections */}
        <div className="space-y-3">
          <h2 className="text-sm font-medium uppercase tracking-wider text-slate-500">
            Connections
          </h2>
          {connections.length === 0 ? (
            <div className="rounded-xl border border-dashed border-slate-700/50 py-12 text-center">
              <Cloud className="mx-auto mb-3 h-8 w-8 text-slate-600" />
              <p className="text-sm text-slate-500">No cloud connections yet</p>
              <button
                onClick={() => setShowWizard(true)}
                className="mt-3 text-sm text-sky-400 hover:text-sky-300"
              >
                Add your first connection
              </button>
            </div>
          ) : (
            connections.map((conn) => (
              <CloudProviderCard
                key={conn.id}
                connection={conn}
                selected={selectedConnectionId === conn.id}
                onSelect={() => {
                  setSelectedConnectionId(conn.id);
                  setSelectedPaths(new Set());
                }}
                onDelete={() => handleDeleteConnection(conn)}
              />
            ))
          )}
        </div>

        {/* Center column: File Browser */}
        <div className="lg:col-span-2 space-y-3">
          {selectedConnection ? (
            <>
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-medium uppercase tracking-wider text-slate-500">
                  Browse: {selectedConnection.display_name}
                </h2>
                {selectedPaths.size > 0 && (
                  <button
                    onClick={() => setShowImportDialog(true)}
                    className="flex items-center gap-2 rounded-lg bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-500"
                  >
                    <FolderDown className="h-4 w-4" />
                    Import {selectedPaths.size} item{selectedPaths.size > 1 ? 's' : ''}
                  </button>
                )}
              </div>
              <CloudFileBrowser
                connectionId={selectedConnection.id}
                selectedPaths={selectedPaths}
                onTogglePath={handleTogglePath}
              />
            </>
          ) : (
            <div className="flex h-64 items-center justify-center rounded-xl border border-dashed border-slate-700/50">
              <p className="text-sm text-slate-600">
                {connections.length > 0
                  ? 'Select a connection to browse files'
                  : 'Add a cloud connection to get started'}
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Import Jobs */}
      <div className="space-y-3">
        <h2 className="text-sm font-medium uppercase tracking-wider text-slate-500">
          Import Jobs
        </h2>
        {jobs.length === 0 ? (
          <div className="rounded-xl border border-dashed border-slate-700/50 py-8 text-center">
            <Download className="mx-auto mb-2 h-6 w-6 text-slate-600" />
            <p className="text-sm text-slate-500">No import jobs yet</p>
          </div>
        ) : (
          <div className="space-y-2">
            {jobs.map((job) => {
              const cfg = STATUS_CONFIG[job.status] || STATUS_CONFIG.pending;
              const progress = job.total_bytes && job.total_bytes > 0
                ? Math.round((job.progress_bytes / job.total_bytes) * 100)
                : null;

              return (
                <div
                  key={job.id}
                  className="flex items-center gap-4 rounded-xl border border-slate-700/50 bg-slate-800/30 p-4"
                >
                  {/* Status badge */}
                  <div className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${cfg.color}`}>
                    {cfg.icon}
                    {cfg.label}
                  </div>

                  {/* Info */}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-slate-300">
                        {job.source_path}
                      </span>
                      <span className="text-xs text-slate-600">
                        {job.job_type === 'sync' ? (
                          <span className="flex items-center gap-1">
                            <RefreshCw className="h-3 w-3" /> Sync
                          </span>
                        ) : 'Import'}
                      </span>
                    </div>
                    <div className="mt-0.5 flex items-center gap-3 text-xs text-slate-500">
                      <span>{formatBytes(job.progress_bytes)}{job.total_bytes ? ` / ${formatBytes(job.total_bytes)}` : ''}</span>
                      <span>{job.files_transferred} files{job.files_total ? ` / ${job.files_total}` : ''}</span>
                      {job.current_file && (
                        <span className="truncate text-slate-600">
                          {job.current_file}
                        </span>
                      )}
                    </div>

                    {/* Progress bar */}
                    {job.status === 'running' && (
                      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-700/50">
                        <div
                          className="h-full rounded-full bg-gradient-to-r from-sky-500 to-sky-400 transition-all duration-500"
                          style={{ width: `${progress ?? 0}%` }}
                        />
                      </div>
                    )}

                    {/* Error */}
                    {job.error_message && (
                      <p className="mt-1 flex items-center gap-1 text-xs text-red-400">
                        <AlertCircle className="h-3 w-3" />
                        {job.error_message}
                      </p>
                    )}
                  </div>

                  {/* Time */}
                  <span className="hidden shrink-0 text-xs text-slate-600 sm:block">
                    {new Date(job.created_at).toLocaleString()}
                  </span>

                  {/* Cancel button */}
                  {(job.status === 'running' || job.status === 'pending') && (
                    <button
                      onClick={() => handleCancelJob(job)}
                      className="rounded-lg border border-slate-700/50 px-3 py-1 text-xs text-slate-400 hover:border-red-500/30 hover:bg-red-500/10 hover:text-red-400"
                    >
                      Cancel
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Modals */}
      {showWizard && (
        <CloudConnectWizard
          onClose={() => setShowWizard(false)}
          onConnected={() => {
            setShowWizard(false);
            loadData();
          }}
        />
      )}

      {showImportDialog && selectedConnection && (
        <CloudImportDialog
          connectionId={selectedConnection.id}
          selectedPaths={Array.from(selectedPaths)}
          onClose={() => setShowImportDialog(false)}
          onStarted={() => {
            setSelectedPaths(new Set());
            loadData();
          }}
        />
      )}
    </div>
  );
}
