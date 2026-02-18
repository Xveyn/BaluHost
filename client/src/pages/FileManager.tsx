import { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import {
  FolderPlus,
  FolderUp,
  Upload,
  Archive,
  Loader2,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { apiClient, getFilePermissions, setFilePermissions } from '../lib/api';
import { getUsers } from '../api/users';
import { VersionHistoryModal } from '../components/vcl/VersionHistoryModal';
import { vclApi } from '../api/vcl';
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
import type { StorageInfo, StorageMountpoint, FileItem, ApiFileItem, PermissionRule } from '../components/file-manager/types';

export default function FileManager() {
  const { user } = useAuth();
  const { t } = useTranslation(['fileManager', 'common']);

  // User list
  const [allUsers, setAllUsers] = useState<Array<{ id: string; username: string }>>([]);

  useEffect(() => {
    getUsers()
      .then(data => {
        if (data && Array.isArray(data.users)) {
          setAllUsers(data.users.map((u) => ({ id: String(u.id), username: u.username })));
        }
      })
      .catch(() => {});
  }, []);

  // Permission modal state
  const [showEditPermissionsModal, setShowEditPermissionsModal] = useState(false);
  const [fileToEditPermissions, setFileToEditPermissions] = useState<FileItem | null>(null);
  const [editRules, setEditRules] = useState<PermissionRule[]>([]);

  // Ownership transfer modal state
  const [showOwnershipModal, setShowOwnershipModal] = useState(false);
  const [fileToTransfer, setFileToTransfer] = useState<FileItem | null>(null);

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

  // User cache for owner names
  const [userCache, setUserCache] = useState<Record<string, string>>({});
  const [files, setFiles] = useState<FileItem[]>([]);
  const [currentPath, setCurrentPath] = useState('');
  const [loading, setLoading] = useState(false);
  const { startUpload, isUploading, onUploadsComplete } = useUpload();
  const [showNewFolderDialog, setShowNewFolderDialog] = useState(false);
  const [newFolderName, setNewFolderName] = useState('');
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [fileToDelete, setFileToDelete] = useState<FileItem | null>(null);
  const [showRenameDialog, setShowRenameDialog] = useState(false);
  const [fileToRename, setFileToRename] = useState<FileItem | null>(null);
  const [newFileName, setNewFileName] = useState('');
  const [dragActive, setDragActive] = useState(false);
  const [viewingFile, setViewingFile] = useState<FileItem | null>(null);
  const [storageInfo, setStorageInfo] = useState<StorageInfo | null>(null);
  const [mountpoints, setMountpoints] = useState<StorageMountpoint[]>([]);
  const [selectedMountpoint, setSelectedMountpoint] = useState<StorageMountpoint | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  // VCL State
  const [showVersionHistory, setShowVersionHistory] = useState(false);
  const [versionHistoryFile, setVersionHistoryFile] = useState<FileItem | null>(null);
  const [versionCounts, setVersionCounts] = useState<Record<number, number>>({});
  const [vclQuota, setVclQuota] = useState<{
    usagePercent: number;
    warning: 'warning' | 'critical' | null;
    current: number;
    max: number;
  } | null>(null);

  const getErrorMessage = (error: unknown): string => {
    if (!error || typeof error !== 'object') return 'Unknown error';
    const obj = error as Record<string, unknown>;
    return String(obj.error ?? obj.detail ?? 'Unknown error');
  };

  useEffect(() => {
    loadMountpoints();
    loadVclQuota();
  }, []);

  // Reload files + storage when uploads complete
  useEffect(() => {
    return onUploadsComplete(() => {
      sessionStorage.removeItem(`files_cache_${currentPath}`);
      sessionStorage.removeItem('storage_info_cache');
      loadFiles(currentPath, false);
      loadStorageInfo();
      loadVclQuota();
    });
  }, [currentPath, onUploadsComplete]);

  useEffect(() => {
    if (selectedMountpoint) {
      loadFiles(currentPath);
      loadStorageInfo();
    }
  }, [currentPath, selectedMountpoint]);

  // Load VCL Quota
  const loadVclQuota = async () => {
    try {
      const quota = await vclApi.getUserQuota();
      let warningLevel: 'warning' | 'critical' | null = null;
      if (quota.usage_percent >= 95) {
        warningLevel = 'critical';
      } else if (quota.usage_percent >= 80) {
        warningLevel = 'warning';
      }

      setVclQuota({
        usagePercent: quota.usage_percent,
        warning: warningLevel,
        current: quota.current_usage_bytes,
        max: quota.max_size_bytes,
      });

      if (warningLevel === 'critical') {
        toast.error(
          `VCL Storage Critical: ${formatNumber(quota.usage_percent, 1)}% used (${formatBytes(quota.current_usage_bytes)} / ${formatBytes(quota.max_size_bytes)})`,
          { duration: 8000 }
        );
      } else if (warningLevel === 'warning') {
        toast(
          `VCL Storage Warning: ${formatNumber(quota.usage_percent, 1)}% used (${formatBytes(quota.current_usage_bytes)} / ${formatBytes(quota.max_size_bytes)})`,
          { duration: 6000, icon: '\u26a0\ufe0f' }
        );
      }
    } catch {
      // Silently ignore quota errors
    }
  };

  // Load version counts for all files with file_id
  useEffect(() => {
    const loadVersionCounts = async () => {
      const fileIds = files
        .filter(f => f.type === 'file' && f.file_id)
        .map(f => f.file_id!);

      if (fileIds.length === 0) return;

      try {
        const counts: Record<number, number> = {};
        await Promise.all(
          fileIds.map(async (fileId) => {
            try {
              const response = await vclApi.getFileVersions(fileId);
              counts[fileId] = response.total;
            } catch {
              // Ignore errors for individual files
            }
          })
        );
        setVersionCounts(counts);
      } catch {
        // Ignore
      }
    };

    loadVersionCounts();
  }, [files]);

  // Load owner names when files change
  useEffect(() => {
    const fetchOwnerNames = async (ownerIds: (string | number)[]) => {
      const uniqueIds = Array.from(new Set(ownerIds.filter(id => id !== undefined && id !== null && String(id) !== 'null')));
      if (uniqueIds.length === 0) return;
      try {
        const data = await getUsers();
        const cache: Record<string, string> = {};
        for (const u of data.users) {
          cache[u.id] = u.username;
        }
        setUserCache(cache);
      } catch {
        // ignore
      }
    };
    const ownerIds = files.map(f => f.ownerId).filter(id => id !== undefined && id !== null && String(id) !== 'null') as (string | number)[];
    fetchOwnerNames(ownerIds);
  }, [files]);

  if (!user) return null;

  const loadMountpoints = async () => {
    try {
      const { data } = await apiClient.get('/api/files/mountpoints');
      setMountpoints(data.mountpoints || []);

      const defaultMp = data.mountpoints.find((mp: StorageMountpoint) => mp.is_default)
                       || data.mountpoints[0];
      if (defaultMp) {
        setSelectedMountpoint(defaultMp);
        setCurrentPath('');
      }
    } catch {
      toast.error('Failed to load storage devices');
    }
  };

  const loadStorageInfo = async () => {
    if (!selectedMountpoint) return;

    const info = {
      totalBytes: selectedMountpoint.size_bytes,
      usedBytes: selectedMountpoint.used_bytes,
      availableBytes: selectedMountpoint.available_bytes
    };
    setStorageInfo(info);
  };

  const getFullPath = (relativePath: string = currentPath): string => {
    if (!selectedMountpoint) return relativePath;

    if (selectedMountpoint.type === 'dev-storage') {
      return relativePath;
    }

    const cleanRelativePath = relativePath.startsWith('/') ? relativePath.slice(1) : relativePath;
    return cleanRelativePath ? `${selectedMountpoint.path}/${cleanRelativePath}` : selectedMountpoint.path;
  };

  const loadFiles = async (path: string, useCache = true) => {
    if (!selectedMountpoint) return;

    const fullPath = getFullPath(path);

    if (useCache) {
      const cacheKey = `files_cache_${fullPath}`;
      const cachedData = sessionStorage.getItem(cacheKey);
      if (cachedData) {
        try {
          const cached = JSON.parse(cachedData);
          setFiles(cached.files);
        } catch {
          // ignore cache parse errors
        }
      }
    }

    setLoading(true);

    try {
      const { data } = await apiClient.get('/api/files/list', { params: { path: fullPath } });
      if (Array.isArray(data.files)) {
        const mappedFiles: FileItem[] = (data.files as ApiFileItem[]).map((file) => ({
          name: file.name,
          path: file.path,
          size: file.size,
          type: file.type,
          modifiedAt: file.modified_at ?? file.mtime ?? new Date().toISOString(),
          ownerId: file.ownerId ?? file.owner_id,
          ownerName: file.ownerName ?? file.owner_name,
          file_id: file.file_id,
        }));
        setFiles(mappedFiles);

        const cacheKey = `files_cache_${fullPath}`;
        sessionStorage.setItem(cacheKey, JSON.stringify({ files: mappedFiles, timestamp: Date.now() }));
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  const handleUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const fileList = e.target.files;
    if (!fileList) return;
    startUpload(fileList, getFullPath(), storageInfo?.availableBytes);
    e.target.value = '';
  };

  const handleFolderUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const fileList = e.target.files;
    if (!fileList) return;
    startUpload(fileList, getFullPath(), storageInfo?.availableBytes);
    e.target.value = '';
  };

  const handleDownload = async (file: FileItem) => {
    if (file.type === 'directory') return;

    try {
      const { data: blob } = await apiClient.get(`/api/files/download/${encodeURIComponent(file.path)}`, {
        responseType: 'blob',
      });
      const downloadUrl = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = downloadUrl;
      a.download = file.name;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(downloadUrl);
    } catch {
      toast.error(t('fileManager:messages.downloadError', 'Download failed'));
    }
  };

  const handleCreateFolder = async () => {
    if (!newFolderName.trim()) {
      toast.error(t('fileManager:messages.enterFolderName', 'Please enter a folder name'));
      return;
    }

    try {
      await apiClient.post('/api/files/folder', {
        path: getFullPath(),
        name: newFolderName,
      });
      toast.success(t('fileManager:messages.folderCreated', 'Folder created successfully'));
      setShowNewFolderDialog(false);
      setNewFolderName('');
      sessionStorage.removeItem(`files_cache_${currentPath}`);
      loadFiles(currentPath, false);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: unknown } })?.response?.data;
      toast.error(`${t('fileManager:messages.folderError', 'Failed to create folder')}: ${getErrorMessage(detail ?? err)}`);
    }
  };

  const confirmDelete = (file: FileItem) => {
    setFileToDelete(file);
    setShowDeleteDialog(true);
  };

  const handleDelete = async () => {
    if (!fileToDelete) return;

    try {
      await apiClient.delete(`/api/files/${encodeURIComponent(fileToDelete.path)}`);
      toast.success(t('fileManager:messages.deleteSuccess'));
      setShowDeleteDialog(false);
      setFileToDelete(null);
      sessionStorage.removeItem(`files_cache_${currentPath}`);
      sessionStorage.removeItem('storage_info_cache');
      loadFiles(currentPath, false);
      loadStorageInfo();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: unknown } })?.response?.data;
      toast.error(`${t('fileManager:messages.deleteError')}: ${getErrorMessage(detail ?? err)}`);
    }
  };

  const startRename = (file: FileItem) => {
    setFileToRename(file);
    setNewFileName(file.name);
    setShowRenameDialog(true);
  };

  const handleRename = async () => {
    if (!fileToRename || !newFileName.trim()) {
      toast.error(t('fileManager:messages.enterFileName', 'Please enter a valid file name'));
      return;
    }

    try {
      await apiClient.put('/api/files/rename', {
        old_path: fileToRename.path,
        new_name: newFileName,
      });
      toast.success(t('fileManager:messages.renameSuccess'));
      setShowRenameDialog(false);
      setFileToRename(null);
      setNewFileName('');
      sessionStorage.removeItem(`files_cache_${currentPath}`);
      loadFiles(currentPath, false);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: unknown } })?.response?.data;
      toast.error(`${t('fileManager:messages.renameError')}: ${getErrorMessage(detail ?? err)}`);
    }
  };

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const traverseFileTree = async (item: FileSystemEntry, path = ''): Promise<File[]> => {
    const files: File[] = [];

    if (item.isFile) {
      return new Promise((resolve) => {
        (item as FileSystemFileEntry).file((file: File) => {
          const newFile = new File([file], path + file.name, { type: file.type });
          Object.defineProperty(newFile, 'webkitRelativePath', {
            value: path + file.name,
            writable: false
          });
          resolve([newFile]);
        });
      });
    } else if (item.isDirectory) {
      const dirReader = (item as FileSystemDirectoryEntry).createReader();
      return new Promise((resolve) => {
        const readEntries = () => {
          dirReader.readEntries(async (entries: FileSystemEntry[]) => {
            if (entries.length === 0) {
              resolve(files);
            } else {
              for (const entry of entries) {
                const subFiles = await traverseFileTree(entry, path + item.name + '/');
                files.push(...subFiles);
              }
              readEntries();
            }
          });
        };
        readEntries();
      });
    }
    return files;
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    const items = e.dataTransfer.items;
    if (!items) return;

    const allFiles: File[] = [];

    for (let i = 0; i < items.length; i++) {
      const item = items[i].webkitGetAsEntry();
      if (item) {
        const files = await traverseFileTree(item);
        allFiles.push(...files);
      }
    }

    if (allFiles.length > 0) {
      const dt = new DataTransfer();
      allFiles.forEach(file => dt.items.add(file));
      startUpload(dt.files, getFullPath(), storageInfo?.availableBytes);
    }
  };

  const handleViewFile = (file: FileItem) => {
    setViewingFile(file);
  };

  const navigateToFolder = (folderPath: string) => {
    if (selectedMountpoint && selectedMountpoint.type !== 'dev-storage') {
      const mountpointPrefix = selectedMountpoint.path;
      if (folderPath.startsWith(mountpointPrefix)) {
        const relativePath = folderPath.slice(mountpointPrefix.length).replace(/^\//, '');
        setCurrentPath(relativePath);
        return;
      }
    }
    setCurrentPath(folderPath);
  };

  const goBack = () => {
    const parts = currentPath.split('/').filter(Boolean);
    parts.pop();
    const parentPath = parts.join('/');
    setCurrentPath(parentPath);
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
        onSelect={(mp) => {
          setSelectedMountpoint(mp);
          setCurrentPath('');
        }}
      />

      {/* Breadcrumb Navigation */}
      <div className="card border-slate-800/60 bg-slate-900/55">
        <div className="flex flex-wrap items-center gap-2 sm:gap-3 text-xs sm:text-sm text-slate-400">
          <button
            onClick={() => setCurrentPath('')}
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
              <span className="text-slate-600 hidden sm:inline">/</span>
              <span className="rounded-full border border-slate-800/70 bg-slate-900/80 px-2.5 sm:px-3 py-1.5 text-[10px] sm:text-xs uppercase tracking-[0.15em] sm:tracking-[0.25em] text-slate-200 truncate max-w-[150px] sm:max-w-none">
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
          onDownload={handleDownload}
          onRename={startRename}
          onDelete={confirmDelete}
          onVersionHistory={handleVersionHistory}
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
          onCreate={handleCreateFolder}
          onClose={() => { setShowNewFolderDialog(false); setNewFolderName(''); }}
        />
      )}

      {/* Delete Confirmation Dialog */}
      {showDeleteDialog && fileToDelete && (
        <DeleteDialog
          file={fileToDelete}
          onConfirm={handleDelete}
          onClose={() => { setShowDeleteDialog(false); setFileToDelete(null); }}
        />
      )}

      {/* Rename Dialog */}
      {showRenameDialog && fileToRename && (
        <RenameDialog
          file={fileToRename}
          newName={newFileName}
          onNameChange={setNewFileName}
          onRename={handleRename}
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
            loadFiles(currentPath, false);
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
            loadFiles(currentPath, false);
          }}
        />
      )}
    </div>
  );
}
