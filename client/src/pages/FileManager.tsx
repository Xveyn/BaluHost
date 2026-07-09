import { useState, useEffect, useMemo, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import {
  FolderPlus,
  FolderUp,
  Upload,
  Archive,
  Home,
  Loader2,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { getFilePermissions, setFilePermissions } from '../api/files';
import { getShareableUsers } from '../api/shares';
import { VersionHistoryModal } from '../components/vcl/VersionHistoryModal';
import { formatBytes, formatNumber } from '../lib/formatters';
import { FileViewer } from '../components/file-manager/FileViewer';
import { StorageSelector } from '../components/file-manager/StorageSelector';
import { PermissionEditor } from '../components/file-manager/PermissionEditor';
import { OwnershipTransferModal } from '../components/file-manager/OwnershipTransferModal';
import { FileListView } from '../components/file-manager/FileListView';
import { NewFolderDialog } from '../components/file-manager/NewFolderDialog';
import { DeleteDialog } from '../components/file-manager/DeleteDialog';
import { RenameDialog } from '../components/file-manager/RenameDialog';
import { useUpload } from '../contexts/UploadContext';
import ShareFileModal from '../components/ShareFileModal';
import { useFileBrowser } from '../hooks/useFileBrowser';
import { useVclFileInfo } from '../hooks/useVclFileInfo';
import { useFileUpload } from '../hooks/useFileUpload';
import { buildOwnerNameCache } from '../components/file-manager/utils';
import type { FileItem, PermissionRule } from '../components/file-manager/types';

export default function FileManager() {
  const { user } = useAuth();
  const { t } = useTranslation(['fileManager', 'common']);

  // User list
  const [allUsers, setAllUsers] = useState<Array<{ id: number; username: string }>>([]);

  useEffect(() => {
    getShareableUsers()
      .then(users => setAllUsers(users))
      .catch(() => {});
  }, []);

  // Permission modal state
  const [showEditPermissionsModal, setShowEditPermissionsModal] = useState(false);
  const [fileToEditPermissions, setFileToEditPermissions] = useState<FileItem | null>(null);
  const [editRules, setEditRules] = useState<PermissionRule[]>([]);

  // Ownership transfer modal state
  const [showOwnershipModal, setShowOwnershipModal] = useState(false);
  const [fileToTransfer, setFileToTransfer] = useState<FileItem | null>(null);

  // Share modal state
  const [sharingFile, setSharingFile] = useState<FileItem | null>(null);

  function isCurrentUserOwnerOrAdmin(ownerId: number | undefined) {
    if (!user) return false;
    return user.role === 'admin' || String(ownerId) === String(user.id);
  }

  async function handleEditPermissionsSave() {
    if (!fileToEditPermissions) return;
    try {
      await setFilePermissions({
        path: fileToEditPermissions.path,
        owner_id: fileToEditPermissions.ownerId ?? user?.id ?? 0,
        rules: editRules.map(rule => ({
          user_id: Number(rule.userId),
          can_view: rule.canView,
          can_edit: rule.canEdit,
          can_delete: rule.canDelete,
        }))
      });
      toast.success(t('fileManager:messages.permissionsSaved'));
    } catch {
      toast.error(t('fileManager:messages.permissionsError'));
    }
    setShowEditPermissionsModal(false);
    setFileToEditPermissions(null);
  }

  const {
    mountpoints, selectedMountpoint, selectMountpoint,
    currentPath, getFullPath, navigateToFolder, goBack, goHome,
    files, loading, storageInfo,
    createFolder, deleteFile, renameFile, downloadFile, refresh,
  } = useFileBrowser();
  const {
    vclQuota, userRootUsageBytes, versionCounts, trackingStatus, vclMode,
    toggleTracking, refreshVcl,
  } = useVclFileInfo(files);
  const {
    dragActive, isUploading, handleUpload, handleFolderUpload, handleDrag, handleDrop,
  } = useFileUpload({ getFullPath, availableBytes: storageInfo?.availableBytes });
  const userCache = useMemo(() => buildOwnerNameCache(files), [files]);
  const { onUploadsComplete } = useUpload();
  const [showNewFolderDialog, setShowNewFolderDialog] = useState(false);
  const [newFolderName, setNewFolderName] = useState('');
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [fileToDelete, setFileToDelete] = useState<FileItem | null>(null);
  const [showRenameDialog, setShowRenameDialog] = useState(false);
  const [fileToRename, setFileToRename] = useState<FileItem | null>(null);
  const [newFileName, setNewFileName] = useState('');
  const [viewingFile, setViewingFile] = useState<FileItem | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  // VCL State
  const [showVersionHistory, setShowVersionHistory] = useState(false);
  const [versionHistoryFile, setVersionHistoryFile] = useState<FileItem | null>(null);

  // Reload files + storage when uploads complete
  useEffect(() => {
    return onUploadsComplete(() => {
      refresh();
      refreshVcl();
    });
  }, [onUploadsComplete, refresh, refreshVcl]);

  if (!user) return null;

  const confirmDelete = (file: FileItem) => {
    setFileToDelete(file);
    setShowDeleteDialog(true);
  };

  const startRename = (file: FileItem) => {
    setFileToRename(file);
    setNewFileName(file.name);
    setShowRenameDialog(true);
  };

  const handleViewFile = (file: FileItem) => {
    setViewingFile(file);
  };

  const handleEditPermissionsClick = async (file: FileItem) => {
    setFileToEditPermissions(file);
    setShowEditPermissionsModal(true);
    try {
      const perms = await getFilePermissions(file.path);
      if (Array.isArray(perms.rules) && perms.rules.length > 0) {
        setEditRules(perms.rules.map((rule: { user_id: number; can_view: boolean; can_edit: boolean; can_delete: boolean }) => ({
          userId: String(rule.user_id),
          canView: rule.can_view,
          canEdit: rule.can_edit,
          canDelete: rule.can_delete,
        })));
      } else {
        setEditRules([{
          userId: String(perms.owner_id ?? ''),
          canView: true,
          canEdit: true,
          canDelete: true,
        }]);
      }
    } catch {
      setEditRules([{
        userId: String(file.ownerId ?? ''),
        canView: true,
        canEdit: true,
        canDelete: true,
      }]);
    }
  };

  const handleVersionHistory = (file: FileItem) => {
    setVersionHistoryFile(file);
    setShowVersionHistory(true);
  };

  const handleTransferOwnershipClick = (file: FileItem) => {
    setFileToTransfer(file);
    setShowOwnershipModal(true);
  };

  const handleShareFile = (file: FileItem) => {
    setSharingFile(file);
  };

  return (
    <div className="space-y-6 min-w-0">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-semibold text-white">
            File Manager
          </h1>
          <p className="mt-1 text-xs sm:text-sm text-slate-400">Browse, upload, and organise your vaults</p>
          {storageInfo && (
            <p className="mt-1 text-xs text-slate-500">
              {formatBytes(storageInfo.usedBytes)} / {formatBytes(storageInfo.totalBytes)} used
              <span className="ml-2 text-sky-400">({formatBytes(storageInfo.availableBytes)} available)</span>
            </p>
          )}
          {selectedMountpoint?.breakdown && (
            <p className="mt-0.5 text-[11px] text-slate-500">
              <span className="text-slate-400">Files: {formatBytes(selectedMountpoint.breakdown.user_files_bytes)}</span>
              {selectedMountpoint.breakdown.cache_bytes > 0 && (
                <span className="ml-2 text-amber-400/80">Cache: {formatBytes(selectedMountpoint.breakdown.cache_bytes)}</span>
              )}
              {selectedMountpoint.breakdown.vcl_bytes > 0 && (
                <span className="ml-2 text-violet-400/80">VCL: {formatBytes(selectedMountpoint.breakdown.vcl_bytes)}</span>
              )}
            </p>
          )}
          {vclQuota && (
            <div className="mt-1">
              <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold border ${
                vclQuota.warning === 'critical'
                  ? 'border-rose-500/40 bg-rose-500/15 text-rose-300'
                  : vclQuota.warning === 'warning'
                  ? 'border-amber-500/40 bg-amber-500/15 text-amber-300'
                  : 'border-sky-500/40 bg-sky-500/15 text-sky-300'
              }`}>
                <Archive className="h-3 w-3" />
                VCL: {formatNumber(vclQuota.usagePercent, 1)}% ({formatBytes(vclQuota.current)} / {formatBytes(vclQuota.max)})
              </span>
            </div>
          )}
          {userRootUsageBytes !== null && (
            <div className="mt-1">
              <span
                title={t('fileManager:labels.myFilesHint', 'Storage used by your home folder (excluding VCL versions)')}
                className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold border border-emerald-500/40 bg-emerald-500/15 text-emerald-300"
              >
                <Home className="h-3 w-3" />
                {t('fileManager:labels.myFiles', 'My Files')}: {formatBytes(userRootUsageBytes)}
              </span>
            </div>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2 sm:gap-3">
          <button
            onClick={() => setShowNewFolderDialog(true)}
            className="flex items-center gap-2 rounded-xl border border-slate-700/40 bg-slate-800/40 px-3 sm:px-4 py-2 sm:py-2.5 text-xs sm:text-sm font-medium text-slate-300 transition hover:bg-slate-800/60 hover:text-white touch-manipulation active:scale-95"
          >
            <FolderPlus className="h-4 w-4" />
            <span className="hidden sm:inline">New Folder</span>
            <span className="sm:hidden">Folder</span>
          </button>
          <label className={`btn btn-primary cursor-pointer text-xs sm:text-sm touch-manipulation active:scale-95 ${isUploading ? 'opacity-70 pointer-events-none' : ''}`}>
            <Upload className="h-4 w-4" />
            <span className="hidden sm:inline">{isUploading ? 'Uploading...' : 'Upload Files'}</span>
            <span className="sm:hidden">Upload</span>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
              onChange={handleUpload}
              disabled={isUploading}
            />
          </label>
          <label className={`hidden sm:flex items-center gap-2 rounded-xl border border-slate-700/40 bg-slate-800/40 px-4 py-2.5 text-sm font-medium text-slate-300 transition hover:bg-slate-800/60 hover:text-white cursor-pointer touch-manipulation active:scale-95 ${isUploading ? 'opacity-70 pointer-events-none' : ''}`}>
            <FolderUp className="h-4 w-4" />
            Upload Folder
            <input
              ref={folderInputRef}
              type="file"
              {...({ webkitdirectory: '', directory: '' } as React.InputHTMLAttributes<HTMLInputElement>)}
              multiple
              className="hidden"
              onChange={handleFolderUpload}
              disabled={isUploading}
            />
          </label>
        </div>
      </div>

      {/* Storage Drive Selector */}
      <StorageSelector
        mountpoints={mountpoints}
        selectedMountpoint={selectedMountpoint}
        onSelect={selectMountpoint}
      />

      {/* Breadcrumb Navigation */}
      <div className="card border-slate-800/60 bg-slate-900/55">
        <div className="flex flex-wrap items-center gap-2 sm:gap-3 text-xs sm:text-sm text-slate-400">
          <button
            onClick={goHome}
            className="rounded-full border border-slate-700/70 bg-slate-950/70 px-2.5 sm:px-3 py-1.5 text-[10px] sm:text-xs font-medium uppercase tracking-[0.15em] sm:tracking-[0.2em] text-slate-300 transition hover:border-slate-600 hover:text-white touch-manipulation active:scale-95"
          >
            {t('fileManager:labels.home', 'Home')}
          </button>
          {currentPath && (
            <>
              <span className="text-slate-600">/</span>
              <button
                onClick={goBack}
                className="rounded-full border border-slate-700/70 bg-slate-950/70 px-2.5 sm:px-3 py-1.5 text-[10px] sm:text-xs font-medium uppercase tracking-[0.15em] sm:tracking-[0.2em] text-slate-300 transition hover:border-slate-600 hover:text-white touch-manipulation active:scale-95"
              >
                &larr; Back
              </button>
              <span className="text-slate-600">/</span>
              <span className="rounded-full border border-slate-800/70 bg-slate-900/80 px-2.5 sm:px-3 py-1.5 text-[10px] sm:text-xs uppercase tracking-[0.15em] sm:tracking-[0.25em] text-slate-200 truncate max-w-[200px] sm:max-w-none" title={currentPath || '/'}>
                {currentPath || '/'}
              </span>
            </>
          )}
        </div>
      </div>

      {loading && files.length === 0 ? (
        <div className="card border-slate-800/60 bg-slate-900/55 py-12 text-center">
          <Loader2 className="h-8 w-8 animate-spin text-blue-500 mx-auto mb-4" />
          <p className="text-sm text-slate-400">Loading files...</p>
        </div>
      ) : (
        <FileListView
          files={files}
          versionCounts={versionCounts}
          userCache={userCache}
          loading={loading}
          dragActive={dragActive}
          isCurrentUserOwnerOrAdmin={isCurrentUserOwnerOrAdmin}
          onNavigate={navigateToFolder}
          onView={handleViewFile}
          onDownload={downloadFile}
          onRename={startRename}
          onDelete={confirmDelete}
          onVersionHistory={handleVersionHistory}
          onToggleTracking={toggleTracking}
          trackingStatus={trackingStatus}
          vclMode={vclMode}
          onShare={handleShareFile}
          onEditPermissions={handleEditPermissionsClick}
          onTransferOwnership={handleTransferOwnershipClick}
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
        />
      )}

      {/* New Folder Dialog */}
      {showNewFolderDialog && (
        <NewFolderDialog
          folderName={newFolderName}
          onFolderNameChange={setNewFolderName}
          onCreate={async () => { if (await createFolder(newFolderName)) { setShowNewFolderDialog(false); setNewFolderName(''); } }}
          onClose={() => { setShowNewFolderDialog(false); setNewFolderName(''); }}
        />
      )}

      {/* Delete Confirmation Dialog */}
      {showDeleteDialog && fileToDelete && (
        <DeleteDialog
          file={fileToDelete}
          onConfirm={async () => { if (fileToDelete && await deleteFile(fileToDelete)) { setShowDeleteDialog(false); setFileToDelete(null); } }}
          onClose={() => { setShowDeleteDialog(false); setFileToDelete(null); }}
        />
      )}

      {/* Rename Dialog */}
      {showRenameDialog && fileToRename && (
        <RenameDialog
          file={fileToRename}
          newName={newFileName}
          onNameChange={setNewFileName}
          onRename={async () => { if (fileToRename && await renameFile(fileToRename, newFileName)) { setShowRenameDialog(false); setFileToRename(null); setNewFileName(''); } }}
          onClose={() => { setShowRenameDialog(false); setFileToRename(null); setNewFileName(''); }}
        />
      )}

      {/* File Viewer Modal */}
      {viewingFile && (
        <FileViewer file={viewingFile} onClose={() => setViewingFile(null)} />
      )}

      {/* Version History Modal */}
      {showVersionHistory && versionHistoryFile && versionHistoryFile.file_id && (
        <VersionHistoryModal
          fileId={versionHistoryFile.file_id}
          fileName={versionHistoryFile.name}
          onClose={() => {
            setShowVersionHistory(false);
            setVersionHistoryFile(null);
          }}
          onVersionRestored={() => {
            refresh();
          }}
        />
      )}

      {/* Edit Permissions Modal */}
      {showEditPermissionsModal && fileToEditPermissions && (
        <PermissionEditor
          file={fileToEditPermissions}
          rules={editRules}
          allUsers={allUsers}
          onRulesChange={setEditRules}
          onSave={handleEditPermissionsSave}
          onClose={() => {
            setShowEditPermissionsModal(false);
            setFileToEditPermissions(null);
          }}
        />
      )}

      {/* Ownership Transfer Modal */}
      {showOwnershipModal && fileToTransfer && (
        <OwnershipTransferModal
          file={fileToTransfer}
          allUsers={allUsers}
          currentUserId={user?.id ?? 0}
          onClose={() => {
            setShowOwnershipModal(false);
            setFileToTransfer(null);
          }}
          onSuccess={(response) => {
            const targetUser = allUsers.find(u => Number(u.id) === Number(response.new_path?.split('/')[0] === fileToTransfer.name ? '' : response.new_path?.split('/')[0]));
            toast.success(t('fileManager:ownership.transferSuccessMessage', {
              count: response.transferred_count,
              user: targetUser?.username ?? '?',
            }));
            setShowOwnershipModal(false);
            setFileToTransfer(null);
            refresh();
          }}
        />
      )}

      {/* Share File Modal */}
      {sharingFile && sharingFile.file_id && (
        <ShareFileModal
          fileId={sharingFile.file_id}
          fileName={sharingFile.name}
          filePath={sharingFile.path}
          users={allUsers}
          onClose={() => setSharingFile(null)}
          onSuccess={() => {
            setSharingFile(null);
            toast.success(t('fileManager:messages.shared', 'Shared successfully'));
          }}
        />
      )}
    </div>
  );
}
