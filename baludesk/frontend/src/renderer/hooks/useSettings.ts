import { useState, useCallback, useEffect } from 'react';
import { AppSettings, SettingsResponse } from '../types';

// Type assertion for Electron API
declare const window: any;

const DEFAULT_SETTINGS: AppSettings = {
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

interface UseSettingsReturn {
  settings: AppSettings;
  loading: boolean;
  error: string | null;
  updateSetting: <K extends keyof AppSettings>(key: K, value: AppSettings[K]) => void;
  updateSettings: (partial: Partial<AppSettings>) => void;
  saveSettings: () => Promise<void>;
  resetSettings: () => void;
  hasChanges: boolean;
}

/**
 * Hook for managing application settings
 * Handles loading, updating, and persisting settings
 */
export function useSettings(): UseSettingsReturn {
  const [settings, setSettings] = useState<AppSettings>(DEFAULT_SETTINGS);
  const [originalSettings, setOriginalSettings] = useState<AppSettings>(DEFAULT_SETTINGS);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Load settings on mount
  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response: SettingsResponse = await window.electronAPI?.getSettings?.();

      if (response?.success && response?.data) {
        const loadedSettings = { ...DEFAULT_SETTINGS, ...response.data };
        setSettings(loadedSettings);
        setOriginalSettings(loadedSettings);
      } else if (response?.error) {
        throw new Error(response.error);
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Failed to load settings';
      setError(errorMsg);
      console.error('Settings load error:', err);
      // Use defaults on error
      setSettings(DEFAULT_SETTINGS);
      setOriginalSettings(DEFAULT_SETTINGS);
    } finally {
      setLoading(false);
    }
  }, []);

  // Update single setting
  const updateSetting = useCallback(<K extends keyof AppSettings>(key: K, value: AppSettings[K]) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
  }, []);

  // Update multiple settings
  const updateSettings = useCallback((partial: Partial<AppSettings>) => {
    setSettings((prev) => ({ ...prev, ...partial }));
  }, []);

  // Save settings to backend
  const saveSettings = useCallback(async () => {
    setError(null);

    try {
      const response: SettingsResponse = await window.electronAPI?.updateSettings?.(settings);

      if (response?.success) {
        setOriginalSettings(settings);
        return;
      } else if (response?.error) {
        throw new Error(response.error);
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Failed to save settings';
      setError(errorMsg);
      throw err;
    }
  }, [settings]);

  // Reset to original settings
  const resetSettings = useCallback(() => {
    setSettings(originalSettings);
    setError(null);
  }, [originalSettings]);

  // Check if there are unsaved changes
  const hasChanges = JSON.stringify(settings) !== JSON.stringify(originalSettings);

  return {
    settings,
    loading,
    error,
    updateSetting,
    updateSettings,
    saveSettings,
    resetSettings,
    hasChanges,
  };
}
