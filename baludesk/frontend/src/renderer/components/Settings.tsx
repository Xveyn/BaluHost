import React, { useState, useEffect } from 'react';
import { AppSettings, SettingsResponse } from '../types';
import UserProfile from './UserProfile';

interface SettingsProps {
  onClose?: () => void;
}

const defaultSettings: AppSettings = {
  serverUrl: 'http://localhost',
  serverPort: 8000,
  username: '',
  rememberPassword: false,
  autoStartSync: true,
  syncInterval: 60,
  maxConcurrentTransfers: 4,
  bandwidthLimitMbps: 0,
  conflictResolution: 'ask',
  theme: 'dark',
  language: 'en',
  startMinimized: false,
  showNotifications: true,
  notifyOnSyncComplete: true,
  notifyOnErrors: true,
  enableDebugLogging: false,
  chunkSizeMb: 10,
};

const Settings: React.FC<SettingsProps> = ({ onClose }) => {
  const [settings, setSettings] = useState<AppSettings>(defaultSettings);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [activeTab, setActiveTab] = useState<'profile' | 'connection' | 'sync' | 'ui' | 'advanced'>('profile');
  const [userId, setUserId] = useState<string | null>(null);

  useEffect(() => {
    loadSettings();
    loadUserId();
  }, []);

  const loadUserId = async () => {
    try {
      const result = await (window as any).electronAPI.getUserInfo?.();
      if (result?.success && result?.data?.id) {
        setUserId(result.data.id);
      }
    } catch (error) {
      console.error('Failed to load user info:', error);
    }
  };

  const loadSettings = async () => {
    try {
      const result = await (window as any).electronAPI.getSettings();
      if (result.success && result.data) {
        setSettings(prev => ({ ...prev, ...result.data }));
      }
    } catch (error) {
      setMessage({ type: 'error', text: 'Failed to load settings' });
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const result = await (window as any).electronAPI.updateSettings(settings);
      if (result.success) {
        setMessage({ type: 'success', text: 'Settings saved successfully!' });
        setTimeout(() => setMessage(null), 3000);
      } else {
        setMessage({ type: 'error', text: result.error || 'Failed to save settings' });
      }
    } catch (error) {
      setMessage({ type: 'error', text: 'Error saving settings' });
    } finally {
      setSaving(false);
    }
  };

  const handleChange = (key: keyof AppSettings, value: any) => {
    setSettings(prev => ({ ...prev, [key]: value }));
  };

  if (loading) {
    return <div className="p-8 text-center">Loading settings...</div>;
  }

  return (
    <div className="h-full flex flex-col bg-slate-900 text-white">
      {/* Header */}
      <div className="border-b border-slate-700 p-6">
        <div className="flex justify-between items-center">
          <h1 className="text-2xl font-bold">Settings</h1>
          {onClose && (
            <button
              onClick={onClose}
              className="text-slate-400 hover:text-white"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-slate-700 bg-slate-800">
        {(['profile', 'connection', 'sync', 'ui', 'advanced'] as const).map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-6 py-3 font-medium capitalize transition-colors ${
              activeTab === tab
                ? 'border-b-2 border-blue-500 text-blue-400'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {message && (
          <div
            className={`mb-4 p-4 rounded-lg ${
              message.type === 'success'
                ? 'bg-green-900 text-green-200'
                : 'bg-red-900 text-red-200'
            }`}
          >
            {message.text}
          </div>
        )}

        {/* Profile Tab */}
        {activeTab === 'profile' && userId && (
          <UserProfile
            serverUrl={settings.serverUrl}
            user={{
              id: userId,
              username: settings.username,
            }}
          />
        )}

        {/* Connection Settings */}
        {activeTab === 'connection' && (
          <div className="space-y-6">
            <h2 className="text-xl font-semibold mb-4">Server Connection</h2>
            
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-2">Server URL</label>
                <input
                  type="text"
                  value={settings.serverUrl}
                  onChange={e => handleChange('serverUrl', e.target.value)}
                  className="w-full px-4 py-2 bg-slate-800 border border-slate-700 rounded text-white focus:outline-none focus:border-blue-500"
                  placeholder="http://localhost"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium mb-2">Port</label>
                <input
                  type="number"
                  value={settings.serverPort}
                  onChange={e => handleChange('serverPort', parseInt(e.target.value))}
                  className="w-full px-4 py-2 bg-slate-800 border border-slate-700 rounded text-white focus:outline-none focus:border-blue-500"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium mb-2">Username</label>
              <input
                type="text"
                value={settings.username}
                onChange={e => handleChange('username', e.target.value)}
                className="w-full px-4 py-2 bg-slate-800 border border-slate-700 rounded text-white focus:outline-none focus:border-blue-500"
              />
            </div>

            <div className="flex items-center space-x-3">
              <input
                type="checkbox"
                id="rememberPassword"
                checked={settings.rememberPassword}
                onChange={e => handleChange('rememberPassword', e.target.checked)}
                className="w-4 h-4 rounded"
              />
              <label htmlFor="rememberPassword" className="text-sm">
                Remember password
              </label>
            </div>
          </div>
        )}

        {/* Sync Settings */}
        {activeTab === 'sync' && (
          <div className="space-y-6">
            <h2 className="text-xl font-semibold mb-4">Sync Behavior</h2>

            <div className="flex items-center space-x-3">
              <input
                type="checkbox"
                id="autoStartSync"
                checked={settings.autoStartSync}
                onChange={e => handleChange('autoStartSync', e.target.checked)}
                className="w-4 h-4 rounded"
              />
              <label htmlFor="autoStartSync" className="text-sm">
                Auto-start synchronization on app launch
              </label>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-2">
                  Sync Interval (seconds)
                </label>
                <input
                  type="number"
                  value={settings.syncInterval}
                  onChange={e => handleChange('syncInterval', parseInt(e.target.value))}
                  className="w-full px-4 py-2 bg-slate-800 border border-slate-700 rounded text-white focus:outline-none focus:border-blue-500"
                  min="5"
                  max="3600"
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">
                  Max Concurrent Transfers
                </label>
                <input
                  type="number"
                  value={settings.maxConcurrentTransfers}
                  onChange={e => handleChange('maxConcurrentTransfers', parseInt(e.target.value))}
                  className="w-full px-4 py-2 bg-slate-800 border border-slate-700 rounded text-white focus:outline-none focus:border-blue-500"
                  min="1"
                  max="32"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium mb-2">
                Bandwidth Limit (Mbps, 0 = unlimited)
              </label>
              <input
                type="number"
                value={settings.bandwidthLimitMbps}
                onChange={e => handleChange('bandwidthLimitMbps', parseInt(e.target.value))}
                className="w-full px-4 py-2 bg-slate-800 border border-slate-700 rounded text-white focus:outline-none focus:border-blue-500"
                min="0"
                step="10"
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-2">
                Conflict Resolution Strategy
              </label>
              <select
                value={settings.conflictResolution}
                onChange={e => handleChange('conflictResolution', e.target.value)}
                className="w-full px-4 py-2 bg-slate-800 border border-slate-700 rounded text-white focus:outline-none focus:border-blue-500"
              >
                <option value="ask">Ask me (default)</option>
                <option value="local">Keep local version</option>
                <option value="remote">Keep remote version</option>
                <option value="newer">Keep newest</option>
              </select>
            </div>
          </div>
        )}

        {/* UI Preferences */}
        {activeTab === 'ui' && (
          <div className="space-y-6">
            <h2 className="text-xl font-semibold mb-4">User Interface</h2>

            <div>
              <label className="block text-sm font-medium mb-2">Theme</label>
              <select
                value={settings.theme}
                onChange={e => handleChange('theme', e.target.value)}
                className="w-full px-4 py-2 bg-slate-800 border border-slate-700 rounded text-white focus:outline-none focus:border-blue-500"
              >
                <option value="dark">Dark</option>
                <option value="light">Light</option>
                <option value="system">System</option>
              </select>
            </div>

            <div className="flex items-center space-x-3">
              <input
                type="checkbox"
                id="startMinimized"
                checked={settings.startMinimized}
                onChange={e => handleChange('startMinimized', e.target.checked)}
                className="w-4 h-4 rounded"
              />
              <label htmlFor="startMinimized" className="text-sm">
                Start application minimized
              </label>
            </div>

            <div className="border-t border-slate-700 pt-4">
              <h3 className="font-medium mb-3">Notifications</h3>

              <div className="space-y-3">
                <div className="flex items-center space-x-3">
                  <input
                    type="checkbox"
                    id="showNotifications"
                    checked={settings.showNotifications}
                    onChange={e => handleChange('showNotifications', e.target.checked)}
                    className="w-4 h-4 rounded"
                  />
                  <label htmlFor="showNotifications" className="text-sm">
                    Enable notifications
                  </label>
                </div>

                <div className="flex items-center space-x-3 ml-6">
                  <input
                    type="checkbox"
                    id="notifyOnSyncComplete"
                    checked={settings.notifyOnSyncComplete}
                    onChange={e => handleChange('notifyOnSyncComplete', e.target.checked)}
                    className="w-4 h-4 rounded"
                    disabled={!settings.showNotifications}
                  />
                  <label htmlFor="notifyOnSyncComplete" className="text-sm">
                    Notify on sync complete
                  </label>
                </div>

                <div className="flex items-center space-x-3 ml-6">
                  <input
                    type="checkbox"
                    id="notifyOnErrors"
                    checked={settings.notifyOnErrors}
                    onChange={e => handleChange('notifyOnErrors', e.target.checked)}
                    className="w-4 h-4 rounded"
                    disabled={!settings.showNotifications}
                  />
                  <label htmlFor="notifyOnErrors" className="text-sm">
                    Notify on errors
                  </label>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Advanced Settings */}
        {activeTab === 'advanced' && (
          <div className="space-y-6">
            <h2 className="text-xl font-semibold mb-4">Advanced</h2>

            <div className="flex items-center space-x-3">
              <input
                type="checkbox"
                id="enableDebugLogging"
                checked={settings.enableDebugLogging}
                onChange={e => handleChange('enableDebugLogging', e.target.checked)}
                className="w-4 h-4 rounded"
              />
              <label htmlFor="enableDebugLogging" className="text-sm">
                Enable debug logging
              </label>
            </div>

            <div>
              <label className="block text-sm font-medium mb-2">
                Chunk Size (MB)
              </label>
              <input
                type="number"
                value={settings.chunkSizeMb}
                onChange={e => handleChange('chunkSizeMb', parseInt(e.target.value))}
                className="w-full px-4 py-2 bg-slate-800 border border-slate-700 rounded text-white focus:outline-none focus:border-blue-500"
                min="1"
                max="100"
              />
              <p className="text-xs text-slate-400 mt-1">
                Larger chunks = faster for good connections, smaller = better for unstable networks
              </p>
            </div>

            <div className="bg-slate-800 p-4 rounded-lg">
              <h3 className="font-medium mb-2">Debug Information</h3>
              <p className="text-xs text-slate-400">
                App Version: {import.meta.env.VITE_APP_VERSION || 'dev'}
              </p>
              <p className="text-xs text-slate-400">
                Backend: BaluDesk C++ Sync Engine
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="border-t border-slate-700 p-6 flex justify-end gap-3 bg-slate-800">
        {onClose && (
          <button
            onClick={onClose}
            className="px-6 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors"
          >
            Cancel
          </button>
        )}
        <button
          onClick={handleSave}
          disabled={saving}
          className="px-6 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {saving ? 'Saving...' : 'Save Settings'}
        </button>
      </div>
    </div>
  );
};

export default Settings;
