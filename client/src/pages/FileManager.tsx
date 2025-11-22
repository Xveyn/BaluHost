import { useState, useEffect } from 'react';
import toast from 'react-hot-toast';
import { buildApiUrl } from '../lib/api';

interface FileItem {
  name: string;
  path: string;
  size: number;
  type: 'file' | 'directory';
  modifiedAt: string;
}

interface ApiFileItem {
  name: string;
  path: string;
  size: number;
  type: 'file' | 'directory';
  modified_at?: string;
  mtime?: string;
}

export default function FileManager() {
  const [files, setFiles] = useState<FileItem[]>([]);
  const [currentPath, setCurrentPath] = useState('');
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [showNewFolderDialog, setShowNewFolderDialog] = useState(false);
  const [newFolderName, setNewFolderName] = useState('');
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [fileToDelete, setFileToDelete] = useState<FileItem | null>(null);
  const [showRenameDialog, setShowRenameDialog] = useState(false);
  const [fileToRename, setFileToRename] = useState<FileItem | null>(null);
  const [newFileName, setNewFileName] = useState('');

  const getToken = (notify = true): string | null => {
    const token = localStorage.getItem('token');
    if (!token && notify) {
      toast.error('Session expired. Please sign in again.');
    }
    return token;
  };

  const getErrorMessage = (error: any): string => {
    if (!error) return 'Unknown error';
    return error.error ?? error.detail ?? 'Unknown error';
  };

  useEffect(() => {
    loadFiles(currentPath);
  }, [currentPath]);

  const loadFiles = async (path: string) => {
    setLoading(true);
    const token = getToken(false);
    if (!token) {
      setLoading(false);
      return;
    }

    try {
      const response = await fetch(buildApiUrl(`/api/files/list?path=${encodeURIComponent(path)}`), {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      const data = await response.json();
      if (Array.isArray(data.files)) {
        const mappedFiles: FileItem[] = (data.files as ApiFileItem[]).map((file) => ({
          name: file.name,
          path: file.path,
          size: file.size,
          type: file.type,
          modifiedAt: file.modified_at ?? file.mtime ?? new Date().toISOString(),
        }));
        setFiles(mappedFiles);
      }
    } catch (err) {
      console.error('Failed to load files:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const fileList = e.target.files;
    if (!fileList) return;

    setUploading(true);
    const token = getToken();
    if (!token) {
      e.target.value = '';
      setUploading(false);
      return;
    }
    const formData = new FormData();

    Array.from(fileList).forEach(file => {
      formData.append('files', file);
    });
    formData.append('path', currentPath);

    try {
      const response = await fetch(buildApiUrl('/api/files/upload'), {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        },
        body: formData
      });

      if (response.ok) {
        toast.success('Files uploaded successfully!');
        loadFiles(currentPath);
      } else {
        const error = await response.json();
        toast.error(`Upload failed: ${getErrorMessage(error)}`);
      }
    } catch (err) {
      console.error('Upload failed:', err);
      toast.error('Upload failed. Please try again.');
    } finally {
      e.target.value = '';
      setUploading(false);
    }
  };

  const handleDownload = async (file: FileItem) => {
    if (file.type === 'directory') return;

    const token = getToken();
    if (!token) {
      return;
    }
    const url = buildApiUrl(`/api/files/download/${encodeURIComponent(file.path)}`);

    try {
      const response = await fetch(url, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (response.ok) {
        const blob = await response.blob();
        const downloadUrl = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = downloadUrl;
        a.download = file.name;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(downloadUrl);
      } else {
        toast.error('Download failed');
      }
    } catch (err) {
      console.error('Download failed:', err);
      toast.error('Download failed. Please try again.');
    }
  };

  const handleCreateFolder = async () => {
    if (!newFolderName.trim()) {
      toast.error('Please enter a folder name');
      return;
    }

    const token = getToken();
    if (!token) {
      return;
    }

    try {
      const response = await fetch(buildApiUrl('/api/files/folder'), {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          path: currentPath,
          name: newFolderName
        })
      });

      if (response.ok) {
        toast.success('Folder created successfully!');
        setShowNewFolderDialog(false);
        setNewFolderName('');
        loadFiles(currentPath);
      } else {
        const error = await response.json();
        toast.error(`Failed to create folder: ${getErrorMessage(error)}`);
      }
    } catch (err) {
      console.error('Create folder failed:', err);
      toast.error('Failed to create folder. Please try again.');
    }
  };

  const confirmDelete = (file: FileItem) => {
    setFileToDelete(file);
    setShowDeleteDialog(true);
  };

  const handleDelete = async () => {
    if (!fileToDelete) return;

    const token = getToken();
    if (!token) {
      return;
    }

    try {
      const response = await fetch(buildApiUrl(`/api/files/${encodeURIComponent(fileToDelete.path)}`), {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (response.ok) {
        toast.success(`${fileToDelete.type === 'directory' ? 'Folder' : 'File'} deleted successfully!`);
        setShowDeleteDialog(false);
        setFileToDelete(null);
        loadFiles(currentPath);
      } else {
        const error = await response.json();
        toast.error(`Delete failed: ${getErrorMessage(error)}`);
      }
    } catch (err) {
      console.error('Delete failed:', err);
      toast.error('Delete failed. Please try again.');
    }
  };

  const startRename = (file: FileItem) => {
    setFileToRename(file);
    setNewFileName(file.name);
    setShowRenameDialog(true);
  };

  const handleRename = async () => {
    if (!fileToRename || !newFileName.trim()) {
      toast.error('Please enter a valid file name');
      return;
    }

    const token = localStorage.getItem('token');

    try {
      const response = await fetch(buildApiUrl('/api/files/rename'), {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          old_path: fileToRename.path,
          new_name: newFileName
        })
      });

      if (response.ok) {
        toast.success('Renamed successfully!');
        setShowRenameDialog(false);
        setFileToRename(null);
        setNewFileName('');
        loadFiles(currentPath);
      } else {
        const error = await response.json();
        toast.error(`Rename failed: ${getErrorMessage(error)}`);
      }
    } catch (err) {
      console.error('Rename failed:', err);
      toast.error('Rename failed. Please try again.');
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
  };

  const navigateToFolder = (folderPath: string) => {
    setCurrentPath(folderPath);
  };

  const goBack = () => {
    const parts = currentPath.split('/').filter(Boolean);
    parts.pop();
    setCurrentPath(parts.join('/'));
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold text-white">
            File Manager
          </h1>
          <p className="mt-1 text-sm text-slate-400">Browse, upload, and organise your vaults</p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={() => setShowNewFolderDialog(true)}
            className="rounded-xl border border-slate-700/70 bg-slate-900/70 px-4 py-2 text-sm font-medium text-slate-200 transition hover:border-sky-500/40 hover:text-white"
          >
            + New Folder
          </button>
          <label className={`btn btn-primary cursor-pointer ${uploading ? 'opacity-70' : ''}`}>
            {uploading ? 'Uploading...' : '↑ Upload Files'}
            <input
              type="file"
              multiple
              className="hidden"
              onChange={handleUpload}
              disabled={uploading}
            />
          </label>
        </div>
      </div>

      <div className="card border-slate-800/60 bg-slate-900/55">
        <div className="flex flex-wrap items-center gap-3 text-sm text-slate-400">
          <button
            onClick={() => setCurrentPath('')}
            className="rounded-full border border-slate-700/70 bg-slate-950/70 px-3 py-1.5 text-xs font-medium uppercase tracking-[0.2em] text-slate-300 transition hover:border-sky-500/40 hover:text-white"
          >
            Home
          </button>
          {currentPath && (
            <>
              <span className="text-slate-600">/</span>
              <button
                onClick={goBack}
                className="rounded-full border border-slate-700/70 bg-slate-950/70 px-3 py-1.5 text-xs font-medium uppercase tracking-[0.2em] text-slate-300 transition hover:border-sky-500/40 hover:text-white"
              >
                ← Back
              </button>
              <span className="text-slate-600">/</span>
              <span className="rounded-full border border-slate-800/70 bg-slate-900/80 px-3 py-1.5 text-xs uppercase tracking-[0.25em] text-slate-200">
                {currentPath || '/'}
              </span>
            </>
          )}
        </div>
      </div>

      {loading ? (
        <div className="card border-slate-800/60 bg-slate-900/55 py-12 text-center">
          <p className="text-sm text-slate-500">Loading files...</p>
        </div>
      ) : (
        <div className="card border-slate-800/60 bg-slate-900/55">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-800/60">
              <thead>
                <tr className="text-left text-xs uppercase tracking-[0.25em] text-slate-500">
                  <th className="px-6 py-4">Name</th>
                  <th className="px-6 py-4">Type</th>
                  <th className="px-6 py-4">Size</th>
                  <th className="px-6 py-4">Modified</th>
                  <th className="px-6 py-4">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {files.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-6 py-12 text-center text-sm text-slate-500">
                      No files found
                    </td>
                  </tr>
                ) : (
                  files.map((file) => (
                    <tr
                      key={file.path}
                      className="group transition hover:bg-slate-900/70"
                    >
                      <td
                        className="px-6 py-4"
                        onClick={() => file.type === 'directory' && navigateToFolder(file.path)}
                      >
                        <div className="flex cursor-pointer items-center gap-3 text-sm text-slate-200">
                          <span className={`flex h-9 w-9 items-center justify-center rounded-xl border text-base ${
                            file.type === 'directory'
                              ? 'border-sky-500/20 bg-sky-500/10 text-sky-200'
                              : 'border-slate-800 bg-slate-900/70 text-slate-400'
                          }`}>
                            {file.type === 'directory' ? '📁' : '📄'}
                          </span>
                          <span className="truncate font-medium group-hover:text-white">
                            {file.name}
                          </span>
                        </div>
                      </td>
                      <td className="px-6 py-4 text-xs uppercase tracking-[0.25em] text-slate-500">
                        {file.type}
                      </td>
                      <td className="px-6 py-4 text-sm text-slate-400">
                        {file.type === 'file' ? formatFileSize(file.size) : '—'}
                      </td>
                      <td className="px-6 py-4 text-sm text-slate-500">
                        {new Date(file.modifiedAt).toLocaleString()}
                      </td>
                      <td className="px-6 py-4 text-sm">
                        <div className="flex flex-wrap items-center gap-2">
                          {file.type === 'file' && (
                            <button
                              onClick={() => handleDownload(file)}
                              className="rounded-xl border border-sky-500/30 bg-sky-500/10 px-3 py-1.5 text-xs font-medium text-sky-200 transition hover:border-sky-400/40 hover:bg-sky-500/20"
                            >
                              ↓ Download
                            </button>
                          )}
                          <button
                            onClick={() => startRename(file)}
                            className="rounded-xl border border-slate-700/70 bg-slate-900/70 px-3 py-1.5 text-xs font-medium text-slate-300 transition hover:border-slate-500 hover:text-white"
                          >
                            ✎ Rename
                          </button>
                          <button
                            onClick={() => confirmDelete(file)}
                            className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 py-1.5 text-xs font-medium text-rose-200 transition hover:border-rose-400/40 hover:bg-rose-500/20"
                          >
                            🗑 Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* New Folder Dialog */}
      {showNewFolderDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-lg">
          <div className="card w-full max-w-md border-slate-800/60 bg-slate-900/70">
            <h3 className="text-xl font-semibold text-white">Create New Folder</h3>
            <p className="mt-2 text-sm text-slate-400">Organise your storage pool with a dedicated directory.</p>
            <input
              type="text"
              value={newFolderName}
              onChange={(e) => setNewFolderName(e.target.value)}
              placeholder="Enter folder name"
              className="input mt-5"
              autoFocus
              onKeyDown={(e) => e.key === 'Enter' && handleCreateFolder()}
            />
            <div className="mt-6 flex justify-end gap-3">
              <button
                onClick={() => {
                  setShowNewFolderDialog(false);
                  setNewFolderName('');
                }}
                className="rounded-xl border border-slate-700/70 bg-slate-900/70 px-4 py-2 text-sm font-medium text-slate-300 transition hover:border-slate-500 hover:text-white"
              >
                Cancel
              </button>
              <button
                onClick={handleCreateFolder}
                className="btn btn-primary"
              >
                Create
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Dialog */}
      {showDeleteDialog && fileToDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-lg">
          <div className="card w-full max-w-md border-rose-500/30 bg-slate-900/75">
            <h3 className="text-xl font-semibold text-white">Confirm Delete</h3>
            <p className="mt-3 text-sm text-slate-400">
              Are you sure you want to remove <span className="font-semibold text-slate-100">{fileToDelete.name}</span>?
              {fileToDelete.type === 'directory' && <span className="text-amber-300"> All nested items will also be deleted.</span>}
            </p>
            <div className="mt-6 flex justify-end gap-3">
              <button
                onClick={() => {
                  setShowDeleteDialog(false);
                  setFileToDelete(null);
                }}
                className="rounded-xl border border-slate-700/70 bg-slate-900/70 px-4 py-2 text-sm font-medium text-slate-300 transition hover:border-slate-500 hover:text-white"
              >
                Cancel
              </button>
              <button
                onClick={handleDelete}
                className="rounded-xl border border-rose-500/50 bg-rose-500/20 px-4 py-2 text-sm font-medium text-rose-200 transition hover:border-rose-400 hover:bg-rose-500/30"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Rename Dialog */}
      {showRenameDialog && fileToRename && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-lg">
          <div className="card w-full max-w-md border-slate-800/60 bg-slate-900/70">
            <h3 className="text-xl font-semibold text-white">Rename {fileToRename.type === 'directory' ? 'Folder' : 'File'}</h3>
            <p className="mt-3 text-sm text-slate-400">Update the display name without affecting the contents.</p>
            <input
              type="text"
              value={newFileName}
              onChange={(e) => setNewFileName(e.target.value)}
              placeholder="Enter new name"
              className="input mt-5"
              autoFocus
              onKeyDown={(e) => e.key === 'Enter' && handleRename()}
            />
            <div className="mt-6 flex justify-end gap-3">
              <button
                onClick={() => {
                  setShowRenameDialog(false);
                  setFileToRename(null);
                  setNewFileName('');
                }}
                className="rounded-xl border border-slate-700/70 bg-slate-900/70 px-4 py-2 text-sm font-medium text-slate-300 transition hover:border-slate-500 hover:text-white"
              >
                Cancel
              </button>
              <button
                onClick={handleRename}
                className="btn btn-primary"
              >
                Rename
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
