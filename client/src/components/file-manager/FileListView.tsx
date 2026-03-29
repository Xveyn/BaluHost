import {
  Eye,
  Download,
  Clock,
  Pencil,
  Trash2,
  Settings2,
  Loader2,
  FolderOpen,
  File as FileIcon,
  Users,
  UserCheck,
  Monitor,
  Share2,
  Shield,
  ShieldOff,
} from 'lucide-react';
import { formatBytes } from '../../lib/formatters';
import type { FileItem } from './types';
import { useSortableTable } from '../../hooks/useSortableTable';
import { SortableHeader } from '../ui/SortableHeader';

export interface FileListViewProps {
  files: FileItem[];
  versionCounts: Record<number, number>;
  userCache: Record<string, string>;
  loading: boolean;
  dragActive: boolean;
  isCurrentUserOwnerOrAdmin: (ownerId: number | undefined) => boolean;
  onNavigate: (folderPath: string) => void;
  onView: (file: FileItem) => void;
  onDownload: (file: FileItem) => void;
  onRename: (file: FileItem) => void;
  onDelete: (file: FileItem) => void;
  onVersionHistory: (file: FileItem) => void;
  onShare: (file: FileItem) => void;
  onEditPermissions: (file: FileItem) => void;
  onTransferOwnership: (file: FileItem) => void;
  onToggleTracking?: (file: FileItem) => void;
  trackingStatus?: Record<number, boolean>;  // file_id -> is_tracked
  vclMode?: 'automatic' | 'manual';
  onDragEnter: (e: React.DragEvent) => void;
  onDragLeave: (e: React.DragEvent) => void;
  onDragOver: (e: React.DragEvent) => void;
  onDrop: (e: React.DragEvent) => void;
}

/** Resolve a display name for the file owner. */
function renderOwnerName(
  file: FileItem,
  userCache: Record<string, string>
): string {
  if (file.ownerName && file.ownerName !== 'null') return file.ownerName;
  if (file.ownerId !== undefined && file.ownerId !== null && userCache[file.ownerId])
    return userCache[file.ownerId];
  if (file.ownerId !== undefined && file.ownerId !== null) return `UID ${file.ownerId}`;
  return '\u2014';
}

/** Render the icon badge for a file or directory. */
function renderFileIcon(file: FileItem, size: 'sm' | 'md' = 'sm') {
  const iconSize = size === 'md' ? 'h-5 w-5' : 'h-4 w-4';
  const containerSize = size === 'md' ? 'h-10 w-10' : 'h-9 w-9';

  return (
    <span className={`flex ${containerSize} items-center justify-center rounded-xl border ${
      file.type === 'directory'
        ? file.name === 'Shared'
          ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-300'
          : 'border-sky-500/20 bg-sky-500/10 text-sky-300'
        : 'border-slate-700/50 bg-slate-800/50 text-slate-400'
    }`}>
      {file.type === 'directory'
        ? file.name === 'Shared' ? <Users className={iconSize} /> : <FolderOpen className={iconSize} />
        : <FileIcon className={iconSize} />}
    </span>
  );
}

/**
 * Check if the current user can perform an action on a file.
 * Returns true if user is owner/admin, or if the share permission is explicitly granted.
 * When permission is undefined (own files, admin), defaults to owner/admin check.
 */
function canPerformAction(
  isOwnerOrAdmin: boolean,
  sharePermission: boolean | undefined,
): boolean {
  if (isOwnerOrAdmin) return true;
  return sharePermission === true;
}

