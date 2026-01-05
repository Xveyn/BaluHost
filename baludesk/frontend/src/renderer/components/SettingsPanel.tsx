import {
  Settings as SettingsIcon,
  Wifi,
  RotateCcw,
  ChevronDown,
  AlertCircle,
  CheckCircle,
  Server,
  Clock,
  Zap,
  Bell,
  Palette,
  Terminal,
  Shield,
} from 'lucide-react';
import { useState, useEffect } from 'react';
import toast from 'react-hot-toast';
import { useSettings } from '../hooks/useSettings';
import { AppSettings } from '../types';

interface SettingsPanelProps {
  onClose?: () => void;
}

type TabType = 'sync' | 'ui' | 'advanced';

/**
 * SettingsPanel - Modern settings interface with tabs
 * Manages Sync, UI, and Advanced settings with real-time persistence
 */
export default function SettingsPanel({ onClose }: SettingsPanelProps) {
  const { settings, loading, error, updateSetting, updateSettings, saveSettings, resetSettings, hasChanges } =
    useSettings();
  const [activeTab, setActiveTab] = useState<TabType>('sync');
  const [saving, setSaving] = useState(false);
  const [lastSaved, setLastSaved] = useState<string | null>(null);
  const [expandedGroup, setExpandedGroup] = useState<string | null>('sync-basic');

  // Show error toast
  useEffect(() => {
    if (error) {
      toast.error(`Settings Error: ${error}`);
    }
  }, [error]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await saveSettings();
      toast.success('Settings saved successfully!');
      setLastSaved(new Date().toLocaleTimeString());
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    if (window.confirm('Reset all settings to defaults?')) {
      resetSettings();
      toast.success('Settings reset to defaults');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <div className="animate-spin mb-4">
            <SettingsIcon className="h-8 w-8 text-blue-500" />
          </div>
          <p className="text-gray-600 dark:text-gray-400">Loading settings...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-white dark:bg-gray-900">
      {/* Header */}
      <div className="border-b border-gray-200 dark:border-gray-700 p-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <SettingsIcon className="h-8 w-8 text-blue-600 dark:text-blue-400" />
            <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Settings</h1>
          </div>
          {onClose && (
            <button
              onClick={onClose}
              className="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
            >
              ✕
            </button>
          )}
        </div>
        {lastSaved && (
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-2 flex items-center gap-2">
            <CheckCircle className="h-4 w-4 text-green-500" />
            Last saved: {lastSaved}
          </p>
        )}
      </div>

      {/* Tab Navigation */}
      <div className="flex border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800">
        {(['sync', 'ui', 'advanced'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`flex items-center gap-2 px-6 py-4 font-medium capitalize transition-all border-b-2 ${
              activeTab === tab
                ? 'border-b-blue-600 text-blue-600 dark:text-blue-400'
                : 'border-b-transparent text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-300'
            }`}
          >
            {tab === 'sync' && <Clock className="h-5 w-5" />}
            {tab === 'ui' && <Palette className="h-5 w-5" />}
            {tab === 'advanced' && <Terminal className="h-5 w-5" />}
            {tab}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {/* SYNC TAB */}
        {activeTab === 'sync' && (
          <div className="space-y-6 max-w-2xl">
            {/* Basic Settings Group */}
            <SettingsGroup
              title="Sync Behavior"
              icon={<Clock className="h-5 w-5" />}
              expanded={expandedGroup === 'sync-basic'}
              onToggle={() =>
                setExpandedGroup(expandedGroup === 'sync-basic' ? null : 'sync-basic')
              }
            >
              <div className="space-y-4">
                {/* Auto-Start */}
                <ToggleSetting
                  label="Auto-start synchronization"
                  description="Automatically start syncing when the app launches"
                  checked={settings.autoStartSync}
                  onChange={(value) => updateSetting('autoStartSync', value)}
                />

                {/* Sync Interval */}
                <SliderSetting
                  label="Sync Interval"
                  description="How often to check for file changes (in seconds)"
                  value={settings.syncInterval}
                  onChange={(value) => updateSetting('syncInterval', value)}
                  min={5}
                  max={3600}
                  step={5}
                  unit="seconds"
                  preset={(
                    <>
                      <button
                        onClick={() => updateSetting('syncInterval', 30)}
                        className="text-xs px-2 py-1 rounded bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-200"
                      >
                        Fast (30s)
                      </button>
                      <button
                        onClick={() => updateSetting('syncInterval', 60)}
                        className="text-xs px-2 py-1 rounded bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-200"
                      >
                        Normal (1m)
                      </button>
                      <button
                        onClick={() => updateSetting('syncInterval', 300)}
                        className="text-xs px-2 py-1 rounded bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-200"
                      >
                        Slow (5m)
                      </button>
                    </>
                  )}
                />
              </div>
            </SettingsGroup>

            {/* Performance Group */}
            <SettingsGroup
              title="Performance"
              icon={<Zap className="h-5 w-5" />}
              expanded={expandedGroup === 'sync-performance'}
              onToggle={() =>
                setExpandedGroup(expandedGroup === 'sync-performance' ? null : 'sync-performance')
              }
            >
              <div className="space-y-4">
                {/* Max Concurrent Transfers */}
                <SliderSetting
                  label="Concurrent Transfers"
                  description="How many files to upload/download at the same time"
                  value={settings.maxConcurrentTransfers}
                  onChange={(value) => updateSetting('maxConcurrentTransfers', value)}
                  min={1}
                  max={32}
                  step={1}
                  unit="files"
                />

                {/* Bandwidth Limit */}
                <SliderSetting
                  label="Bandwidth Limit"
                  description="Maximum upload/download speed (0 = unlimited)"
                  value={settings.bandwidthLimitMbps}
                  onChange={(value) => updateSetting('bandwidthLimitMbps', value)}
                  min={0}
                  max={1000}
                  step={10}
                  unit="Mbps"
                  preset={(
                    <>
                      <button
                        onClick={() => updateSetting('bandwidthLimitMbps', 0)}
                        className="text-xs px-2 py-1 rounded bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-200"
                      >
                        Unlimited
                      </button>
                      <button
                        onClick={() => updateSetting('bandwidthLimitMbps', 50)}
                        className="text-xs px-2 py-1 rounded bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-200"
                      >
                        50 Mbps
                      </button>
                      <button
                        onClick={() => updateSetting('bandwidthLimitMbps', 100)}
                        className="text-xs px-2 py-1 rounded bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-200"
                      >
                        100 Mbps
                      </button>
                    </>
                  )}
                />
              </div>
            </SettingsGroup>

            {/* Conflict Resolution Group */}
            <SettingsGroup
              title="Conflict Resolution"
              icon={<Shield className="h-5 w-5" />}
              expanded={expandedGroup === 'sync-conflict'}
              onToggle={() =>
                setExpandedGroup(expandedGroup === 'sync-conflict' ? null : 'sync-conflict')
              }
            >
              <div className="space-y-4">
                <SelectSetting
                  label="Default Strategy"
                  description="How to handle file conflicts when both versions changed"
                  value={settings.conflictResolution}
                  onChange={(value) => updateSetting('conflictResolution', value as any)}
                  options={[
                    { value: 'ask', label: 'Ask me (recommended)' },
                    { value: 'local', label: 'Keep local version' },
                    { value: 'remote', label: 'Keep remote version' },
                    { value: 'newer', label: 'Keep newest version' },
                  ]}
                />
              </div>
            </SettingsGroup>
          </div>
        )}

        {/* UI TAB */}
        {activeTab === 'ui' && (
          <div className="space-y-6 max-w-2xl">
            {/* Appearance Group */}
            <SettingsGroup
              title="Appearance"
              icon={<Palette className="h-5 w-5" />}
              expanded={expandedGroup === 'ui-appearance'}
              onToggle={() =>
                setExpandedGroup(expandedGroup === 'ui-appearance' ? null : 'ui-appearance')
              }
            >
              <div className="space-y-4">
                <SelectSetting
                  label="Theme"
                  description="Choose your preferred color scheme"
                  value={settings.theme}
                  onChange={(value) => updateSetting('theme', value as any)}
                  options={[
                    { value: 'dark', label: '🌙 Dark' },
                    { value: 'light', label: '☀️ Light' },
                    { value: 'system', label: '⚙️ System default' },
                  ]}
                />
              </div>
            </SettingsGroup>

            {/* Behavior Group */}
            <SettingsGroup
              title="Application Behavior"
              icon={<SettingsIcon className="h-5 w-5" />}
              expanded={expandedGroup === 'ui-behavior'}
              onToggle={() =>
                setExpandedGroup(expandedGroup === 'ui-behavior' ? null : 'ui-behavior')
              }
            >
              <div className="space-y-4">
                <ToggleSetting
                  label="Start application minimized"
                  description="Launch the app in the system tray"
                  checked={settings.startMinimized}
                  onChange={(value) => updateSetting('startMinimized', value)}
                />
              </div>
            </SettingsGroup>

            {/* Notifications Group */}
            <SettingsGroup
              title="Notifications"
              icon={<Bell className="h-5 w-5" />}
              expanded={expandedGroup === 'ui-notifications'}
              onToggle={() =>
                setExpandedGroup(expandedGroup === 'ui-notifications' ? null : 'ui-notifications')
              }
            >
              <div className="space-y-4">
                <ToggleSetting
                  label="Enable notifications"
                  description="Show system notifications for sync events"
                  checked={settings.showNotifications}
                  onChange={(value) => updateSetting('showNotifications', value)}
                />

                {settings.showNotifications && (
                  <div className="ml-4 space-y-3 border-l-2 border-blue-300 dark:border-blue-700 pl-4">
                    <ToggleSetting
                      label="Sync complete notifications"
                      description="Notify when sync finishes successfully"
                      checked={settings.notifyOnSyncComplete}
                      onChange={(value) => updateSetting('notifyOnSyncComplete', value)}
                      small
                    />

                    <ToggleSetting
                      label="Error notifications"
                      description="Notify when sync encounters errors"
                      checked={settings.notifyOnErrors}
                      onChange={(value) => updateSetting('notifyOnErrors', value)}
                      small
                    />
                  </div>
                )}
              </div>
            </SettingsGroup>
          </div>
        )}

        {/* ADVANCED TAB */}
        {activeTab === 'advanced' && (
          <div className="space-y-6 max-w-2xl">
            {/* Performance Tuning */}
            <SettingsGroup
              title="Performance Tuning"
              icon={<Zap className="h-5 w-5" />}
              expanded={expandedGroup === 'adv-performance'}
              onToggle={() =>
                setExpandedGroup(expandedGroup === 'adv-performance' ? null : 'adv-performance')
              }
            >
              <div className="space-y-4">
                <SliderSetting
                  label="Chunk Size"
                  description="Size of each transfer chunk. Larger = faster on good connections, smaller = better for unstable networks"
                  value={settings.chunkSizeMb}
                  onChange={(value) => updateSetting('chunkSizeMb', value)}
                  min={1}
                  max={100}
                  step={1}
                  unit="MB"
                  preset={(
                    <>
                      <button
                        onClick={() => updateSetting('chunkSizeMb', 5)}
                        className="text-xs px-2 py-1 rounded bg-purple-100 dark:bg-purple-900 text-purple-700 dark:text-purple-200"
                      >
                        Small (5MB)
                      </button>
                      <button
                        onClick={() => updateSetting('chunkSizeMb', 10)}
                        className="text-xs px-2 py-1 rounded bg-purple-100 dark:bg-purple-900 text-purple-700 dark:text-purple-200"
                      >
                        Medium (10MB)
                      </button>
                      <button
                        onClick={() => updateSetting('chunkSizeMb', 50)}
                        className="text-xs px-2 py-1 rounded bg-purple-100 dark:bg-purple-900 text-purple-700 dark:text-purple-200"
                      >
                        Large (50MB)
                      </button>
                    </>
                  )}
                />
              </div>
            </SettingsGroup>

            {/* Debug */}
            <SettingsGroup
              title="Debug & Logging"
              icon={<Terminal className="h-5 w-5" />}
              expanded={expandedGroup === 'adv-debug'}
              onToggle={() =>
                setExpandedGroup(expandedGroup === 'adv-debug' ? null : 'adv-debug')
              }
            >
              <div className="space-y-4">
                <ToggleSetting
                  label="Enable debug logging"
                  description="Log detailed debug information (may impact performance)"
                  checked={settings.enableDebugLogging}
                  onChange={(value) => updateSetting('enableDebugLogging', value)}
                />

                <div className="bg-gray-100 dark:bg-gray-800 p-3 rounded text-xs text-gray-600 dark:text-gray-400 font-mono">
                  <p>App Version: {import.meta.env.VITE_APP_VERSION || 'dev'}</p>
                  <p>Backend: BaluDesk C++ Sync Engine</p>
                  <p>Settings Version: v2.0</p>
                </div>
              </div>
            </SettingsGroup>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="border-t border-gray-200 dark:border-gray-700 p-6 bg-gray-50 dark:bg-gray-800 flex justify-between items-center">
        <div className="flex gap-2">
          <button
            onClick={handleReset}
            className="px-4 py-2 text-gray-700 dark:text-gray-300 bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 rounded-lg transition flex items-center gap-2"
          >
            <RotateCcw className="h-4 w-4" />
            Reset to Defaults
          </button>
        </div>

        <div className="flex gap-3">
          {onClose && (
            <button
              onClick={onClose}
              className="px-4 py-2 text-gray-700 dark:text-gray-300 bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 rounded-lg transition"
            >
              Close
            </button>
          )}
          <button
            onClick={handleSave}
            disabled={!hasChanges || saving}
            className="px-6 py-2 bg-blue-600 text-white hover:bg-blue-700 rounded-lg transition disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 font-medium"
          >
            {saving ? 'Saving...' : 'Save Settings'}
            {!saving && hasChanges && <span className="h-2 w-2 bg-red-400 rounded-full" />}
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * Reusable Setting Components
 */

interface SettingsGroupProps {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
  expanded: boolean;
  onToggle: () => void;
}

function SettingsGroup({ title, icon, children, expanded, onToggle }: SettingsGroupProps) {
  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between p-4 hover:bg-gray-50 dark:hover:bg-gray-800 transition"
      >
        <div className="flex items-center gap-3">
          <div className="text-gray-600 dark:text-gray-400">{icon}</div>
          <h3 className="font-semibold text-gray-900 dark:text-white">{title}</h3>
        </div>
        <ChevronDown
          className={`h-5 w-5 transition-transform text-gray-600 dark:text-gray-400 ${
            expanded ? 'rotate-180' : ''
          }`}
        />
      </button>

      {expanded && (
        <div className="border-t border-gray-200 dark:border-gray-700 p-4 bg-gray-50 dark:bg-gray-800">
          {children}
        </div>
      )}
    </div>
  );
}

interface ToggleSettingProps {
  label: string;
  description?: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  small?: boolean;
}

function ToggleSetting({ label, description, checked, onChange, small = false }: ToggleSettingProps) {
  return (
    <div className="flex items-start justify-between">
      <div className={small ? 'text-sm' : ''}>
        <label className={`font-medium text-gray-900 dark:text-white ${small ? 'text-sm' : 'text-base'}`}>
          {label}
        </label>
        {description && (
          <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">{description}</p>
        )}
      </div>
      <button
        onClick={() => onChange(!checked)}
        className={`relative h-6 w-11 rounded-full transition-colors ${
          checked ? 'bg-blue-600' : 'bg-gray-300 dark:bg-gray-600'
        }`}
      >
        <div
          className={`absolute h-5 w-5 bg-white rounded-full top-0.5 transition-transform ${
            checked ? 'translate-x-5' : 'translate-x-0.5'
          }`}
        />
      </button>
    </div>
  );
}

interface SliderSettingProps {
  label: string;
  description?: string;
  value: number;
  onChange: (value: number) => void;
  min: number;
  max: number;
  step: number;
  unit?: string;
  preset?: React.ReactNode;
}

function SliderSetting({
  label,
  description,
  value,
  onChange,
  min,
  max,
  step,
  unit,
  preset,
}: SliderSettingProps) {
  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <label className="font-medium text-gray-900 dark:text-white">{label}</label>
        <span className="text-sm font-mono bg-gray-100 dark:bg-gray-800 px-2 py-1 rounded text-gray-700 dark:text-gray-300">
          {value} {unit}
        </span>
      </div>
      {description && <p className="text-xs text-gray-600 dark:text-gray-400 mb-2">{description}</p>}

      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full h-2 bg-gray-300 dark:bg-gray-600 rounded-lg appearance-none cursor-pointer"
      />

      {preset && <div className="flex gap-2 mt-3">{preset}</div>}
    </div>
  );
}

interface SelectSettingProps {
  label: string;
  description?: string;
  value: string;
  onChange: (value: string) => void;
  options: Array<{ value: string; label: string }>;
}

function SelectSetting({
  label,
  description,
  value,
  onChange,
  options,
}: SelectSettingProps) {
  return (
    <div>
      <label className="font-medium text-gray-900 dark:text-white block mb-2">{label}</label>
      {description && <p className="text-xs text-gray-600 dark:text-gray-400 mb-2">{description}</p>}

      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full px-4 py-2 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white focus:outline-none focus:border-blue-500 transition"
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </div>
  );
}
