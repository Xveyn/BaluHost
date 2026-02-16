import { useState, useEffect, useCallback } from 'react';
import { Folder, File, ChevronRight, ArrowLeft, Loader2, AlertCircle, Check } from 'lucide-react';
import { browseFiles, type CloudFile } from '../../api/cloud-import';
import { formatBytes } from '../../lib/formatters';

interface CloudFileBrowserProps {
  connectionId: number;
  selectedPaths: Set<string>;
  onTogglePath: (path: string, isDirectory: boolean) => void;
}

export function CloudFileBrowser({ connectionId, selectedPaths, onTogglePath }: CloudFileBrowserProps) {
  const [currentPath, setCurrentPath] = useState('/');
  const [files, setFiles] = useState<CloudFile[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadFiles = useCallback(async (path: string) => {
    setLoading(true);
    setError(null);
    try {
      const result = await browseFiles(connectionId, path);
      setFiles(result);
      setCurrentPath(path);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to load files';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [connectionId]);

  useEffect(() => {
    loadFiles('/');
  }, [connectionId, loadFiles]);

  const navigateTo = (path: string) => {
    loadFiles(path);
  };

  const goUp = () => {
    const parts = currentPath.split('/').filter(Boolean);
    parts.pop();
    navigateTo('/' + parts.join('/'));
  };

  // Breadcrumbs
  const breadcrumbs = currentPath.split('/').filter(Boolean);

  return (
    <div className="flex flex-col rounded-2xl border border-slate-800/60 bg-slate-900/55 backdrop-blur-xl shadow-[0_20px_60px_rgba(2,6,23,0.55)]">
      {/* Breadcrumb bar */}
      <div className="flex items-center gap-1 border-b border-slate-700/30 px-3 py-2 text-sm">
        {currentPath !== '/' && (
          <button
            onClick={goUp}
            className="mr-1 rounded p-1 text-slate-400 hover:bg-slate-700/50 hover:text-slate-200"
          >
            <ArrowLeft className="h-4 w-4" />
          </button>
        )}
        <button
          onClick={() => navigateTo('/')}
          className="rounded px-1.5 py-0.5 text-slate-400 hover:bg-slate-700/50 hover:text-sky-400"
        >
          Root
        </button>
        {breadcrumbs.map((part, i) => (
          <span key={i} className="flex items-center gap-1">
            <ChevronRight className="h-3 w-3 text-slate-600" />
            <button
              onClick={() => navigateTo('/' + breadcrumbs.slice(0, i + 1).join('/'))}
              className="rounded px-1.5 py-0.5 text-slate-400 hover:bg-slate-700/50 hover:text-sky-400"
            >
              {part}
            </button>
          </span>
        ))}
      </div>

      {/* File list */}
      <div className="max-h-[400px] overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center gap-2 py-12 text-slate-500">
            <Loader2 className="h-5 w-5 animate-spin" />
            <span>Loading files...</span>
          </div>
        ) : error ? (
          <div className="flex items-center justify-center gap-2 py-12 text-red-400">
            <AlertCircle className="h-5 w-5" />
            <span>{error}</span>
          </div>
        ) : files.length === 0 ? (
          <div className="py-12 text-center text-slate-500">
            Empty folder
          </div>
        ) : (
          <div className="divide-y divide-slate-700/20">
            {/* Directories first, then files */}
            {[...files]
              .sort((a, b) => {
                if (a.is_directory !== b.is_directory) return a.is_directory ? -1 : 1;
                return a.name.localeCompare(b.name);
              })
              .map((file) => {
                const isSelected = selectedPaths.has(file.path);
                return (
                  <div
                    key={file.path}
                    className={`flex items-center gap-3 px-3 py-2 transition-colors ${
                      isSelected
                        ? 'bg-sky-500/10'
                        : 'hover:bg-slate-700/30'
                    }`}
                  >
                    {/* Checkbox */}
                    <button
                      onClick={() => onTogglePath(file.path, file.is_directory)}
                      className={`flex h-5 w-5 shrink-0 items-center justify-center rounded border transition-colors ${
                        isSelected
                          ? 'border-sky-500 bg-sky-500 text-white'
                          : 'border-slate-600 hover:border-slate-400'
                      }`}
                    >
                      {isSelected && <Check className="h-3 w-3" />}
                    </button>

                    {/* Icon + name (clickable for dirs) */}
                    <div
                      className={`flex min-w-0 flex-1 items-center gap-2 ${
                        file.is_directory ? 'cursor-pointer' : ''
                      }`}
                      onClick={() => file.is_directory && navigateTo(file.path)}
                    >
                      {file.is_directory ? (
                        <Folder className="h-4 w-4 shrink-0 text-amber-400" />
                      ) : (
                        <File className="h-4 w-4 shrink-0 text-slate-500" />
                      )}
                      <span className={`truncate text-sm ${
                        file.is_directory ? 'text-slate-200 hover:text-sky-400' : 'text-slate-400'
                      }`}>
                        {file.name}
                      </span>
                    </div>

                    {/* Size */}
                    {file.size_bytes != null && !file.is_directory && (
                      <span className="shrink-0 text-xs text-slate-600">
                        {formatBytes(file.size_bytes)}
                      </span>
                    )}

                    {/* Modified date */}
                    {file.modified_at && (
                      <span className="hidden shrink-0 text-xs text-slate-600 sm:block">
                        {new Date(file.modified_at).toLocaleDateString()}
                      </span>
                    )}

                    {/* Navigate arrow for dirs */}
                    {file.is_directory && (
                      <ChevronRight
                        className="h-4 w-4 shrink-0 cursor-pointer text-slate-600 hover:text-slate-400"
                        onClick={() => navigateTo(file.path)}
                      />
                    )}
                  </div>
                );
              })}
          </div>
        )}
      </div>
    </div>
  );
}
