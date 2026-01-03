import { useState, useEffect } from 'react';
import { ChevronRight, Folder, File, HardDrive, RefreshCw, Upload, FolderPlus, Trash2, Edit2, Download, Home } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';

interface FileItem {
  id: number;
  name: string;
  path: string;
  type: 'file' | 'directory';
  size: number;
  owner: string;
  created_at: string;
  updated_at: string;
  mount_id?: string;
}

interface Mountpoint {
  id: string;
  name: string;
  mount_path: string;
  raid_level: string;
  total_size: number;
  used_size: number;
}

const FileExplorer: React.FC = () => {
  const [mountpoints, setMountpoints] = useState<Mountpoint[]>([]);
  const [selectedMount, setSelectedMount] = useState<Mountpoint | null>(null);
  const [currentPath, setCurrentPath] = useState('/');
  const [files, setFiles] = useState<FileItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<FileItem | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    loadMountpoints();
  }, []);

  useEffect(() => {
    if (selectedMount) {
      loadFiles();
    }
  }, [selectedMount, currentPath]);

  const loadMountpoints = async () => {
    try {
      setLoading(true);
      const response = await window.electronAPI.invoke('get_mountpoints', {});
      
      if (response.success && response.mountpoints) {
        setMountpoints(response.mountpoints);
        if (response.mountpoints.length > 0 && !selectedMount) {
          setSelectedMount(response.mountpoints[0]);
        }
      } else {
        setError('Failed to load storage drives');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load storage drives');
    } finally {
      setLoading(false);
    }
  };

  const loadFiles = async () => {
    if (!selectedMount) return;

    try {
      setLoading(true);
      setError(null);
      const response = await window.electronAPI.invoke('list_files', {
        path: currentPath,
        mountId: selectedMount.id
      });

      if (response.success && response.files) {
        setFiles(response.files);
      } else {
        setError('Failed to load files');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load files');
    } finally {
      setLoading(false);
    }
  };

  const navigateToFolder = (folder: FileItem) => {
    if (folder.type === 'directory') {
      setCurrentPath(folder.path);
    }
  };

  const navigateUp = () => {
    if (currentPath === '/') return;
    const parts = currentPath.split('/').filter(Boolean);
    parts.pop();
    setCurrentPath('/' + parts.join('/'));
  };

  const formatSize = (bytes: number): string => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
  };

  const formatDate = (dateString: string): string => {
    try {
      return new Date(dateString).toLocaleString();
    } catch {
      return dateString;
    }
  };

  const getBreadcrumbs = () => {
    const parts = currentPath.split('/').filter(Boolean);
    const breadcrumbs = [{ name: 'Root', path: '/' }];
    
    let path = '';
    for (const part of parts) {
      path += '/' + part;
      breadcrumbs.push({ name: part, path });
    }
    
    return breadcrumbs;
  };

  const handleCreateFolder = async () => {
    const name = prompt('Enter folder name:');
    if (!name || !selectedMount) return;

    try {
      const response = await window.electronAPI.invoke('create_folder', {
        path: currentPath,
        name,
        mountId: selectedMount.id
      });

      if (response.success) {
        toast.success(`Folder "${name}" created`);
        loadFiles();
      } else {
        toast.error('Failed to create folder');
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to create folder');
    }
  };

  const handleDelete = async (file: FileItem) => {
    if (!confirm(`Delete ${file.name}?`)) return;

    try {
      const response = await window.electronAPI.invoke('delete_file', {
        fileId: file.id
      });

      if (response.success) {
        toast.success(`"${file.name}" deleted`);
        loadFiles();
      } else {
        toast.error('Failed to delete file');
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to delete file');
    }
  };

  const handleRename = async (file: FileItem) => {
    const newName = prompt('Enter new name:', file.name);
    if (!newName || newName === file.name) return;

    try {
      const response = await window.electronAPI.invoke('rename_file', {
        fileId: file.id,
        newName
      });

      if (response.success) {
        toast.success(`Renamed to "${newName}"`);
        loadFiles();
      } else {
        toast.error('Failed to rename file');
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to rename file');
    }
  };

  const handleDownload = async (file: FileItem) => {
    try {
      // Open save dialog
      const savePath = await window.electronAPI.selectSaveLocation(file.name);
      if (!savePath) return; // User cancelled

      toast.loading('Downloading...', { id: 'download' });

      const response = await window.electronAPI.invoke('download_file', {
        remotePath: file.path,
        localPath: savePath
      });

      toast.dismiss('download');

      if (response.success) {
        toast.success(`Downloaded to ${savePath}`);
      } else {
        toast.error(response.error || 'Failed to download file');
      }
    } catch (err) {
      toast.dismiss('download');
      toast.error(err instanceof Error ? err.message : 'Failed to download file');
    }
  };

  const handleUpload = async () => {
    if (!selectedMount) return;

    try {
      // Open file selection dialog
      const filePath = await window.electronAPI.selectFile();
      if (!filePath) return; // User cancelled

      // Extract filename
      const fileName = filePath.split(/[\\/]/).pop() || 'file';
      const remotePath = currentPath === '/' ? `/${fileName}` : `${currentPath}/${fileName}`;

      toast.loading('Uploading...', { id: 'upload' });

      const response = await window.electronAPI.invoke('upload_file', {
        localPath: filePath,
        remotePath,
        mountId: selectedMount.id
      });

      toast.dismiss('upload');

      if (response.success) {
        toast.success(`Uploaded ${fileName}`);
        loadFiles();
      } else {
        toast.error(response.error || 'Failed to upload file');
      }
    } catch (err) {
      toast.dismiss('upload');
      toast.error(err instanceof Error ? err.message : 'Failed to upload file');
    }
  };

  return (
    <div className="flex flex-col h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
      {/* Header */}
      <div className="border-b border-white/10 bg-white/5 backdrop-blur-md">
        <div className="flex h-16 items-center justify-between px-6">
          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-3">
              <div className="rounded-lg bg-gradient-to-br from-blue-500 to-blue-600 p-2">
                <HardDrive className="h-5 w-5 text-white" />
              </div>
              <div>
                <h1 className="text-lg font-bold text-white">File Explorer</h1>
                <p className="text-xs text-slate-400">{selectedMount?.name || 'Select storage'}</p>
              </div>
            </div>
          </div>

          <div className="flex items-center space-x-2">
            <button
              onClick={() => navigate('/')}
              className="rounded-lg px-4 py-2 text-sm font-medium text-white hover:bg-white/10 transition-all flex items-center space-x-2"
            >
              <Home className="h-4 w-4" />
              <span>Dashboard</span>
            </button>
            <button
              onClick={loadFiles}
              disabled={!selectedMount || loading}
              className="rounded-lg bg-blue-500/20 px-4 py-2 text-sm font-medium text-blue-400 hover:bg-blue-500/30 disabled:opacity-50 transition-all flex items-center space-x-2"
            >
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
              <span>Refresh</span>
            </button>
          </div>
        </div>
      </div>

      {/* Storage & Actions Bar */}
      <div className="border-b border-white/10 bg-white/5 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <label className="text-sm font-medium text-slate-300">Storage:</label>
            <select
              value={selectedMount?.id || ''}
              onChange={(e) => {
                const mount = mountpoints.find(m => m.id === e.target.value);
                setSelectedMount(mount || null);
                setCurrentPath('/');
              }}
              className="rounded-lg border border-white/20 bg-white/10 px-4 py-2 text-white backdrop-blur-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50 min-w-[300px]"
            >
              {mountpoints.map(m => (
                <option key={m.id} value={m.id} className="bg-slate-800">
                  {m.name} - {formatSize(m.used_size)} / {formatSize(m.total_size)}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center space-x-2">
            <button
              onClick={handleCreateFolder}
              disabled={!selectedMount}
              className="rounded-lg bg-emerald-500/20 px-4 py-2 text-sm font-medium text-emerald-400 hover:bg-emerald-500/30 disabled:opacity-50 transition-all flex items-center space-x-2"
            >
              <FolderPlus className="h-4 w-4" />
              <span>New Folder</span>
            </button>
            <button
              onClick={handleUpload}
              disabled={!selectedMount}
              className="rounded-lg bg-blue-500/20 px-4 py-2 text-sm font-medium text-blue-400 hover:bg-blue-500/30 disabled:opacity-50 transition-all flex items-center space-x-2"
            >
              <Upload className="h-4 w-4" />
              <span>Upload</span>
            </button>
          </div>
        </div>
      </div>

      {/* Breadcrumb Navigation */}
      <div className="bg-white/5 px-6 py-3 border-b border-white/10">
        <div className="flex items-center gap-2 text-sm">
          {getBreadcrumbs().map((crumb, index) => (
            <div key={crumb.path} className="flex items-center gap-2">
              {index > 0 && <ChevronRight className="w-4 h-4 text-slate-500" />}
              <button
                onClick={() => setCurrentPath(crumb.path)}
                className="text-blue-400 hover:text-blue-300 hover:underline font-medium transition-colors"
              >
                {crumb.name}
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* File List */}
      <div className="flex-1 overflow-auto px-6 py-4">
        {error && (
          <div className="bg-red-500/10 border border-red-500/30 text-red-400 px-4 py-3 rounded-lg mb-4 backdrop-blur-sm">
            {error}
          </div>
        )}

        {loading ? (
          <div className="flex flex-col items-center justify-center h-64 space-y-4">
            <RefreshCw className="w-12 h-12 animate-spin text-blue-500" />
            <p className="text-slate-400">Loading files...</p>
          </div>
        ) : (
          <div className="rounded-xl border border-white/10 bg-white/5 backdrop-blur-sm overflow-hidden">
            <table className="w-full">
              <thead className="bg-white/5 border-b border-white/10">
                <tr>
                  <th className="px-6 py-4 text-left text-xs font-semibold text-slate-300 uppercase tracking-wider">
                    Name
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-semibold text-slate-300 uppercase tracking-wider">
                    Size
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-semibold text-slate-300 uppercase tracking-wider">
                    Owner
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-semibold text-slate-300 uppercase tracking-wider">
                    Modified
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-semibold text-slate-300 uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {currentPath !== '/' && (
                  <tr className="hover:bg-white/10 cursor-pointer transition-all group" onClick={navigateUp}>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center gap-3">
                        <div className="rounded-lg bg-blue-500/20 p-2 group-hover:bg-blue-500/30 transition-all">
                          <Folder className="w-4 h-4 text-blue-400" />
                        </div>
                        <span className="font-medium text-white">..</span>
                      </div>
                    </td>
                    <td colSpan={4}></td>
                  </tr>
                )}
                {files.map((file, idx) => (
                  <tr
                    key={`${currentPath}/${file.path}-${idx}`}
                    className={`hover:bg-white/10 transition-all cursor-pointer group ${
                      selectedFile?.path === file.path ? 'bg-blue-500/20 border-l-4 border-blue-500' : ''
                    }`}
                    onClick={() => setSelectedFile(file)}
                    onDoubleClick={() => file.type === 'directory' && navigateToFolder(file)}
                  >
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center gap-3">
                        {file.type === 'directory' ? (
                          <div className="rounded-lg bg-blue-500/20 p-2 group-hover:bg-blue-500/30 transition-all">
                            <Folder className="w-4 h-4 text-blue-400" />
                          </div>
                        ) : (
                          <div className="rounded-lg bg-slate-500/20 p-2 group-hover:bg-slate-500/30 transition-all">
                            <File className="w-4 h-4 text-slate-400" />
                          </div>
                        )}
                        <span className="font-medium text-white">{file.name}</span>
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-400">
                      {file.type === 'file' ? formatSize(file.size) : '-'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-400">
                      {file.owner || '-'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-400">
                      {file.updated_at ? formatDate(file.updated_at) : '-'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                      <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleRename(file);
                          }}
                          className="p-2 text-blue-400 hover:bg-blue-500/20 rounded-lg transition-all"
                          title="Rename"
                        >
                          <Edit2 className="w-4 h-4" />
                        </button>
                        {file.type === 'file' && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleDownload(file);
                            }}
                            className="p-2 text-green-400 hover:bg-green-500/20 rounded-lg transition-all"
                            title="Download"
                          >
                            <Download className="w-4 h-4" />
                          </button>
                        )}
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDelete(file);
                          }}
                          className="p-2 text-red-400 hover:bg-red-500/20 rounded-lg transition-all"
                          title="Delete"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {files.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-6 py-16 text-center">
                      <div className="flex flex-col items-center gap-3 text-slate-500">
                        <div className="rounded-full bg-white/5 p-6">
                          <Folder className="w-16 h-16" />
                        </div>
                        <div>
                          <p className="text-lg font-medium text-slate-400">This folder is empty</p>
                          <p className="text-sm text-slate-600 mt-1">Add files or create a new folder to get started</p>
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default FileExplorer;
