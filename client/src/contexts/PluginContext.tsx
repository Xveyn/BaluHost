/**
 * Plugin Context for managing plugin state across the application
 */
import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import type {
  PluginInfo,
  PluginUIInfo,
  PluginNavItem,
} from '../api/plugins';
import {
  listPlugins,
  getUIManifest,
} from '../api/plugins';

interface PluginContextType {
  plugins: PluginInfo[];
  enabledPlugins: PluginUIInfo[];
  pluginNavItems: PluginNavItem[];
  isLoading: boolean;
  error: string | null;
  refreshPlugins: () => Promise<void>;
}

const PluginContext = createContext<PluginContextType | undefined>(undefined);

interface PluginProviderProps {
  children: React.ReactNode;
}

export function PluginProvider({ children }: PluginProviderProps) {
  const [plugins, setPlugins] = useState<PluginInfo[]>([]);
  const [enabledPlugins, setEnabledPlugins] = useState<PluginUIInfo[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadPlugins = useCallback(async () => {
    // Only load plugins if user is authenticated
    const token = localStorage.getItem('token');
    if (!token) {
      setIsLoading(false);
      return;
    }

    try {
      setIsLoading(true);
      setError(null);

      // Fetch both plugin list and UI manifest in parallel
      const [pluginList, manifest] = await Promise.all([
        listPlugins(),
        getUIManifest(),
      ]);

      setPlugins(pluginList?.plugins ?? []);
      setEnabledPlugins(manifest?.plugins ?? []);
    } catch (err) {
      console.error('Failed to load plugins:', err);
      setError(err instanceof Error ? err.message : 'Failed to load plugins');
      // Ensure arrays stay as arrays on error
      setPlugins([]);
      setEnabledPlugins([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPlugins();
  }, [loadPlugins]);

  // Flatten nav items from all enabled plugins, sorted by order
  const pluginNavItems = (enabledPlugins ?? [])
    .flatMap((plugin) =>
      (plugin.nav_items ?? []).map((item) => ({
        ...item,
        // Prefix path with plugin name for routing
        path: `${plugin.name}/${item.path}`,
        // Include plugin name for context
        _pluginName: plugin.name,
        _pluginDisplayName: plugin.display_name,
      }))
    )
    .sort((a, b) => a.order - b.order);

  const value: PluginContextType = {
    plugins,
    enabledPlugins,
    pluginNavItems,
    isLoading,
    error,
    refreshPlugins: loadPlugins,
  };

  return (
    <PluginContext.Provider value={value}>
      {children}
    </PluginContext.Provider>
  );
}

export function usePlugins() {
  const context = useContext(PluginContext);
  if (context === undefined) {
    throw new Error('usePlugins must be used within a PluginProvider');
  }
  return context;
}

/**
 * Hook to check if a specific plugin is enabled
 */
export function usePluginEnabled(pluginName: string): boolean {
  const { enabledPlugins } = usePlugins();
  return enabledPlugins.some((p) => p.name === pluginName);
}

/**
 * Hook to get a specific plugin's info
 */
export function usePluginInfo(pluginName: string): PluginInfo | undefined {
  const { plugins } = usePlugins();
  return plugins.find((p) => p.name === pluginName);
}
