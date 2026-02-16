import { useState } from 'react';
import { X, Download, RefreshCw, FolderInput, FolderOpen } from 'lucide-react';
import { startImport, type CloudImportJob } from '../../api/cloud-import';
import { toast } from 'react-hot-toast';
import { NasFolderPicker } from './NasFolderPicker';

interface CloudImportDialogProps {
  connectionId: number;
  selectedPaths: string[];
  onClose: () => void;
  onStarted: (job: CloudImportJob) => void;
}

export function CloudImportDialog({
  connectionId,
  selectedPaths,
  onClose,
  onStarted,
}: CloudImportDialogProps) {
  const [destinationPath, setDestinationPath] = useState('cloud-import');
  const [jobType, setJobType] = useState<'import' | 'sync'>('import');
  const [submitting, setSubmitting] = useState(false);
  const [showFolderPicker, setShowFolderPicker] = useState(false);

  const handleSubmit = async () => {
    if (selectedPaths.length === 0) return;

    setSubmitting(true);
    try {
      // Start an import for each selected path (or combine them)
      const sourcePath = selectedPaths.length === 1
        ? selectedPaths[0]
        : '/';  // If multiple selected, import root (user can refine)

      const job = await startImport({
        connection_id: connectionId,
        source_path: sourcePath,
        destination_path: destinationPath,
        job_type: jobType,
      });

      toast.success(`${jobType === 'sync' ? 'Sync' : 'Import'} started`);
      onStarted(job);
      onClose();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to start import';
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-2xl border border-slate-700/50 bg-slate-900 p-6 shadow-2xl">
        {/* Header */}
        <div className="mb-6 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-slate-100">Start Import</h3>
          <button
            onClick={onClose}
            className="rounded-lg p-1 text-slate-400 hover:bg-slate-700/50 hover:text-slate-200"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Selected paths */}
        <div className="mb-4">
          <label className="mb-1.5 block text-sm font-medium text-slate-400">
            Source ({selectedPaths.length} selected)
          </label>
          <div className="max-h-24 overflow-y-auto rounded-lg border border-slate-700/50 bg-slate-800/50 px-3 py-2">
            {selectedPaths.map((path) => (
              <p key={path} className="truncate text-sm text-slate-300">{path}</p>
            ))}
          </div>
        </div>

        {/* Destination */}
        <div className="mb-4">
          <label className="mb-1.5 block text-sm font-medium text-slate-400">
            Destination on NAS
          </label>
          <div className="flex gap-2">
            <div className="flex flex-1 items-center gap-2 rounded-lg border border-slate-700/50 bg-slate-800/50 px-3 py-2">
              <FolderInput className="h-4 w-4 shrink-0 text-slate-500" />
              <input
                type="text"
                value={destinationPath}
                onChange={(e) => setDestinationPath(e.target.value)}
                placeholder="cloud-import"
                className="w-full bg-transparent text-sm text-slate-200 outline-none placeholder:text-slate-600"
              />
            </div>
            <button
              type="button"
              onClick={() => setShowFolderPicker(true)}
              className="flex items-center gap-1.5 rounded-lg border border-slate-700/50 px-3 py-2 text-sm text-slate-400 transition-colors hover:bg-slate-800 hover:text-slate-200"
              title="Browse folders"
            >
              <FolderOpen className="h-4 w-4" />
              Browse
            </button>
          </div>
          <p className="mt-1 text-xs text-slate-600">
            Relative to your storage root
          </p>
        </div>

        {/* Job type */}
        <div className="mb-6">
          <label className="mb-1.5 block text-sm font-medium text-slate-400">Mode</label>
          <div className="flex gap-2">
            <button
              onClick={() => setJobType('import')}
              className={`flex flex-1 items-center justify-center gap-2 rounded-lg border px-3 py-2 text-sm transition-colors ${
                jobType === 'import'
                  ? 'border-sky-500/50 bg-sky-500/10 text-sky-400'
                  : 'border-slate-700/50 text-slate-500 hover:border-slate-600 hover:text-slate-400'
              }`}
            >
              <Download className="h-4 w-4" />
              One-time Import
            </button>
            <button
              onClick={() => setJobType('sync')}
              className={`flex flex-1 items-center justify-center gap-2 rounded-lg border px-3 py-2 text-sm transition-colors ${
                jobType === 'sync'
                  ? 'border-violet-500/50 bg-violet-500/10 text-violet-400'
                  : 'border-slate-700/50 text-slate-500 hover:border-slate-600 hover:text-slate-400'
              }`}
            >
              <RefreshCw className="h-4 w-4" />
              Recurring Sync
            </button>
          </div>
          {jobType === 'sync' && (
            <p className="mt-1.5 text-xs text-violet-400/70">
              This path will be synced periodically via the Cloud Sync scheduler.
            </p>
          )}
        </div>

        {/* Actions */}
        <div className="flex justify-end gap-3">
          <button
            onClick={onClose}
            className="rounded-lg border border-slate-700/50 px-4 py-2 text-sm text-slate-400 hover:bg-slate-800"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting || selectedPaths.length === 0}
            className="flex items-center gap-2 rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-sky-500 disabled:opacity-50"
          >
            {submitting ? (
              <>
                <div className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                Starting...
              </>
            ) : (
              <>
                <Download className="h-4 w-4" />
                Start {jobType === 'sync' ? 'Sync' : 'Import'}
              </>
            )}
          </button>
        </div>
      </div>

      {showFolderPicker && (
        <NasFolderPicker
          initialPath={destinationPath}
          onSelect={(path) => {
            setDestinationPath(path);
            setShowFolderPicker(false);
          }}
          onClose={() => setShowFolderPicker(false)}
        />
      )}
    </div>
  );
}
