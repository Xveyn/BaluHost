/**
 * Plugin Loader for dynamically loading plugin UI bundles
 */
import React from 'react';

// Cache for loaded plugin modules
const moduleCache = new Map<string, Record<string, unknown>>();

// Loading promises to prevent duplicate loads
const loadingPromises = new Map<string, Promise<Record<string, unknown>>>();

/**
 * Load a plugin's JavaScript bundle dynamically
 */
export async function loadPluginBundle(
  pluginName: string,
  bundlePath: string = 'bundle.js'
): Promise<Record<string, unknown>> {
  const cacheKey = `${pluginName}/${bundlePath}`;

  // Return cached module if available
  if (moduleCache.has(cacheKey)) {
    return moduleCache.get(cacheKey)!;
  }

  // Return existing loading promise if one is in progress
  if (loadingPromises.has(cacheKey)) {
    return loadingPromises.get(cacheKey)!;
  }

  // Create new loading promise
  const loadPromise = (async () => {
    try {
      // Add cache-buster to force fresh load
      const cacheBuster = `?v=${Date.now()}`;
      const bundleUrl = `/api/plugins/${pluginName}/ui/${bundlePath}${cacheBuster}`;

      // Dynamically import the bundle
      // Using dynamic import with webpackIgnore to prevent bundler interference
      const module = await import(/* @vite-ignore */ bundleUrl);

      // Cache the loaded module
      moduleCache.set(cacheKey, module);
      loadingPromises.delete(cacheKey);

      return module;
    } catch (error) {
      loadingPromises.delete(cacheKey);
      throw new Error(`Failed to load plugin bundle ${pluginName}: ${error}`);
    }
  })();

  loadingPromises.set(cacheKey, loadPromise);
  return loadPromise;
}

/**
 * Load a specific component from a plugin bundle
 */
export async function loadPluginComponent<T = React.ComponentType>(
  pluginName: string,
  componentName: string = 'default',
  bundlePath: string = 'bundle.js'
): Promise<T> {
  const module = await loadPluginBundle(pluginName, bundlePath);

  const component = module[componentName];
  if (!component) {
    throw new Error(
      `Component '${componentName}' not found in plugin '${pluginName}'`
    );
  }

  return component as T;
}

/**
 * Check if a plugin bundle is already loaded
 */
export function isPluginLoaded(pluginName: string, bundlePath: string = 'bundle.js'): boolean {
  const cacheKey = `${pluginName}/${bundlePath}`;
  return moduleCache.has(cacheKey);
}

/**
 * Clear the plugin cache (useful for development/hot reloading)
 */
export function clearPluginCache(pluginName?: string): void {
  if (pluginName) {
    // Clear specific plugin
    for (const key of moduleCache.keys()) {
      if (key.startsWith(`${pluginName}/`)) {
        moduleCache.delete(key);
      }
    }
  } else {
    // Clear all
    moduleCache.clear();
  }
}

/**
 * Load plugin styles (CSS)
 */
export function loadPluginStyles(
  pluginName: string,
  stylesPath: string
): HTMLLinkElement {
  const styleId = `plugin-styles-${pluginName}`;

  // Check if already loaded
  let linkElement = document.getElementById(styleId) as HTMLLinkElement;
  if (linkElement) {
    return linkElement;
  }

  // Create and append link element
  linkElement = document.createElement('link');
  linkElement.id = styleId;
  linkElement.rel = 'stylesheet';
  linkElement.href = `/api/plugins/${pluginName}/ui/${stylesPath}`;
  document.head.appendChild(linkElement);

  return linkElement;
}

/**
 * Unload plugin styles
 */
export function unloadPluginStyles(pluginName: string): void {
  const styleId = `plugin-styles-${pluginName}`;
  const linkElement = document.getElementById(styleId);
  if (linkElement) {
    linkElement.remove();
  }
}
