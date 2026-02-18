/**
 * VersionsTab - Shows commit history grouped by version tags.
 * Dev-only tab on the UpdatePage.
 */
import { useState, useEffect, useCallback } from 'react';
import { toast } from 'react-hot-toast';
import {
  ChevronDown,
  ChevronRight,
  Tag,
  Loader2,
  GitCommit,
  FileCode,
  Plus,
  Minus,
} from 'lucide-react';
import {
  getCommitHistory,
  getCommitDiff,
  type CommitHistoryResponse,
  type CommitDiffResponse,
} from '../../api/updates';
import { extractErrorMessage } from '../../lib/api';

const TYPE_COLORS: Record<string, string> = {
  feat: 'bg-emerald-500/20 text-emerald-400',
  fix: 'bg-rose-500/20 text-rose-400',
  perf: 'bg-amber-500/20 text-amber-400',
  refactor: 'bg-sky-500/20 text-sky-400',
  chore: 'bg-slate-500/20 text-slate-400',
  docs: 'bg-violet-500/20 text-violet-400',
  test: 'bg-cyan-500/20 text-cyan-400',
  style: 'bg-pink-500/20 text-pink-400',
  ci: 'bg-slate-500/20 text-slate-400',
  build: 'bg-slate-500/20 text-slate-400',
};

const STATUS_COLORS: Record<string, string> = {
  added: 'text-emerald-400',
  modified: 'text-sky-400',
  deleted: 'text-rose-400',
  renamed: 'text-amber-400',
};

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '';
  try {
    return new Date(dateStr).toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  } catch {
    return dateStr;
  }
}

