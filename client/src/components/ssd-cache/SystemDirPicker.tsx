/**
 * SystemDirPicker — browse and select system directories for migration paths.
 * Admin-only, uses /api/ssd/migration/browse.
 */

import { useState, useEffect, useCallback } from 'react';
import {
  Folder,
  ChevronRight,
  ArrowLeft,
  Loader2,
  AlertCircle,
  Check,
  X,
  HardDrive,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { browseDirectory } from '../../api/migration';
import type { DirectoryEntry } from '../../api/migration';

interface SystemDirPickerProps {
  title?: string;
  initialPath?: string;
  onSelect: (path: string) => void;
  onClose: () => void;
}

export default function SystemDirPicker({
  title,
  initialPath = '/mnt',
  onSelect,
  onClose,
}: SystemDirPickerProps) {
  const { t } = useTranslation();
  const [currentPath, setCurrentPath] = useState(initialPath || '/mnt');
  const [entries, setEntries] = useState<DirectoryEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedPath, setSelectedPath] = useState(initialPath || '/mnt');

  const loadEntries = useCallback(async (path: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await browseDirectory(path);
      setEntries(data);
      setCurrentPath(path);
      setSelectedPath(path);
    } catch (err: unknown) {
      const detail =
        err != null && typeof err === 'object' && 'response' in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined;
      setError(detail || 'Failed to load directories');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadEntries(initialPath || '/mnt');
  }, [initialPath, loadEntries]);

  const navigateTo = (path: string) => {
    loadEntries(path);
  };

  const goUp = () => {
    if (currentPath === '/') return;
    const parent = currentPath.replace(/\/[^/]+\/?$/, '') || '/';
    navigateTo(parent);
  };

  // Build breadcrumbs from absolute path
  const parts = currentPath.split('/').filter(Boolean);

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="flex w-full max-w-lg flex-col rounded-2xl border border-slate-700/50 bg-slate-900 shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-700/30 px-5 py-4">
          <h3 className="text-lg font-semibold text-slate-100">
            {title || t('ssdCache.migration.browse', 'Browse Directory')}
          </h3>
          <button
            onClick={onClose}
            className="rounded-lg p-1 text-slate-400 hover:bg-slate-700/50 hover:text-slate-200"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Breadcrumb bar */}
        <div className="flex items-center gap-1 border-b border-slate-700/30 px-4 py-2 text-sm overflow-x-auto">
          {currentPath !== '/' && (
            <button
              onClick={goUp}
              className="mr-1 rounded p-1 text-slate-400 hover:bg-slate-700/50 hover:text-slate-200 shrink-0"
            >
              <ArrowLeft className="h-4 w-4" />
            </button>
          )}
          <button
            onClick={() => navigateTo('/')}
            className="rounded px-1.5 py-0.5 text-slate-400 hover:bg-slate-700/50 hover:text-sky-400 shrink-0"
          >
            /
          </button>
          {parts.map((part, i) => (
            <span key={i} className="flex items-center gap-1 shrink-0">
              <ChevronRight className="h-3 w-3 text-slate-600" />
              <button
                onClick={() => navigateTo('/' + parts.slice(0, i + 1).join('/'))}
                className="rounded px-1.5 py-0.5 text-slate-400 hover:bg-slate-700/50 hover:text-sky-400"
              >
                {part}
              </button>
            </span>
          ))}
        </div>

        {/* Directory list */}
        <div className="max-h-[320px] min-h-[200px] overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center gap-2 py-12 text-slate-500">
              <Loader2 className="h-5 w-5 animate-spin" />
            </div>
          ) : error ? (
            <div className="flex items-center justify-center gap-2 py-12 text-red-400">
              <AlertCircle className="h-5 w-5" />
              <span className="text-sm">{error}</span>
            </div>
          ) : entries.length === 0 ? (
            <div className="py-12 text-center text-slate-500 text-sm">
              {t('ssdCache.migration.noSubdirs', 'No subdirectories')}
            </div>
          ) : (
            <div className="divide-y divide-slate-700/20">
              {entries.map((entry) => {
                const isSelected = selectedPath === entry.path;
                return (
                  <div
                    key={entry.path}
                    className={`flex cursor-pointer items-center gap-3 px-4 py-2.5 transition-colors ${
                      isSelected ? 'bg-sky-500/10' : 'hover:bg-slate-700/30'
                    }`}
                    onClick={() => setSelectedPath(entry.path)}
                    onDoubleClick={() => navigateTo(entry.path)}
                  >
                    <Folder className="h-4 w-4 shrink-0 text-amber-400" />
                    <span className="min-w-0 flex-1 truncate text-sm text-slate-200">
                      {entry.name}
                    </span>
                    {entry.is_mountpoint && (
                      <span className="flex items-center gap-1 rounded-full bg-violet-500/20 px-2 py-0.5 text-[10px] font-medium text-violet-300 shrink-0">
                        <HardDrive className="h-3 w-3" />
                        {t('ssdCache.migration.mountpoint', 'mount')}
                      </span>
                    )}
                    {isSelected && (
                      <Check className="h-4 w-4 shrink-0 text-sky-400" />
                    )}
                    <ChevronRight
                      className="h-4 w-4 shrink-0 text-slate-600 hover:text-slate-400"
                      onClick={(e) => {
                        e.stopPropagation();
                        navigateTo(entry.path);
                      }}
                    />
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Selected path display */}
        <div className="border-t border-slate-700/30 px-4 py-2">
          <p className="truncate text-xs text-slate-500">
            {t('ssdCache.migration.selected', 'Selected')}:{' '}
            <span className="text-slate-300 font-mono">{selectedPath}</span>
          </p>
        </div>

        {/* Footer actions */}
        <div className="flex items-center justify-end gap-3 border-t border-slate-700/30 px-5 py-4">
          <button
            onClick={onClose}
            className="rounded-lg border border-slate-700/50 px-4 py-2 text-sm text-slate-400 hover:bg-slate-800"
          >
            {t('common.cancel', 'Cancel')}
          </button>
          <button
            onClick={() => onSelect(selectedPath)}
            className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-sky-500"
          >
            {t('ssdCache.migration.selectDir', 'Select')}
          </button>
        </div>
      </div>
    </div>
  );
}