export function FileListView({
  files,
  versionCounts,
  userCache,
  loading: _loading,
  dragActive: _dragActive,
  isCurrentUserOwnerOrAdmin,
  onNavigate,
  onView,
  onDownload,
  onRename,
  onDelete,
  onVersionHistory,
  onShare,
  onEditPermissions,
  onTransferOwnership,
  onToggleTracking,
  trackingStatus,
  vclMode,
  onDragEnter,
  onDragLeave,
  onDragOver,
  onDrop,
}: FileListViewProps) {
  const { sortedData, sortKey, sortDirection, toggleSort } = useSortableTable(files, {
    getValueForSort: {
      owner: (file) => renderOwnerName(file, userCache),
    },
  });
  return (
    <div
      className={`card border-slate-800/60 bg-slate-900/55 transition-all relative ${_dragActive ? 'border-sky-500 bg-sky-500/10' : ''}`}
      onDragEnter={onDragEnter}
      onDragLeave={onDragLeave}
      onDragOver={onDragOver}
      onDrop={onDrop}
    >
      {_loading && files.length > 0 && (
        <div className="absolute top-2 right-2 z-10 flex items-center gap-2 rounded-lg border border-sky-500/30 bg-sky-500/10 px-3 py-1.5 text-xs text-sky-200">
          <Loader2 className="h-3 w-3 animate-spin" />
          Updating...
        </div>
      )}
      {_dragActive && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-sky-500/20 backdrop-blur-sm rounded-2xl border-2 border-dashed border-sky-500">
          <p className="text-lg font-semibold text-sky-200">Drop files or folders here</p>
        </div>
      )}

      {/* Desktop Table View */}
      <div className="hidden lg:block overflow-x-auto">
        <table className="min-w-full">
          <thead className="bg-slate-800/30 border-b border-slate-700/50">
            <tr>
              <SortableHeader label="Name" sortKey="name" activeSortKey={sortKey} sortDirection={sortDirection} onSort={toggleSort} className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider" />
              <th className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">Type</th>
              <SortableHeader label="Size" sortKey="size" activeSortKey={sortKey} sortDirection={sortDirection} onSort={toggleSort} className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider" />
              <SortableHeader label="Modified" sortKey="modifiedAt" activeSortKey={sortKey} sortDirection={sortDirection} onSort={toggleSort} className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider" />
              <SortableHeader label="Owner" sortKey="owner" activeSortKey={sortKey} sortDirection={sortDirection} onSort={toggleSort} className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider" />
              <th className="px-4 sm:px-6 py-3 sm:py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {sortedData.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-6 py-12 text-center text-sm text-slate-500">
                  No files found
                </td>
              </tr>
            ) : (
              sortedData.map((file) => (
                <tr
                  key={file.path}
                  className="hover:bg-slate-800/30 transition-colors"
                >
                  <td
                    className="px-4 sm:px-6 py-4"
                    onClick={() => file.type === 'directory' && onNavigate(file.path)}
                  >
                    <div className="flex cursor-pointer items-center gap-3 text-sm text-slate-200">
                      {renderFileIcon(file)}
                      <div className="flex items-center gap-2 min-w-0 flex-1">
                        <span className="truncate font-medium hover:text-white transition-colors">
                          {file.name}
                        </span>
                        {file.type === 'file' && file.file_id && versionCounts[file.file_id] > 0 && (
                          <span className="shrink-0 inline-flex items-center gap-1 rounded-full bg-sky-500/20 border border-sky-500/30 px-2 py-0.5 text-[10px] font-semibold text-sky-200">
                            <Clock className="h-3 w-3" />
                            {versionCounts[file.file_id]}
                          </span>
                        )}
                        {file.syncInfo && file.syncInfo.length > 0 && (
                          <span
                            className="shrink-0 inline-flex items-center gap-1 rounded-full bg-teal-500/20 border border-teal-500/30 px-2 py-0.5 text-[10px] font-semibold text-teal-200"
                            title={file.syncInfo.map(s =>
                              `${s.deviceName} (${s.platform}, ${s.syncDirection})`
                            ).join('\n')}
                          >
                            <Monitor className="h-3 w-3" />
                            {file.syncInfo.length === 1
                              ? file.syncInfo[0].deviceName
                              : `${file.syncInfo.length} devices`}
                          </span>
                        )}
                      </div>
                    </div>
                  </td>
                  <td className="px-4 sm:px-6 py-4 text-xs uppercase tracking-wider text-slate-500">
                    {file.type}
                  </td>
                  <td className="px-4 sm:px-6 py-4 text-sm text-slate-400">
                    {file.type === 'file' || file.size > 0 ? formatBytes(file.size) : '\u2014'}
                  </td>
                  <td className="px-4 sm:px-6 py-4 text-sm text-slate-500">
                    {new Date(file.modifiedAt).toLocaleString()}
                  </td>
                  <td className="px-4 sm:px-6 py-4 text-sm text-sky-400 font-mono">
                    {renderOwnerName(file, userCache)}
                  </td>
                  <td className="px-4 sm:px-6 py-4 text-sm">
                    <div className="flex flex-wrap items-center gap-1.5">
                      {file.type === 'file' && (
                        <>
                          <button
                            onClick={() => onView(file)}
                            className="p-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 text-emerald-200 transition hover:border-emerald-500/50 hover:bg-emerald-500/20"
                            title="View"
                          >
                            <Eye className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => onDownload(file)}
                            className="p-2 rounded-lg border border-sky-500/30 bg-sky-500/10 text-sky-200 transition hover:border-sky-500/50 hover:bg-sky-500/20"
                            title="Download"
                          >
                            <Download className="w-4 h-4" />
                          </button>
                        </>
                      )}
                      {file.file_id && isCurrentUserOwnerOrAdmin(file.ownerId) && (
                        <button
                          onClick={() => onShare(file)}
                          className="p-2 rounded-lg border border-teal-500/30 bg-teal-500/10 text-teal-200 transition hover:border-teal-500/50 hover:bg-teal-500/20"
                          title="Share"
                        >
                          <Share2 className="w-4 h-4" />
                        </button>
                      )}
                      {file.file_id && onToggleTracking && (
                        (() => {
                          const isTracked = trackingStatus?.[file.file_id!] ?? (vclMode !== 'manual');
                          return (
                            <button
                              onClick={() => onToggleTracking(file)}
                              className={`p-2 rounded-lg border transition ${
                                isTracked
                                  ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200 hover:border-emerald-500/50 hover:bg-emerald-500/20'
                                  : 'border-slate-700/30 bg-slate-800/30 text-slate-500 hover:border-slate-600 hover:text-slate-300'
                              }`}
                              title={isTracked ? 'VCL: Tracked' : 'VCL: Not tracked'}
                            >
                              {isTracked ? <Shield className="w-4 h-4" /> : <ShieldOff className="w-4 h-4" />}
                            </button>
                          );
                        })()
                      )}
                      {file.type === 'file' && file.file_id && (
                        <button
                          onClick={() => onVersionHistory(file)}
                          className="p-2 rounded-lg border border-violet-500/30 bg-violet-500/10 text-violet-200 transition hover:border-violet-500/50 hover:bg-violet-500/20 relative"
                          title="Versions"
                        >
                          <Clock className="w-4 h-4" />
                          {versionCounts[file.file_id] > 0 && (
                            <span className="absolute -top-1 -right-1 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-violet-500/30 px-1 text-[9px] font-bold text-violet-200">
                              {versionCounts[file.file_id]}
                            </span>
                          )}
                        </button>
                      )}
                      {canPerformAction(isCurrentUserOwnerOrAdmin(file.ownerId), file.canWrite) && (
                        <button
                          onClick={() => onRename(file)}
                          className="p-2 rounded-lg border border-slate-700/50 bg-slate-800/50 text-slate-300 transition hover:border-slate-600 hover:text-white"
                          title="Rename"
                        >
                          <Pencil className="w-4 h-4" />
                        </button>
                      )}
                      {canPerformAction(isCurrentUserOwnerOrAdmin(file.ownerId), file.canDelete) && (
                        <button
                          onClick={() => onDelete(file)}
                          className="p-2 rounded-lg border border-rose-500/30 bg-rose-500/10 text-rose-200 transition hover:border-rose-500/50 hover:bg-rose-500/20"
                          title="Delete"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      )}
                      {isCurrentUserOwnerOrAdmin(file.ownerId) && (
                        <button
                          onClick={() => onEditPermissions(file)}
                          className="p-2 rounded-lg border border-indigo-500/30 bg-indigo-500/10 text-indigo-200 transition hover:border-indigo-500/50 hover:bg-indigo-500/20"
                          title="Permissions"
                        >
                          <Settings2 className="w-4 h-4" />
                        </button>
                      )}
                      {isCurrentUserOwnerOrAdmin(file.ownerId) && (
                        <button
                          onClick={() => onTransferOwnership(file)}
                          className="p-2 rounded-lg border border-amber-500/30 bg-amber-500/10 text-amber-200 transition hover:border-amber-500/50 hover:bg-amber-500/20"
                          title="Transfer Ownership"
                        >
                          <UserCheck className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Mobile Card View */}
      <div className="lg:hidden space-y-3">
        {sortedData.length === 0 ? (
          <div className="py-12 text-center text-sm text-slate-500">
            No files found
          </div>
        ) : (
          sortedData.map((file) => (
            <div
              key={file.path}
              className="rounded-xl border border-slate-800/60 bg-slate-950/70 p-4 space-y-3 touch-manipulation active:bg-slate-900/50 transition"
            >
              {/* File Header */}
              <div
                onClick={() => file.type === 'directory' && onNavigate(file.path)}
                className="flex items-center gap-3 cursor-pointer"
              >
                {renderFileIcon(file, 'md')}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium text-slate-200 truncate">{file.name}</p>
                    {file.type === 'file' && file.file_id && versionCounts[file.file_id] > 0 && (
                      <span className="shrink-0 inline-flex items-center gap-1 rounded-full bg-sky-500/20 border border-sky-500/30 px-2 py-0.5 text-[10px] font-semibold text-sky-200">
                        <Clock className="h-2.5 w-2.5" />
                        {versionCounts[file.file_id]}
                      </span>
                    )}
                    {file.syncInfo && file.syncInfo.length > 0 && (
                      <span
                        className="shrink-0 inline-flex items-center gap-1 rounded-full bg-teal-500/20 border border-teal-500/30 px-2 py-0.5 text-[10px] font-semibold text-teal-200"
                        title={file.syncInfo.map(s =>
                          `${s.deviceName} (${s.platform}, ${s.syncDirection})`
                        ).join('\n')}
                      >
                        <Monitor className="h-2.5 w-2.5" />
                        {file.syncInfo.length === 1
                          ? file.syncInfo[0].deviceName
                          : `${file.syncInfo.length} devices`}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 mt-1 text-xs text-slate-500">
                    <span className="uppercase tracking-wider">{file.type}</span>
                    {(file.type === 'file' || file.size > 0) && (
                      <>
                        <span>&middot;</span>
                        <span>{formatBytes(file.size)}</span>
                      </>
                    )}
                  </div>
                </div>
              </div>

              {/* File Meta */}
              <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-500">
                <div>
                  <span className="text-slate-600">Modified: </span>
                  {new Date(file.modifiedAt).toLocaleDateString()}
                </div>
                <div>
                  <span className="text-slate-600">Owner: </span>
                  <span className="text-sky-400 font-mono">
                    {renderOwnerName(file, userCache)}
                  </span>
                </div>
              </div>

              {/* Actions */}
              <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-slate-800/40">
                {file.type === 'file' && (
                  <>
                    <button
                      onClick={() => onView(file)}
                      className="flex-1 flex items-center justify-center gap-1.5 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs font-medium text-emerald-200 transition hover:border-emerald-500/50 hover:bg-emerald-500/20 touch-manipulation active:scale-95"
                    >
                      <Eye className="w-3.5 h-3.5" />
                      View
                    </button>
                    <button
                      onClick={() => onDownload(file)}
                      className="flex-1 flex items-center justify-center gap-1.5 rounded-lg border border-sky-500/30 bg-sky-500/10 px-3 py-2 text-xs font-medium text-sky-200 transition hover:border-sky-500/50 hover:bg-sky-500/20 touch-manipulation active:scale-95"
                    >
                      <Download className="w-3.5 h-3.5" />
                      Download
                    </button>
                  </>
                )}
                {file.file_id && isCurrentUserOwnerOrAdmin(file.ownerId) && (
                  <button
                    onClick={() => onShare(file)}
                    className="flex-1 flex items-center justify-center gap-1.5 rounded-lg border border-teal-500/30 bg-teal-500/10 px-3 py-2 text-xs font-medium text-teal-200 transition hover:border-teal-500/50 hover:bg-teal-500/20 touch-manipulation active:scale-95"
                  >
                    <Share2 className="w-3.5 h-3.5" />
                    Share
                  </button>
                )}
                {file.file_id && onToggleTracking && (
                  (() => {
                    const isTracked = trackingStatus?.[file.file_id!] ?? (vclMode !== 'manual');
                    return (
                      <button
                        onClick={() => onToggleTracking(file)}
                        className={`flex-1 flex items-center justify-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-medium transition touch-manipulation active:scale-95 ${
                          isTracked
                            ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200 hover:border-emerald-500/50'
                            : 'border-slate-700/30 bg-slate-800/30 text-slate-400 hover:text-slate-300'
                        }`}
                      >
                        {isTracked ? <Shield className="w-3.5 h-3.5" /> : <ShieldOff className="w-3.5 h-3.5" />}
                        VCL
                      </button>
                    );
                  })()
                )}
                {file.type === 'file' && file.file_id && (
                  <button
                    onClick={() => onVersionHistory(file)}
                    className="w-full flex items-center justify-center gap-1.5 rounded-lg border border-violet-500/30 bg-violet-500/10 px-3 py-2 text-xs font-medium text-violet-200 transition hover:border-violet-500/50 hover:bg-violet-500/20 touch-manipulation active:scale-95"
                  >
                    <Clock className="w-3.5 h-3.5" />
                    Versions
                    {versionCounts[file.file_id] > 0 && (
                      <span className="inline-flex items-center justify-center rounded-full bg-violet-400/20 px-1.5 py-0.5 text-[10px] font-bold">
                        {versionCounts[file.file_id]}
                      </span>
                    )}
                  </button>
                )}
                {canPerformAction(isCurrentUserOwnerOrAdmin(file.ownerId), file.canWrite) && (
                  <button
                    onClick={() => onRename(file)}
                    className="flex-1 flex items-center justify-center gap-1.5 rounded-lg border border-slate-700/50 bg-slate-800/50 px-3 py-2 text-xs font-medium text-slate-300 transition hover:border-slate-600 hover:text-white touch-manipulation active:scale-95"
                  >
                    <Pencil className="w-3.5 h-3.5" />
                    Rename
                  </button>
                )}
                {canPerformAction(isCurrentUserOwnerOrAdmin(file.ownerId), file.canDelete) && (
                  <button
                    onClick={() => onDelete(file)}
                    className="flex-1 flex items-center justify-center gap-1.5 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs font-medium text-rose-200 transition hover:border-rose-500/50 hover:bg-rose-500/20 touch-manipulation active:scale-95"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                )}
                {isCurrentUserOwnerOrAdmin(file.ownerId) && (
                  <button
                    onClick={() => onTransferOwnership(file)}
                    className="flex-1 flex items-center justify-center gap-1.5 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs font-medium text-amber-200 transition hover:border-amber-500/50 hover:bg-amber-500/20 touch-manipulation active:scale-95"
                  >
                    <UserCheck className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
