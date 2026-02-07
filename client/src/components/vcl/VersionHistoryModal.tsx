/**
 * Version History Modal
 * Shows all versions of a file with actions (restore, delete, download, priority)
 */

import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
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
  Loader2,
} from 'lucide-react';
import {
  getFileVersions,
  restoreVersion,
  deleteVersion,
  toggleVersionPriority,
  downloadVersion,
  getVersionDiff,
  formatBytes,
  formatCompressionRatio,
  calculateSavingsPercent,
} from '../../api/vcl';
import { formatNumber } from '../../lib/formatters';
import type { VersionDetail, VersionDiffResponse } from '../../types/vcl';

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
  
  // Diff state
  const [selectedForDiff, setSelectedForDiff] = useState<number[]>([]);
  const [diffData, setDiffData] = useState<VersionDiffResponse | null>(null);
  const [showDiff, setShowDiff] = useState(false);
  const [diffLoading, setDiffLoading] = useState(false);
  const { t } = useTranslation('admin');

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
      setError(err.response?.data?.detail || t('versionHistory.errors.loadFailed'));
    } finally {
      setLoading(false);
    }
  };

  const handleRestore = async (versionId: number, versionNumber: number) => {
    if (!confirm(t('versionHistory.actions.restoreConfirm', { number: versionNumber }))) return;

    try {
      setActionLoading(versionId);
      setError(null);
      await restoreVersion({ version_id: versionId });
      setSuccessMessage(t('versionHistory.actions.restored', { number: versionNumber }));
      setTimeout(() => setSuccessMessage(null), 3000);
      onVersionRestored?.();
    } catch (err: any) {
      setError(err.response?.data?.detail || t('versionHistory.errors.restoreFailed'));
    } finally {
      setActionLoading(null);
    }
  };

  const handleDelete = async (versionId: number, versionNumber: number) => {
    if (!confirm(t('versionHistory.actions.deleteConfirm', { number: versionNumber }))) return;

    try {
      setActionLoading(versionId);
      setError(null);
      await deleteVersion(versionId);
      setSuccessMessage(t('versionHistory.actions.deleted', { number: versionNumber }));
      setTimeout(() => setSuccessMessage(null), 3000);
      loadVersions(); // Reload list
    } catch (err: any) {
      setError(err.response?.data?.detail || t('versionHistory.errors.deleteFailed'));
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
      setError(err.response?.data?.detail || t('versionHistory.errors.priorityFailed'));
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
      
      setSuccessMessage(t('versionHistory.actions.downloadStarted'));
      setTimeout(() => setSuccessMessage(null), 2000);
    } catch (err: any) {
      setError(err.response?.data?.detail || t('versionHistory.errors.downloadFailed'));
    } finally {
      setActionLoading(null);
    }
  };

  const handleSelectForDiff = (versionId: number) => {
    setSelectedForDiff((prev) => {
      if (prev.includes(versionId)) {
        return prev.filter((id) => id !== versionId);
      }
      if (prev.length >= 2) {
        return [prev[1], versionId]; // Keep only last and new
      }
      return [...prev, versionId];
    });
  };

  const handleCompareDiff = async () => {
    if (selectedForDiff.length !== 2) return;
    
    try {
      setDiffLoading(true);
      setError(null);
      // Always compare older vs newer
      const [id1, id2] = selectedForDiff.sort((a, b) => a - b);
      const data = await getVersionDiff(id1, id2);
      setDiffData(data);
      setShowDiff(true);
    } catch (err: any) {
      setError(err.response?.data?.detail || t('versionHistory.errors.diffFailed'));
    } finally {
      setDiffLoading(false);
    }
  };

  const closeDiff = () => {
    setShowDiff(false);
    setDiffData(null);
    setSelectedForDiff([]);
  };

  if (showDiff && diffData) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/90 backdrop-blur-lg p-4">
        <div className="card w-full max-w-6xl max-h-[90vh] border-slate-800/60 bg-slate-900/90 flex flex-col">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-xl font-semibold text-white">{t('versionHistory.diff.title', { fileName: diffData.file_name })}</h3>
            <button
              onClick={closeDiff}
              className="rounded-xl border border-slate-700/70 bg-slate-900/70 px-4 py-2 text-sm font-medium text-slate-300 transition hover:border-slate-500 hover:text-white"
            >
              {t('versionHistory.diff.close')}
            </button>
          </div>
          
          <div className="text-sm text-slate-400 mb-4 flex gap-4">
            <span>{t('versionHistory.diff.old', { version: selectedForDiff[0], size: formatBytes(diffData.old_size) })}</span>
            <span>→</span>
            <span>{t('versionHistory.diff.new', { version: selectedForDiff[1], size: formatBytes(diffData.new_size) })}</span>
          </div>

          {diffData.is_binary ? (
            <div className="flex-1 flex items-center justify-center text-slate-500">
              <div className="text-center">
                <AlertCircle className="w-12 h-12 mx-auto mb-3 text-amber-500" />
                <p>{diffData.message || t('versionHistory.diff.binaryMessage')}</p>
              </div>
            </div>
          ) : (
            <div className="flex-1 overflow-auto bg-slate-950/50 rounded-lg p-4 font-mono text-xs">
              {diffData.diff_lines && diffData.diff_lines.length > 0 ? (
                <table className="w-full border-collapse">
                  <tbody>
                    {diffData.diff_lines.map((line, idx) => (
                      <tr
                        key={idx}
                        className={`${
                          line.type === 'added'
                            ? 'bg-green-500/10'
                            : line.type === 'removed'
                            ? 'bg-red-500/10'
                            : ''
                        }`}
                      >
                        <td className="px-2 py-0.5 text-slate-600 text-right select-none w-12 border-r border-slate-800">
                          {line.line_number_old ?? ''}
                        </td>
                        <td className="px-2 py-0.5 text-slate-600 text-right select-none w-12 border-r border-slate-800">
                          {line.line_number_new ?? ''}
                        </td>
                        <td className="px-2 py-0.5 w-8">
                          {line.type === 'added' && <span className="text-green-400">+</span>}
                          {line.type === 'removed' && <span className="text-red-400">-</span>}
                          {line.type === 'unchanged' && <span className="text-slate-600"> </span>}
                        </td>
                        <td className="px-2 py-0.5">
                          <pre className={`whitespace-pre-wrap break-all ${
                            line.type === 'added'
                              ? 'text-green-300'
                              : line.type === 'removed'
                              ? 'text-red-300'
                              : 'text-slate-300'
                          }`}>{line.content}</pre>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="text-center text-slate-500">{t('versionHistory.diff.noDifferences')}</div>
              )}
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="bg-slate-900 rounded-xl shadow-2xl border border-slate-800 w-full max-w-4xl max-h-[85vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-slate-800">
          <div>
            <h2 className="text-xl font-bold text-white flex items-center gap-2">
              <Clock className="w-5 h-5 text-sky-400" />
              {t('versionHistory.title')}
            </h2>
            <p className="text-sm text-slate-400 mt-1">{fileName}</p>
          </div>
          <div className="flex items-center gap-2">
            {selectedForDiff.length === 2 && (
              <button
                onClick={handleCompareDiff}
                disabled={diffLoading}
                className="rounded-lg border border-blue-700/70 bg-blue-900/50 px-4 py-2 text-sm font-medium text-blue-200 transition hover:border-blue-500 hover:bg-blue-900/70 disabled:opacity-50 flex items-center gap-2"
              >
                {diffLoading ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    {t('versionHistory.loading')}
                  </>
                ) : (
                  <>{t('versionHistory.diff.compare', { v1: selectedForDiff[0], v2: selectedForDiff[1] })}</>
                )}
              </button>
            )}
            <button
              onClick={onClose}
              className="p-2 hover:bg-slate-800 rounded-lg transition-colors"
            >
              <X className="w-5 h-5 text-slate-400" />
            </button>
          </div>
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
              <p>{t('versionHistory.noVersions')}</p>
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
                    {/* Checkbox for Diff */}
                    <div className="flex-shrink-0 pt-1">
                      <input
                        type="checkbox"
                        checked={selectedForDiff.includes(version.id)}
                        onChange={() => handleSelectForDiff(version.id)}
                        className="w-4 h-4 rounded border-slate-600 bg-slate-800 text-blue-500 focus:ring-blue-500 focus:ring-offset-slate-900 cursor-pointer"
                        title={t('versionHistory.actions.selectForComparison')}
                      />
                    </div>

                    {/* Version Info */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="text-lg font-semibold text-white">
                          {t('versionHistory.version', { number: version.version_number })}
                        </span>
                        {isLatest && (
                          <span className="px-2 py-0.5 bg-sky-500/20 text-sky-400 text-xs font-medium rounded-full">
                            {t('versionHistory.latest')}
                          </span>
                        )}
                        {version.is_high_priority && (
                          <Star className="w-4 h-4 text-amber-400 fill-amber-400" />
                        )}
                        {version.was_cached && (
                          <span className="px-2 py-0.5 bg-violet-500/20 text-violet-400 text-xs font-medium rounded-full">
                            {t('versionHistory.cached')}
                          </span>
                        )}
                      </div>

                      {/* Metadata */}
                      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm text-slate-400 mb-2">
                        <div>
                          <span className="text-slate-500">{t('versionHistory.fields.created')}:</span>{' '}
                          {new Date(version.created_at).toLocaleString()}
                        </div>
                        <div>
                          <span className="text-slate-500">{t('versionHistory.fields.size')}:</span>{' '}
                          {formatBytes(version.file_size)}
                        </div>
                        <div>
                          <span className="text-slate-500">{t('versionHistory.fields.compressed')}:</span>{' '}
                          {formatBytes(version.compressed_size)}
                        </div>
                        <div>
                          <span className="text-slate-500">{t('versionHistory.fields.ratio')}:</span>{' '}
                          {formatCompressionRatio(version.compression_ratio)}
                        </div>
                        <div>
                          <span className="text-slate-500">{t('versionHistory.fields.savings')}:</span>{' '}
                          {formatNumber(savingsPercent, 1)}%
                        </div>
                        <div>
                          <span className="text-slate-500">{t('versionHistory.fields.storage')}:</span>{' '}
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
                        title={version.is_high_priority ? t('versionHistory.actions.removePriority') : t('versionHistory.actions.markPriority')}
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
                        title={t('versionHistory.actions.download')}
                      >
                        <Download className="w-4 h-4" />
                      </button>

                      <button
                        onClick={() => handleRestore(version.id, version.version_number)}
                        disabled={isWorking || isLatest}
                        className="p-2 text-slate-400 hover:text-green-400 hover:bg-slate-700 rounded-lg transition-colors disabled:opacity-50"
                        title={t('versionHistory.actions.restore')}
                      >
                        <RotateCcw className="w-4 h-4" />
                      </button>

                      <button
                        onClick={() => handleDelete(version.id, version.version_number)}
                        disabled={isWorking || isLatest}
                        className="p-2 text-slate-400 hover:text-red-400 hover:bg-slate-700 rounded-lg transition-colors disabled:opacity-50"
                        title={t('versionHistory.actions.delete')}
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>

                  {isWorking && (
                    <div className="mt-3 pt-3 border-t border-slate-700/50 flex items-center gap-2 text-sky-400">
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-sky-500"></div>
                      <span className="text-sm">{t('versionHistory.processing')}</span>
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
              {t('versionHistory.versionsTotal', { count: versions.length })}
            </div>
            <button
              onClick={onClose}
              className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-lg transition-colors"
            >
              {t('common.close')}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
