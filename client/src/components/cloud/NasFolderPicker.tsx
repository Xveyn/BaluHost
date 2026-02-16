import { useState, useEffect, useCallback } from 'react';
import {
  Folder,
  ChevronRight,
  ArrowLeft,
  Loader2,
  AlertCircle,
  FolderPlus,
  Check,
  X,
} from 'lucide-react';
import { apiClient } from '../../lib/api';

interface NasFolder {
  name: string;
  path: string;
  type: string;
}

interface NasFolderPickerProps {
  initialPath?: string;
  onSelect: (path: string) => void;
  onClose: () => void;
}

export function NasFolderPicker({ initialPath = '', onSelect, onClose }: NasFolderPickerProps) {
  const [currentPath, setCurrentPath] = useState(initialPath);
  const [folders, setFolders] = useState<NasFolder[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedPath, setSelectedPath] = useState(initialPath);
  const [creatingFolder, setCreatingFolder] = useState(false);
  const [newFolderName, setNewFolderName] = useState('');

  const loadFolders = useCallback(async (path: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiClient.get('/api/files/list', {
        params: { path: path || '/' },
      });
      const allFiles: NasFolder[] = res.data.files || [];
      setFolders(allFiles.filter((f) => f.type === 'directory'));
      setCurrentPath(path);
      setSelectedPath(path);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to load folders';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadFolders(initialPath);
  }, [initialPath, loadFolders]);

  const navigateTo = (path: string) => {
    loadFolders(path);
  };

  const goUp = () => {
    const parts = currentPath.split('/').filter(Boolean);
    parts.pop();
    navigateTo(parts.join('/'));
  };

  const handleCreateFolder = async () => {
    const trimmed = newFolderName.trim();
    if (!trimmed) return;

    try {
      const folderPath = currentPath ? `${currentPath}/${trimmed}` : trimmed;
      await apiClient.post('/api/files/folder', { path: folderPath });
      setNewFolderName('');
      setCreatingFolder(false);
      loadFolders(currentPath);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to create folder';
      setError(msg);
    }
  };

  const breadcrumbs = currentPath.split('/').filter(Boolean);

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="flex w-full max-w-lg flex-col rounded-2xl border border-slate-700/50 bg-slate-900 shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-700/30 px-5 py-4">
          <h3 className="text-lg font-semibold text-slate-100">Select Destination Folder</h3>
          <button
            onClick={onClose}
            className="rounded-lg p-1 text-slate-400 hover:bg-slate-700/50 hover:text-slate-200"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Breadcrumb bar */}
        <div className="flex items-center gap-1 border-b border-slate-700/30 px-4 py-2 text-sm">
          {currentPath !== '' && (
            <button
              onClick={goUp}
              className="mr-1 rounded p-1 text-slate-400 hover:bg-slate-700/50 hover:text-slate-200"
            >
              <ArrowLeft className="h-4 w-4" />
            </button>
          )}
          <button
            onClick={() => navigateTo('')}
            className="rounded px-1.5 py-0.5 text-slate-400 hover:bg-slate-700/50 hover:text-sky-400"
          >
            Storage Root
          </button>
          {breadcrumbs.map((part, i) => (
            <span key={i} className="flex items-center gap-1">
              <ChevronRight className="h-3 w-3 text-slate-600" />
              <button
                onClick={() => navigateTo(breadcrumbs.slice(0, i + 1).join('/'))}
                className="rounded px-1.5 py-0.5 text-slate-400 hover:bg-slate-700/50 hover:text-sky-400"
              >
                {part}
              </button>
            </span>
          ))}
        </div>

        {/* Folder list */}
        <div className="max-h-[320px] min-h-[200px] overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center gap-2 py-12 text-slate-500">
              <Loader2 className="h-5 w-5 animate-spin" />
              <span>Loading...</span>
            </div>
          ) : error ? (
            <div className="flex items-center justify-center gap-2 py-12 text-red-400">
              <AlertCircle className="h-5 w-5" />
              <span>{error}</span>
            </div>
          ) : folders.length === 0 && !creatingFolder ? (
            <div className="py-12 text-center text-slate-500">
              No subfolders
            </div>
          ) : (
            <div className="divide-y divide-slate-700/20">
              {folders
                .sort((a, b) => a.name.localeCompare(b.name))
                .map((folder) => {
                  const isSelected = selectedPath === folder.path;
                  return (
                    <div
                      key={folder.path}
                      className={`flex cursor-pointer items-center gap-3 px-4 py-2.5 transition-colors ${
                        isSelected
                          ? 'bg-sky-500/10'
                          : 'hover:bg-slate-700/30'
                      }`}
                      onClick={() => setSelectedPath(folder.path)}
                      onDoubleClick={() => navigateTo(folder.path)}
                    >
                      <Folder className="h-4 w-4 shrink-0 text-amber-400" />
                      <span className="min-w-0 flex-1 truncate text-sm text-slate-200">
                        {folder.name}
                      </span>
                      {isSelected && (
                        <Check className="h-4 w-4 shrink-0 text-sky-400" />
                      )}
                      <ChevronRight
                        className="h-4 w-4 shrink-0 text-slate-600 hover:text-slate-400"
                        onClick={(e) => {
                          e.stopPropagation();
                          navigateTo(folder.path);
                        }}
                      />
                    </div>
                  );
                })}
            </div>
          )}

          {/* New folder inline */}
          {creatingFolder && (
            <div className="flex items-center gap-2 border-t border-slate-700/30 px-4 py-2.5">
              <FolderPlus className="h-4 w-4 shrink-0 text-emerald-400" />
              <input
                type="text"
                value={newFolderName}
                onChange={(e) => setNewFolderName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleCreateFolder();
                  if (e.key === 'Escape') setCreatingFolder(false);
                }}
                placeholder="Folder name"
                autoFocus
                className="min-w-0 flex-1 bg-transparent text-sm text-slate-200 outline-none placeholder:text-slate-600"
              />
              <button
                onClick={handleCreateFolder}
                disabled={!newFolderName.trim()}
                className="rounded px-2 py-1 text-xs font-medium text-emerald-400 hover:bg-emerald-500/10 disabled:opacity-40"
              >
                Create
              </button>
              <button
                onClick={() => setCreatingFolder(false)}
                className="rounded px-2 py-1 text-xs text-slate-500 hover:bg-slate-700/50"
              >
                Cancel
              </button>
            </div>
          )}
        </div>

        {/* Selected path display */}
        <div className="border-t border-slate-700/30 px-4 py-2">
          <p className="truncate text-xs text-slate-500">
            Selected: <span className="text-slate-300">{selectedPath || '/ (storage root)'}</span>
          </p>
        </div>

        {/* Footer actions */}
        <div className="flex items-center justify-between border-t border-slate-700/30 px-5 py-4">
          <button
            onClick={() => setCreatingFolder(true)}
            disabled={creatingFolder}
            className="flex items-center gap-1.5 rounded-lg border border-slate-700/50 px-3 py-2 text-sm text-slate-400 transition-colors hover:bg-slate-800 hover:text-slate-200 disabled:opacity-40"
          >
            <FolderPlus className="h-4 w-4" />
            New Folder
          </button>
          <div className="flex gap-3">
            <button
              onClick={onClose}
              className="rounded-lg border border-slate-700/50 px-4 py-2 text-sm text-slate-400 hover:bg-slate-800"
            >
              Cancel
            </button>
            <button
              onClick={() => onSelect(selectedPath)}
              className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-sky-500"
            >
              Select
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
