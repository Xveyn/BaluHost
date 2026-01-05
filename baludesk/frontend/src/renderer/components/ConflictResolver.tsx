import { useState, useCallback } from 'react';
import { AlertCircle, FileText, Clock, HardDrive, CheckCircle, XCircle } from 'lucide-react';
import toast from 'react-hot-toast';
import { FileConflict, ConflictResolutionOption, ConflictResolution } from '../../lib/types';

interface ConflictResolverProps {
  conflicts: FileConflict[];
  onResolveConflict: (resolution: ConflictResolution) => Promise<void>;
  onResolveAll: (option: ConflictResolutionOption) => Promise<void>;
  isLoading?: boolean;
}

interface ConflictItemState {
  conflictId: string;
  resolution: ConflictResolutionOption | null;
  isResolving: boolean;
  error?: string;
}

/**
 * ConflictResolver - Handles file synchronization conflicts
 * Provides UI for viewing conflicting versions and choosing resolution strategy
 * Supports: keep-local, keep-remote, keep-both, manual
 */
export default function ConflictResolver({
  conflicts,
  onResolveConflict,
  onResolveAll,
  isLoading = false,
}: ConflictResolverProps) {
  const [conflictStates, setConflictStates] = useState<ConflictItemState[]>(
    conflicts.map((c) => ({
      conflictId: c.id,
      resolution: null,
      isResolving: false,
    }))
  );

  const [previewConflictId, setPreviewConflictId] = useState<string | null>(
    conflicts.length > 0 ? conflicts[0].id : null
  );

  const [autoResolveMode, setAutoResolveMode] = useState<ConflictResolutionOption | null>(null);

  // Handle individual conflict resolution
  const handleResolveConflict = useCallback(
    async (conflict: FileConflict, option: ConflictResolutionOption) => {
      const stateIndex = conflictStates.findIndex((s) => s.conflictId === conflict.id);
      if (stateIndex === -1) return;

      // Update state to show loading
      setConflictStates((prev) => [
        ...prev.slice(0, stateIndex),
        { ...prev[stateIndex], isResolving: true, resolution: option },
        ...prev.slice(stateIndex + 1),
      ]);

      try {
        await onResolveConflict({
          conflictId: conflict.id,
          resolution: option,
        });

        toast.success(`Conflict resolved: ${conflict.path}`);

        // Remove from list
        setConflictStates((prev) => prev.filter((s) => s.conflictId !== conflict.id));
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : 'Unknown error';
        toast.error(`Failed to resolve conflict: ${errorMsg}`);

        // Update state with error
        setConflictStates((prev) => [
          ...prev.slice(0, stateIndex),
          { ...prev[stateIndex], isResolving: false, error: errorMsg },
          ...prev.slice(stateIndex + 1),
        ]);
      }
    },
    [conflictStates, onResolveConflict]
  );

  // Handle bulk resolution
  const handleResolveAll = useCallback(
    async (option: ConflictResolutionOption) => {
      setAutoResolveMode(option);

      try {
        await onResolveAll(option);
        toast.success(`All conflicts resolved with: ${option}`);
        setConflictStates([]);
        setAutoResolveMode(null);
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : 'Unknown error';
        toast.error(`Failed to resolve conflicts: ${errorMsg}`);
        setAutoResolveMode(null);
      }
    },
    [onResolveAll]
  );

  const previewConflict = conflicts.find((c) => c.id === previewConflictId);
  const remainingConflicts = conflictStates.length;

  if (conflicts.length === 0) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-center">
          <CheckCircle className="h-12 w-12 text-green-500 mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
            No conflicts
          </h3>
          <p className="text-gray-500 dark:text-gray-400 mt-1">All files are in sync</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-white dark:bg-gray-900">
      {/* Header */}
      <div className="border-b border-gray-200 dark:border-gray-700 p-6">
        <div className="flex items-center gap-3 mb-2">
          <AlertCircle className="h-6 w-6 text-amber-500" />
          <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
            Resolve Conflicts
          </h2>
        </div>
        <p className="text-gray-600 dark:text-gray-400">
          {remainingConflicts} file{remainingConflicts !== 1 ? 's' : ''} need{remainingConflicts !== 1 ? '' : 's'} your
          attention
        </p>
      </div>

      {/* Quick Actions */}
      {remainingConflicts > 1 && (
        <div className="border-b border-gray-200 dark:border-gray-700 px-6 py-4 bg-gray-50 dark:bg-gray-800">
          <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
            Resolve all with:
          </p>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => handleResolveAll('keep-local')}
              disabled={isLoading || autoResolveMode !== null}
              className="px-3 py-2 text-sm font-medium rounded-lg bg-blue-50 dark:bg-blue-900 text-blue-700 dark:text-blue-200 hover:bg-blue-100 dark:hover:bg-blue-800 disabled:opacity-50 disabled:cursor-not-allowed transition"
            >
              Keep Local
            </button>
            <button
              onClick={() => handleResolveAll('keep-remote')}
              disabled={isLoading || autoResolveMode !== null}
              className="px-3 py-2 text-sm font-medium rounded-lg bg-green-50 dark:bg-green-900 text-green-700 dark:text-green-200 hover:bg-green-100 dark:hover:bg-green-800 disabled:opacity-50 disabled:cursor-not-allowed transition"
            >
              Keep Remote
            </button>
            <button
              onClick={() => handleResolveAll('keep-both')}
              disabled={isLoading || autoResolveMode !== null}
              className="px-3 py-2 text-sm font-medium rounded-lg bg-purple-50 dark:bg-purple-900 text-purple-700 dark:text-purple-200 hover:bg-purple-100 dark:hover:bg-purple-800 disabled:opacity-50 disabled:cursor-not-allowed transition"
            >
              Keep Both
            </button>
          </div>
        </div>
      )}

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Conflict List */}
        <div className="w-80 border-r border-gray-200 dark:border-gray-700 overflow-y-auto">
          {conflictStates.map((state) => {
            const conflict = conflicts.find((c) => c.id === state.conflictId);
            if (!conflict) return null;

            return (
              <button
                key={conflict.id}
                onClick={() => setPreviewConflictId(conflict.id)}
                className={`w-full px-4 py-4 border-b border-gray-200 dark:border-gray-700 text-left hover:bg-gray-50 dark:hover:bg-gray-800 transition ${
                  previewConflictId === conflict.id
                    ? 'bg-blue-50 dark:bg-blue-900 border-l-4 border-l-blue-500'
                    : ''
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                      {conflict.path.split('/').pop()}
                    </p>
                    <p className="text-xs text-gray-500 dark:text-gray-400 truncate mt-1">
                      {conflict.path}
                    </p>
                    <p className="text-xs text-amber-600 dark:text-amber-400 mt-2">
                      {conflict.conflictType}
                    </p>
                  </div>
                  {state.resolution && (
                    <div className="flex-shrink-0">
                      {state.isResolving ? (
                        <div className="animate-spin h-4 w-4 text-blue-500" />
                      ) : (
                        <CheckCircle className="h-4 w-4 text-green-500" />
                      )}
                    </div>
                  )}
                </div>
              </button>
            );
          })}
        </div>

        {/* Preview & Resolution */}
        {previewConflict && (
          <div className="flex-1 flex flex-col overflow-hidden">
            {/* File Path Header */}
            <div className="border-b border-gray-200 dark:border-gray-700 p-6">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                {previewConflict.path}
              </h3>
              <p className="text-sm text-gray-600 dark:text-gray-400 mt-2">
                Conflict type: <span className="font-medium">{previewConflict.conflictType}</span>
              </p>
            </div>

            {/* Version Comparison */}
            <div className="flex-1 overflow-y-auto p-6">
              <div className="grid grid-cols-2 gap-6">
                {/* Local Version */}
                <div className="flex flex-col">
                  <div className="flex items-center gap-2 mb-4">
                    <div className="h-2 w-2 bg-blue-500 rounded-full" />
                    <h4 className="font-semibold text-gray-900 dark:text-white">Local Version</h4>
                  </div>

                  {previewConflict.localVersion.exists ? (
                    <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-4 space-y-3">
                      <div className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                        <HardDrive className="h-4 w-4" />
                        <span>{formatBytes(previewConflict.localVersion.size)}</span>
                      </div>
                      <div className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                        <Clock className="h-4 w-4" />
                        <span>{formatDateTime(previewConflict.localVersion.modifiedAt)}</span>
                      </div>
                      {previewConflict.localVersion.content && (
                        <div className="mt-4 pt-4 border-t border-blue-200 dark:border-blue-700">
                          <p className="text-xs text-gray-600 dark:text-gray-400 mb-2">Preview:</p>
                          <pre className="text-xs bg-white dark:bg-gray-800 p-3 rounded border border-blue-200 dark:border-blue-700 overflow-auto max-h-40">
                            {previewConflict.localVersion.content}
                          </pre>
                        </div>
                      )}
                      <button
                        onClick={() =>
                          handleResolveConflict(previewConflict, 'keep-local')
                        }
                        disabled={conflictStates.find((s) => s.conflictId === previewConflict.id)?.isResolving}
                        className="mt-4 w-full px-3 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition"
                      >
                        Keep Local
                      </button>
                    </div>
                  ) : (
                    <div className="bg-red-50 dark:bg-red-900/20 rounded-lg p-4 flex items-center gap-2 text-red-700 dark:text-red-300">
                      <XCircle className="h-5 w-5" />
                      <span className="text-sm font-medium">File deleted locally</span>
                    </div>
                  )}
                </div>

                {/* Remote Version */}
                <div className="flex flex-col">
                  <div className="flex items-center gap-2 mb-4">
                    <div className="h-2 w-2 bg-green-500 rounded-full" />
                    <h4 className="font-semibold text-gray-900 dark:text-white">Remote Version</h4>
                  </div>

                  {previewConflict.remoteVersion.exists ? (
                    <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-4 space-y-3">
                      <div className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                        <HardDrive className="h-4 w-4" />
                        <span>{formatBytes(previewConflict.remoteVersion.size)}</span>
                      </div>
                      <div className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                        <Clock className="h-4 w-4" />
                        <span>{formatDateTime(previewConflict.remoteVersion.modifiedAt)}</span>
                      </div>
                      {previewConflict.remoteVersion.content && (
                        <div className="mt-4 pt-4 border-t border-green-200 dark:border-green-700">
                          <p className="text-xs text-gray-600 dark:text-gray-400 mb-2">Preview:</p>
                          <pre className="text-xs bg-white dark:bg-gray-800 p-3 rounded border border-green-200 dark:border-green-700 overflow-auto max-h-40">
                            {previewConflict.remoteVersion.content}
                          </pre>
                        </div>
                      )}
                      <button
                        onClick={() =>
                          handleResolveConflict(previewConflict, 'keep-remote')
                        }
                        disabled={conflictStates.find((s) => s.conflictId === previewConflict.id)?.isResolving}
                        className="mt-4 w-full px-3 py-2 bg-green-600 hover:bg-green-700 text-white text-sm font-medium rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition"
                      >
                        Keep Remote
                      </button>
                    </div>
                  ) : (
                    <div className="bg-red-50 dark:bg-red-900/20 rounded-lg p-4 flex items-center gap-2 text-red-700 dark:text-red-300">
                      <XCircle className="h-5 w-5" />
                      <span className="text-sm font-medium">File deleted remotely</span>
                    </div>
                  )}
                </div>
              </div>

              {/* Keep Both Option */}
              {previewConflict.localVersion.exists && previewConflict.remoteVersion.exists && (
                <div className="mt-6 pt-6 border-t border-gray-200 dark:border-gray-700">
                  <button
                    onClick={() => handleResolveConflict(previewConflict, 'keep-both')}
                    disabled={conflictStates.find((s) => s.conflictId === previewConflict.id)?.isResolving}
                    className="w-full px-4 py-3 bg-purple-100 dark:bg-purple-900 text-purple-700 dark:text-purple-300 font-medium rounded-lg hover:bg-purple-200 dark:hover:bg-purple-800 disabled:opacity-50 disabled:cursor-not-allowed transition"
                  >
                    Keep Both Versions
                  </button>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-2 text-center">
                    Remote version will be renamed with .conflict suffix
                  </p>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Utility Functions
 */
function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function formatDateTime(dateString: string): string {
  try {
    const date = new Date(dateString);
    return date.toLocaleString('de-DE', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return dateString;
  }
}
