import { useEffect, useState } from 'react';
import { Cloud, FolderSync, Settings, LogOut, Activity, Files, FolderPlus } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';

interface DashboardProps {
  user: { username: string; serverUrl?: string };
  onLogout: () => void;
}

interface SyncStats {
  status: string;
  uploadSpeed: number;
  downloadSpeed: number;
  pendingUploads: number;
  pendingDownloads: number;
  lastSync: string;
}

export default function Dashboard({ user, onLogout }: DashboardProps) {
  const [syncStats, setSyncStats] = useState<SyncStats | null>(null);
  const [folders, setFolders] = useState<any[]>([]);
  const navigate = useNavigate();

  useEffect(() => {
    // Listen to backend messages
    window.electronAPI.onBackendMessage((message) => {
      console.log('Backend message:', message);
      
      if (message.type === 'sync_stats') {
        setSyncStats(message.data);
      } else if (message.type === 'sync_folders') {
        setFolders(message.data);
      }
    });

    // Request initial data
    fetchSyncState();
    fetchSyncFolders();

    return () => {
      window.electronAPI.removeBackendListener();
    };
  }, []);

  const fetchSyncState = async () => {
    try {
      const response = await window.electronAPI.sendBackendCommand({
        type: 'get_sync_state',
      });
      if (response.success) {
        setSyncStats(response.data);
      }
    } catch (err) {
      console.error('Failed to fetch sync state:', err);
    }
  };

  const fetchSyncFolders = async () => {
    try {
      const response = await window.electronAPI.sendBackendCommand({
        type: 'get_sync_folders',
      });
      if (response.success) {
        setFolders(response.data || []);
      }
    } catch (err) {
      console.error('Failed to fetch sync folders:', err);
    }
  };

  const handleAddFolder = async () => {
    // TODO: Implement folder selection dialog
    toast('Folder selection coming soon!');
  };

  const handleLogout = async () => {
    try {
      await window.electronAPI.sendBackendCommand({ type: 'logout' });
      onLogout();
      toast.success('Logged out successfully');
    } catch (err) {
      console.error('Logout error:', err);
      onLogout(); // Logout anyway
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
      {/* Header */}
      <header className="border-b border-white/10 bg-white/5 backdrop-blur-md">
        <div className="flex h-16 items-center justify-between px-6">
          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-3">
              <div className="rounded-lg bg-gradient-to-br from-blue-500 to-blue-600 p-2">
                <Cloud className="h-5 w-5 text-white" />
              </div>
              <div>
                <h1 className="text-lg font-bold text-white">BaluDesk</h1>
                <p className="text-xs text-slate-400">Desktop Client</p>
              </div>
            </div>
          </div>

          <nav className="flex items-center space-x-2">
            <button
              onClick={() => navigate('/')}
              className="rounded-lg px-4 py-2 text-sm font-medium text-white bg-white/10 hover:bg-white/20 transition-all"
            >
              <Activity className="inline h-4 w-4 mr-2" />
              Dashboard
            </button>
            <button
              onClick={() => navigate('/files')}
              className="rounded-lg px-4 py-2 text-sm font-medium text-white hover:bg-white/10 transition-all"
            >
              <Files className="inline h-4 w-4 mr-2" />
              Files
            </button>
          </nav>

          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-3 rounded-lg bg-white/5 px-4 py-2">
              <div className="h-8 w-8 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-white text-sm font-bold">
                {user.username[0].toUpperCase()}
              </div>
              <div className="text-sm">
                <div className="font-medium text-white">{user.username}</div>
                {user.serverUrl && (
                  <div className="text-xs text-slate-400">
                    {new URL(user.serverUrl).hostname}
                  </div>
                )}
              </div>
            </div>
            <button
              onClick={handleLogout}
              className="rounded-lg p-2 text-slate-400 hover:bg-red-500/20 hover:text-red-400 transition-all"
              title="Logout"
            >
              <LogOut className="h-5 w-5" />
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="p-6">
        <div className="mx-auto max-w-7xl space-y-6">
          {/* Sync Status Cards */}
          <div className="grid gap-6 md:grid-cols-4">
            <div className="group relative overflow-hidden rounded-xl border border-white/10 bg-gradient-to-br from-blue-500/10 to-blue-600/10 p-6 backdrop-blur-sm transition-all hover:border-blue-500/30 hover:shadow-lg hover:shadow-blue-500/20">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-slate-400">Status</p>
                  <p className="mt-2 text-3xl font-bold text-white">
                    {syncStats?.status || 'Idle'}
                  </p>
                </div>
                <div className="rounded-lg bg-blue-500/20 p-3">
                  <Activity className="h-6 w-6 text-blue-400" />
                </div>
              </div>
            </div>

            <div className="group relative overflow-hidden rounded-xl border border-white/10 bg-gradient-to-br from-emerald-500/10 to-emerald-600/10 p-6 backdrop-blur-sm transition-all hover:border-emerald-500/30 hover:shadow-lg hover:shadow-emerald-500/20">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-slate-400">Upload Queue</p>
                  <p className="mt-2 text-3xl font-bold text-white">
                    {syncStats?.pendingUploads || 0}
                  </p>
                </div>
                <div className="rounded-lg bg-emerald-500/20 p-3 text-2xl font-bold text-emerald-400">↑</div>
              </div>
            </div>

            <div className="group relative overflow-hidden rounded-xl border border-white/10 bg-gradient-to-br from-purple-500/10 to-purple-600/10 p-6 backdrop-blur-sm transition-all hover:border-purple-500/30 hover:shadow-lg hover:shadow-purple-500/20">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-slate-400">Download Queue</p>
                  <p className="mt-2 text-3xl font-bold text-white">
                    {syncStats?.pendingDownloads || 0}
                  </p>
                </div>
                <div className="rounded-lg bg-purple-500/20 p-3 text-2xl font-bold text-purple-400">↓</div>
              </div>
            </div>

            <div className="group relative overflow-hidden rounded-xl border border-white/10 bg-gradient-to-br from-orange-500/10 to-orange-600/10 p-6 backdrop-blur-sm transition-all hover:border-orange-500/30 hover:shadow-lg hover:shadow-orange-500/20">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-slate-400">Sync Folders</p>
                  <p className="mt-2 text-3xl font-bold text-white">
                    {folders.length}
                  </p>
                </div>
                <div className="rounded-lg bg-orange-500/20 p-3">
                  <FolderSync className="h-6 w-6 text-orange-400" />
                </div>
              </div>
            </div>
          </div>

          {/* Sync Folders */}
          <div className="rounded-xl border border-white/10 bg-white/5 p-6 backdrop-blur-sm">
            <div className="mb-6 flex items-center justify-between">
              <h2 className="text-2xl font-bold text-white">Sync Folders</h2>
              <button 
                onClick={handleAddFolder} 
                className="rounded-lg bg-gradient-to-r from-blue-500 to-blue-600 px-4 py-2 text-sm font-medium text-white shadow-lg shadow-blue-500/30 transition-all hover:shadow-xl hover:shadow-blue-500/40 hover:scale-105"
              >
                <FolderPlus className="inline h-4 w-4 mr-2" />
                Add Folder
              </button>
            </div>

            {folders.length === 0 ? (
              <div className="rounded-xl border border-dashed border-slate-700 bg-slate-950/50 py-12 text-center">
                <FolderSync className="mx-auto h-12 w-12 text-slate-600" />
                <p className="mt-4 text-slate-400">No sync folders configured</p>
                <p className="mt-2 text-sm text-slate-500">
                  Add a folder to start syncing files
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {folders.map((folder) => (
                  <div
                    key={folder.id}
                    className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-950/50 p-4"
                  >
                    <div className="flex items-center space-x-4">
                      <FolderSync className="h-5 w-5 text-sky-500" />
                      <div>
                        <p className="font-medium text-slate-100">{folder.localPath}</p>
                        <p className="text-sm text-slate-400">→ {folder.remotePath}</p>
                      </div>
                    </div>
                    <div className="flex items-center space-x-4">
                      <span
                        className={`rounded-full px-3 py-1 text-xs ${
                          folder.enabled
                            ? 'bg-green-500/20 text-green-400'
                            : 'bg-slate-700 text-slate-400'
                        }`}
                      >
                        {folder.enabled ? 'Active' : 'Paused'}
                      </span>
                      <button className="rounded-lg p-2 text-slate-400 hover:bg-slate-800 hover:text-slate-100">
                        <Settings className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* System Info */}
          <div className="rounded-xl border border-slate-800 bg-slate-900/30 p-4 text-center text-xs text-slate-500">
            BaluDesk Desktop Client v1.0.0 - Connected to C++ Backend - Last sync:{' '}
            {syncStats?.lastSync || 'Never'}
          </div>
        </div>
      </main>
    </div>
  );
}
