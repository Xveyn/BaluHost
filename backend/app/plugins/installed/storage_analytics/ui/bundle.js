/**
 * Storage Analytics Plugin UI Bundle
 *
 * This is a simple plugin UI that displays storage analytics.
 * In production, this would be built with Vite/webpack from React/TypeScript sources.
 */

// Since this is loaded dynamically, we use the global React from the parent app
const React = window.React;
const { useState, useEffect } = React;

// API helper
async function fetchPluginApi(endpoint) {
  const token = localStorage.getItem('token');
  const response = await fetch(`/api/plugins/storage_analytics${endpoint}`, {
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
  });
  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }
  return response.json();
}

// Format bytes to human readable
function formatBytes(bytes) {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// Main plugin component
function StorageAnalytics({ user }) {
  const [stats, setStats] = useState(null);
  const [userUsage, setUserUsage] = useState([]);
  const [fileTypes, setFileTypes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [scanning, setScanning] = useState(false);

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    try {
      setLoading(true);
      const [statsRes, usersRes, typesRes] = await Promise.all([
        fetchPluginApi('/stats'),
        fetchPluginApi('/users'),
        fetchPluginApi('/file-types'),
      ]);
      setStats(statsRes.stats);
      setUserUsage(usersRes.users);
      setFileTypes(typesRes.file_types);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function triggerScan() {
    try {
      setScanning(true);
      await fetchPluginApi('/scan');
      await loadData();
    } catch (err) {
      setError(err.message);
    } finally {
      setScanning(false);
    }
  }

  if (loading) {
    return React.createElement('div', {
      className: 'flex items-center justify-center h-64'
    }, React.createElement('div', {
      className: 'animate-spin rounded-full h-8 w-8 border-b-2 border-sky-500'
    }));
  }

  if (error) {
    return React.createElement('div', {
      className: 'p-4 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400'
    }, error);
  }

  return React.createElement('div', { className: 'space-y-6' },
    // Header
    React.createElement('div', { className: 'flex items-center justify-between' },
      React.createElement('div', null,
        React.createElement('h1', { className: 'text-2xl font-semibold text-white' }, 'Storage Analytics'),
        React.createElement('p', { className: 'text-sm text-slate-400 mt-1' }, 'Storage usage insights and breakdown')
      ),
      React.createElement('button', {
        onClick: triggerScan,
        disabled: scanning,
        className: 'px-4 py-2 text-sm font-medium rounded-lg bg-sky-500/20 text-sky-400 hover:bg-sky-500/30 disabled:opacity-50'
      }, scanning ? 'Scanning...' : 'Refresh Data')
    ),

    // Stats Cards
    React.createElement('div', { className: 'grid grid-cols-1 md:grid-cols-3 gap-4' },
      // Total Files
      React.createElement('div', { className: 'rounded-xl border border-slate-800 bg-slate-900/50 p-6' },
        React.createElement('div', { className: 'text-sm text-slate-400 mb-1' }, 'Total Files'),
        React.createElement('div', { className: 'text-2xl font-semibold text-white' },
          stats?.total_files?.toLocaleString() || '0'
        )
      ),
      // Total Size
      React.createElement('div', { className: 'rounded-xl border border-slate-800 bg-slate-900/50 p-6' },
        React.createElement('div', { className: 'text-sm text-slate-400 mb-1' }, 'Total Size'),
        React.createElement('div', { className: 'text-2xl font-semibold text-white' },
          formatBytes(stats?.total_size_bytes || 0)
        )
      ),
      // Total Folders
      React.createElement('div', { className: 'rounded-xl border border-slate-800 bg-slate-900/50 p-6' },
        React.createElement('div', { className: 'text-sm text-slate-400 mb-1' }, 'Total Folders'),
        React.createElement('div', { className: 'text-2xl font-semibold text-white' },
          stats?.total_folders?.toLocaleString() || '0'
        )
      )
    ),

    // Two column layout
    React.createElement('div', { className: 'grid grid-cols-1 lg:grid-cols-2 gap-6' },
      // User Usage
      React.createElement('div', { className: 'rounded-xl border border-slate-800 bg-slate-900/50 p-6' },
        React.createElement('h3', { className: 'text-lg font-medium text-white mb-4' }, 'Usage by User'),
        React.createElement('div', { className: 'space-y-4' },
          userUsage.map((u, i) =>
            React.createElement('div', { key: i, className: 'space-y-2' },
              React.createElement('div', { className: 'flex justify-between text-sm' },
                React.createElement('span', { className: 'text-white' }, u.username),
                React.createElement('span', { className: 'text-slate-400' },
                  `${formatBytes(u.total_size_bytes)} (${u.percentage.toFixed(1)}%)`
                )
              ),
              React.createElement('div', { className: 'h-2 bg-slate-800 rounded-full overflow-hidden' },
                React.createElement('div', {
                  className: 'h-full bg-sky-500 rounded-full',
                  style: { width: `${u.percentage}%` }
                })
              )
            )
          )
        )
      ),

      // File Types
      React.createElement('div', { className: 'rounded-xl border border-slate-800 bg-slate-900/50 p-6' },
        React.createElement('h3', { className: 'text-lg font-medium text-white mb-4' }, 'File Type Distribution'),
        React.createElement('div', { className: 'space-y-3' },
          fileTypes.map((ft, i) =>
            React.createElement('div', { key: i, className: 'flex items-center justify-between' },
              React.createElement('div', { className: 'flex items-center gap-3' },
                React.createElement('div', {
                  className: 'w-3 h-3 rounded-full',
                  style: { backgroundColor: ['#0ea5e9', '#22c55e', '#eab308', '#ef4444', '#8b5cf6'][i % 5] }
                }),
                React.createElement('span', { className: 'text-sm text-white' }, ft.extension)
              ),
              React.createElement('div', { className: 'text-right' },
                React.createElement('div', { className: 'text-sm text-white' }, formatBytes(ft.total_size_bytes)),
                React.createElement('div', { className: 'text-xs text-slate-500' }, `${ft.count} files`)
              )
            )
          )
        )
      )
    )
  );
}

// Dashboard widget component
function StorageOverviewWidget({ user }) {
  const [stats, setStats] = useState(null);

  useEffect(() => {
    fetchPluginApi('/stats')
      .then(res => setStats(res.stats))
      .catch(console.error);
  }, []);

  return React.createElement('div', { className: 'p-4' },
    React.createElement('div', { className: 'text-sm text-slate-400 mb-2' }, 'Storage Overview'),
    stats ? React.createElement('div', null,
      React.createElement('div', { className: 'text-2xl font-semibold text-white' }, formatBytes(stats.total_size_bytes)),
      React.createElement('div', { className: 'text-xs text-slate-500 mt-1' }, `${stats.total_files} files`)
    ) : React.createElement('div', { className: 'text-slate-500' }, 'Loading...')
  );
}

// Export components
export default StorageAnalytics;
export { StorageAnalytics, StorageOverviewWidget };
