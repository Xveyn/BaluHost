import { useEffect, useState } from 'react';
import { Cloud, FolderSync, Settings, LogOut, Activity } from 'lucide-react';
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
    <div className="min-h-screen bg-slate-950">
      {/* Header */}
      <header className="border-b border-slate-800 bg-slate-900/50 backdrop-blur-sm">
        <div className="flex h-16 items-center justify-between px-6">
          <div className="flex items-center space-x-3">
            <Cloud className="h-6 w-6 text-sky-500" />
            <h1 className="text-lg font-semibold text-slate-100">BaluDesk</h1>
          </div>

          <div className="flex items-center space-x-4">
            <div className="text-sm text-slate-400">
              <span className="text-slate-300">{user.username}</span>
              {user.serverUrl && (
                <span className="ml-2 text-slate-500">
                  @ {new URL(user.serverUrl).hostname}
                </span>
              )}
            </div>
            <button
              onClick={handleLogout}
              className="rounded-lg p-2 text-slate-400 hover:bg-slate-800 hover:text-slate-100"
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
          <div className="grid gap-4 md:grid-cols-4">
            <div className="card border border-slate-800 bg-slate-900/50 p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-slate-400">Status</p>
                  <p className="mt-2 text-2xl font-semibold text-slate-100">
                    {syncStats?.status || 'Idle'}
                  </p>
                </div>
                <Activity className="h-8 w-8 text-sky-500" />
              </div>
            </div>

            <div className="card border border-slate-800 bg-slate-900/50 p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-slate-400">Upload Queue</p>
                  <p className="mt-2 text-2xl font-semibold text-slate-100">
                    {syncStats?.pendingUploads || 0}
                  </p>
                </div>
                <div className="text-sky-500">↑</div>
              </div>
            </div>

            <div className="card border border-slate-800 bg-slate-900/50 p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-slate-400">Download Queue</p>
                  <p className="mt-2 text-2xl font-semibold text-slate-100">
                    {syncStats?.pendingDownloads || 0}
                  </p>
                </div>
                <div className="text-sky-500">↓</div>
              </div>
            </div>

            <div className="card border border-slate-800 bg-slate-900/50 p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-slate-400">Sync Folders</p>
                  <p className="mt-2 text-2xl font-semibold text-slate-100">
                    {folders.length}
                  </p>
                </div>
                <FolderSync className="h-8 w-8 text-sky-500" />
              </div>
            </div>
          </div>

          {/* Sync Folders */}
          <div className="card border border-slate-800 bg-slate-900/50 p-6">
            <div className="mb-6 flex items-center justify-between">
              <h2 className="text-xl font-semibold text-slate-100">Sync Folders</h2>
              <button onClick={handleAddFolder} className="btn btn-primary">
                + Add Folder
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