export default function VersionsTab() {
  const [history, setHistory] = useState<CommitHistoryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  const [selectedCommit, setSelectedCommit] = useState<string | null>(null);
  const [diffCache, setDiffCache] = useState<Record<string, CommitDiffResponse>>({});
  const [diffLoading, setDiffLoading] = useState<string | null>(null);

  const fetchHistory = useCallback(async () => {
    setLoading(true);
    try {
      const result = await getCommitHistory();
      setHistory(result);
      // Auto-expand first group
      if (result.groups.length > 0) {
        setExpandedGroups(new Set([result.groups[0].version]));
      }
    } catch (err: unknown) {
      const detail = err != null && typeof err === 'object' && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : undefined;
      toast.error(extractErrorMessage(detail, 'Failed to load commit history'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  const toggleGroup = (version: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(version)) {
        next.delete(version);
      } else {
        next.add(version);
      }
      return next;
    });
  };

  const handleCommitClick = async (hash: string) => {
    if (selectedCommit === hash) {
      setSelectedCommit(null);
      return;
    }
    setSelectedCommit(hash);

    if (diffCache[hash]) return;

    setDiffLoading(hash);
    try {
      const diff = await getCommitDiff(hash);
      setDiffCache((prev) => ({ ...prev, [hash]: diff }));
    } catch (err: unknown) {
      const detail = err != null && typeof err === 'object' && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : undefined;
      toast.error(extractErrorMessage(detail, 'Failed to load diff'));
      setSelectedCommit(null);
    } finally {
      setDiffLoading(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-sky-500" />
      </div>
    );
  }

  if (!history || history.groups.length === 0) {
    return (
      <div className="bg-slate-800 rounded-lg border border-slate-700 p-8 text-center">
        <GitCommit className="h-12 w-12 text-slate-600 mx-auto mb-3" />
        <p className="text-slate-400">No commit history available</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {/* Summary */}
      <div className="flex items-center gap-3 mb-4 text-sm text-slate-400">
        <GitCommit className="h-4 w-4" />
        <span>{history.total_commits} commits across {history.groups.length} versions</span>
      </div>

      {/* Version Groups */}
      {history.groups.map((group) => {
        const isExpanded = expandedGroups.has(group.version);
        const isUnreleased = !group.tag;
        return (
          <div
            key={group.version}
            className={`bg-slate-800 rounded-lg border overflow-hidden ${
              isUnreleased ? 'border-amber-500/30' : 'border-slate-700'
            }`}
          >
            {/* Group Header */}
            <button
              onClick={() => toggleGroup(group.version)}
              className="w-full flex items-center gap-3 px-4 py-3 hover:bg-slate-700/50 transition-colors text-left"
            >
              {isExpanded ? (
                <ChevronDown className="h-4 w-4 text-slate-400 shrink-0" />
              ) : (
                <ChevronRight className="h-4 w-4 text-slate-400 shrink-0" />
              )}
              {isUnreleased ? (
                <GitCommit className="h-4 w-4 text-amber-400 shrink-0" />
              ) : (
                <Tag className="h-4 w-4 text-sky-400 shrink-0" />
              )}
              <span className={`font-medium ${isUnreleased ? 'text-amber-400' : 'text-white'}`}>
                {group.tag || group.version}
              </span>
              {isUnreleased && (
                <span className="text-xs text-amber-500/70">
                  HEAD is {group.commit_count} {group.commit_count === 1 ? 'commit' : 'commits'} ahead of latest tag
                </span>
              )}
              {group.date && (
                <span className="text-sm text-slate-500">
                  {formatDate(group.date)}
                </span>
              )}
              <span className={`ml-auto text-xs px-2 py-0.5 rounded ${
                isUnreleased ? 'text-amber-400 bg-amber-500/15' : 'text-slate-500 bg-slate-700'
              }`}>
                {group.commit_count} {group.commit_count === 1 ? 'commit' : 'commits'}
              </span>
            </button>

            {/* Commits */}
            {isExpanded && (
              <div className="border-t border-slate-700">
                {group.commits.map((commit) => {
                  const isSelected = selectedCommit === commit.hash;
                  const diff = diffCache[commit.hash];
                  const isLoadingDiff = diffLoading === commit.hash;

                  return (
                    <div key={commit.hash}>
                      {/* Commit Row */}
                      <button
                        onClick={() => handleCommitClick(commit.hash)}
                        className={`w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors text-sm ${
                          isSelected
                            ? 'bg-slate-700/70'
                            : 'hover:bg-slate-700/30'
                        }`}
                      >
                        <span className="font-mono text-xs text-sky-400 shrink-0 w-16">
                          {commit.hash_short}
                        </span>
                        {commit.type && (
                          <span
                            className={`px-1.5 py-0.5 rounded text-xs font-medium shrink-0 ${
                              TYPE_COLORS[commit.type] || 'bg-slate-500/20 text-slate-400'
                            }`}
                          >
                            {commit.type}
                          </span>
                        )}
                        <span className="text-slate-200 truncate">
                          {commit.message}
                        </span>
                        <span className="ml-auto text-xs text-slate-500 shrink-0">
                          {formatDate(commit.date)}
                        </span>
                        {isLoadingDiff && (
                          <Loader2 className="h-3 w-3 animate-spin text-slate-400 shrink-0" />
                        )}
                      </button>

                      {/* Diff Panel */}
                      {isSelected && diff && (
                        <div className="border-t border-slate-700/50 bg-slate-900/50 px-4 py-3">
                          {/* File list */}
                          <div className="mb-3 space-y-1">
                            <div className="flex items-center gap-2 text-xs text-slate-400 mb-2">
                              <FileCode className="h-3.5 w-3.5" />
                              <span>{diff.files.length} {diff.files.length === 1 ? 'file' : 'files'} changed</span>
                              {diff.stats && (
                                <span className="text-slate-500">({diff.stats})</span>
                              )}
                            </div>
                            {diff.files.map((file) => (
                              <div
                                key={file.path}
                                className="flex items-center gap-2 text-xs font-mono"
                              >
                                <span className={STATUS_COLORS[file.status] || 'text-slate-400'}>
                                  {file.status[0].toUpperCase()}
                                </span>
                                <span className="text-slate-300 truncate">{file.path}</span>
                                <span className="ml-auto flex items-center gap-1.5 shrink-0">
                                  {file.additions > 0 && (
                                    <span className="flex items-center gap-0.5 text-emerald-400">
                                      <Plus className="h-3 w-3" />
                                      {file.additions}
                                    </span>
                                  )}
                                  {file.deletions > 0 && (
                                    <span className="flex items-center gap-0.5 text-rose-400">
                                      <Minus className="h-3 w-3" />
                                      {file.deletions}
                                    </span>
                                  )}
                                </span>
                              </div>
                            ))}
                          </div>

                          {/* Raw Diff */}
                          {diff.diff && (
                            <div className="mt-3 border-t border-slate-700/50 pt-3">
                              <pre className="text-xs font-mono overflow-x-auto max-h-96 overflow-y-auto rounded bg-slate-950 p-3">
                                {diff.diff.split('\n').map((line, i) => {
                                  let lineClass = 'text-slate-400';
                                  if (line.startsWith('+') && !line.startsWith('+++')) {
                                    lineClass = 'text-emerald-400 bg-emerald-500/10';
                                  } else if (line.startsWith('-') && !line.startsWith('---')) {
                                    lineClass = 'text-rose-400 bg-rose-500/10';
                                  } else if (line.startsWith('@@')) {
                                    lineClass = 'text-sky-400';
                                  } else if (line.startsWith('diff --git')) {
                                    lineClass = 'text-white font-bold';
                                  }
                                  return (
                                    <div key={i} className={`${lineClass} whitespace-pre`}>
                                      {line}
                                    </div>
                                  );
                                })}
                              </pre>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
