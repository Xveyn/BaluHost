import { Cloud, Activity, Files, FolderSync, AlertCircle, LogOut, Settings as SettingsIcon } from 'lucide-react';
import { useNavigate, useLocation } from 'react-router-dom';
import toast from 'react-hot-toast';

interface MainLayoutProps {
  user: { username: string; serverUrl?: string };
  onLogout: () => void;
  children: React.ReactNode;
  conflictCount?: number;
}

interface NavTab {
  id: string;
  label: string;
  path: string;
  icon: React.ReactNode;
  badge?: number;
}

export default function MainLayout({ user, onLogout, children, conflictCount = 0 }: MainLayoutProps) {
  const navigate = useNavigate();
  const location = useLocation();

  const navTabs: NavTab[] = [
    {
      id: 'dashboard',
      label: 'Dashboard',
      path: '/',
      icon: <Activity className="h-4 w-4" />,
    },
    {
      id: 'sync',
      label: 'Sync',
      path: '/sync',
      icon: <FolderSync className="h-4 w-4" />,
    },
    {
      id: 'files',
      label: 'Files',
      path: '/files',
      icon: <Files className="h-4 w-4" />,
    },
    {
      id: 'conflicts',
      label: 'Conflicts',
      path: '/conflicts',
      icon: <AlertCircle className="h-4 w-4" />,
      badge: conflictCount > 0 ? conflictCount : undefined,
    },
  ];

  const isActiveTab = (path: string) => {
    if (path === '/' && location.pathname === '/') return true;
    if (path !== '/' && location.pathname.startsWith(path)) return true;
    return false;
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
      <header className="border-b border-white/10 bg-white/5 backdrop-blur-md sticky top-0 z-40">
        <div className="flex h-16 items-center justify-between px-6">
          {/* Logo */}
          <div className="flex items-center space-x-3">
            <div className="rounded-lg bg-gradient-to-br from-blue-500 to-blue-600 p-2">
              <Cloud className="h-5 w-5 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-white">BaluDesk</h1>
              <p className="text-xs text-slate-400">Desktop Client</p>
            </div>
          </div>

          {/* Navigation Tabs */}
          <nav className="flex items-center space-x-1">
            {navTabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => navigate(tab.path)}
                className={`flex items-center space-x-2 rounded-lg px-4 py-2 text-sm font-medium transition-all relative ${
                  isActiveTab(tab.path)
                    ? 'bg-white/20 text-white shadow-lg shadow-blue-500/20'
                    : 'text-slate-300 hover:bg-white/10'
                }`}
              >
                {tab.icon}
                <span>{tab.label}</span>
                {tab.badge && (
                  <span className="ml-2 inline-flex items-center justify-center h-5 w-5 rounded-full bg-red-500 text-white text-xs font-bold">
                    {tab.badge}
                  </span>
                )}
              </button>
            ))}
          </nav>

          {/* User Profile & Logout */}
          <div className="flex items-center space-x-3">
            <button
              onClick={() => navigate('/settings')}
              className={`rounded-lg p-2 transition-all ${
                isActiveTab('/settings')
                  ? 'bg-white/20 text-white'
                  : 'text-slate-400 hover:bg-white/10 hover:text-white'
              }`}
              title="Settings"
            >
              <SettingsIcon className="h-5 w-5" />
            </button>

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
        <div className="mx-auto max-w-7xl">
          {children}
        </div>
      </main>
    </div>
  );
}
