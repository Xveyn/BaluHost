/**
 * Version History Modal
 * Shows all versions of a file with actions (restore, delete, download, priority)
 */

import { useState, useEffect } from 'react';
import {
  X,
  Clock,
  Download,
  RotateCcw,
  Trash2,
  Star,
  StarOff,
  Archive,
  AlertCircle,
  Check,
} from 'lucide-react';
import {
  getFileVersions,
  restoreVersion,
  deleteVersion,
  toggleVersionPriority,
  downloadVersion,
  formatBytes,
  formatCompressionRatio,
  calculateSavingsPercent,
} from '../../api/vcl';
import type { VersionDetail } from '../../types/vcl';

interface VersionHistoryModalProps {
  fileId: number;
  fileName: string;
  onClose: () => void;
  onVersionRestored?: () => void;
}

export function VersionHistoryModal({
  fileId,
  fileName,
  onClose,
  onVersionRestored,
}: VersionHistoryModalProps) {
  const [versions, setVersions] = useState<VersionDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  useEffect(() => {
    loadVersions();
  }, [fileId]);

  const loadVersions = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getFileVersions(fileId);
      setVersions(data.versions);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load versions');
    } finally {
      setLoading(false);
    }
  };

  const handleRestore = async (versionId: number, versionNumber: number) => {
    if (!confirm(`Restore file to version ${versionNumber}?`)) return;

    try {
      setActionLoading(versionId);
      setError(null);
      await restoreVersion({ version_id: versionId });
      setSuccessMessage(`File restored to version ${versionNumber}`);
      setTimeout(() => setSuccessMessage(null), 3000);
      onVersionRestored?.();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to restore version');
    } finally {
      setActionLoading(null);
    }
  };

  const handleDelete = async (versionId: number, versionNumber: number) => {
    if (!confirm(`Delete version ${versionNumber}? This cannot be undone.`)) return;

    try {
      setActionLoading(versionId);
      setError(null);
      await deleteVersion(versionId);
      setSuccessMessage(`Version ${versionNumber} deleted`);
      setTimeout(() => setSuccessMessage(null), 3000);
      loadVersions(); // Reload list
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to delete version');
    } finally {
      setActionLoading(null);
    }
  };

  const handleTogglePriority = async (versionId: number, currentPriority: boolean) => {
    try {
      setActionLoading(versionId);
      setError(null);
      await toggleVersionPriority(versionId, !currentPriority);
      loadVersions(); // Reload to update UI
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to toggle priority');
    } finally {
      setActionLoading(null);
    }
  };

  const handleDownload = async (versionId: number, versionNumber: number) => {
    try {
      setActionLoading(versionId);
      setError(null);
      const blob = await downloadVersion(versionId);
      
      // Create download link
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${fileName}_v${versionNumber}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
      
      setSuccessMessage('Download started');
      setTimeout(() => setSuccessMessage(null), 2000);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to download version');
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="bg-slate-900 rounded-xl shadow-2xl border border-slate-800 w-full max-w-4xl max-h-[85vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-slate-800">
          <div>
            <h2 className="text-xl font-bold text-white flex items-center gap-2">
              <Clock className="w-5 h-5 text-sky-400" />
              Version History
            </h2>
            <p className="text-sm text-slate-400 mt-1">{fileName}</p>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-slate-800 rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-slate-400" />
          </button>
        </div>

        {/* Messages */}
        {error && (
          <div className="mx-6 mt-4 p-4 bg-red-500/10 border border-red-500/30 rounded-lg flex items-center gap-2 text-red-400">
            <AlertCircle className="w-5 h-5 flex-shrink-0" />
            <span className="text-sm">{error}</span>
          </div>
        )}
        {successMessage && (
          <div className="mx-6 mt-4 p-4 bg-green-500/10 border border-green-500/30 rounded-lg flex items-center gap-2 text-green-400">
            <Check className="w-5 h-5 flex-shrink-0" />
            <span className="text-sm">{successMessage}</span>
          </div>
        )}

        {/* Version List */}
        <div className="flex-1 overflow-y-auto p-6 space-y-3">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-sky-500"></div>
            </div>
          ) : versions.length === 0 ? (
            <div className="text-center py-12 text-slate-400">
              <Clock className="w-12 h-12 mx-auto mb-3 opacity-50" />
              <p>No versions available</p>
            </div>
          ) : (
            versions.map((version, index) => {
              const savingsPercent = calculateSavingsPercent(
                version.file_size,
                version.compressed_size
              );
              const isLatest = index === 0;
              const isWorking = actionLoading === version.id;

              return (
                <div
                  key={version.id}
                  className={`p-4 rounded-lg border transition-all ${
                    isLatest
                      ? 'bg-sky-500/10 border-sky-500/30'
                      : 'bg-slate-800/40 border-slate-700/50 hover:border-slate-600'
                  }`}
                >
                  <div className="flex items-start justify-between gap-4">
                    {/* Version Info */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="text-lg font-semibold text-white">
                          Version {version.version_number}
                        </span>
                        {isLatest && (
                          <span className="px-2 py-0.5 bg-sky-500/20 text-sky-400 text-xs font-medium rounded-full">
                            Latest
                          </span>
                        )}
                        {version.is_high_priority && (
                          <Star className="w-4 h-4 text-amber-400 fill-amber-400" />
                        )}
                        {version.was_cached && (
                          <span className="px-2 py-0.5 bg-violet-500/20 text-violet-400 text-xs font-medium rounded-full">
                            Cached
                          </span>
                        )}
                      </div>

                      {/* Metadata */}
                      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm text-slate-400 mb-2">
                        <div>
                          <span className="text-slate-500">Created:</span>{' '}
                          {new Date(version.created_at).toLocaleString()}
                        </div>
                        <div>
                          <span className="text-slate-500">Size:</span>{' '}
                          {formatBytes(version.file_size)}
                        </div>
                        <div>
                          <span className="text-slate-500">Compressed:</span>{' '}
                          {formatBytes(version.compressed_size)}
                        </div>
                        <div>
                          <span className="text-slate-500">Ratio:</span>{' '}
                          {formatCompressionRatio(version.compression_ratio)}
                        </div>
                        <div>
                          <span className="text-slate-500">Savings:</span>{' '}
                          {savingsPercent.toFixed(1)}%
                        </div>
                        <div>
                          <span className="text-slate-500">Storage:</span>{' '}
                          <span className={version.storage_type === 'reference' ? 'text-green-400' : ''}>
                            {version.storage_type}
                          </span>
                        </div>
                      </div>

                      {version.comment && (
                        <div className="text-sm text-slate-300 mt-2 italic">
                          "{version.comment}"
                        </div>
                      )}
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => handleTogglePriority(version.id, version.is_high_priority)}
                        disabled={isWorking}
                        className={`p-2 rounded-lg transition-colors ${
                          version.is_high_priority
                            ? 'text-amber-400 hover:bg-amber-500/10'
                            : 'text-slate-400 hover:bg-slate-700'
                        } disabled:opacity-50`}
                        title={version.is_high_priority ? 'Remove priority' : 'Mark as priority'}
                      >
                        {version.is_high_priority ? (
                          <Star className="w-4 h-4 fill-amber-400" />
                        ) : (
                          <StarOff className="w-4 h-4" />
                        )}
                      </button>

                      <button
                        onClick={() => handleDownload(version.id, version.version_number)}
                        disabled={isWorking}
                        className="p-2 text-slate-400 hover:text-sky-400 hover:bg-slate-700 rounded-lg transition-colors disabled:opacity-50"
                        title="Download version"
                      >
                        <Download className="w-4 h-4" />
                      </button>

                      <button
                        onClick={() => handleRestore(version.id, version.version_number)}
                        disabled={isWorking || isLatest}
                        className="p-2 text-slate-400 hover:text-green-400 hover:bg-slate-700 rounded-lg transition-colors disabled:opacity-50"
                        title="Restore this version"
                      >
                        <RotateCcw className="w-4 h-4" />
                      </button>

                      <button
                        onClick={() => handleDelete(version.id, version.version_number)}
                        disabled={isWorking || isLatest}
                        className="p-2 text-slate-400 hover:text-red-400 hover:bg-slate-700 rounded-lg transition-colors disabled:opacity-50"
                        title="Delete version"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>

                  {isWorking && (
                    <div className="mt-3 pt-3 border-t border-slate-700/50 flex items-center gap-2 text-sky-400">
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-sky-500"></div>
                      <span className="text-sm">Processing...</span>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>

        {/* Footer */}
        <div className="p-6 border-t border-slate-800 bg-slate-900/50">
          <div className="flex items-center justify-between text-sm">
            <div className="text-slate-400">
              <Archive className="w-4 h-4 inline mr-1" />
              {versions.length} version{versions.length !== 1 ? 's' : ''} total
            </div>
            <button
              onClick={onClose}
              className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-lg transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
