/**
 * Plugin SDK for BaluHost
 *
 * Exposes React, UI components, icons, toast notifications, and API utilities
 * to plugins via window.BaluHost
 *
 * Usage in plugins:
 *   const { React, ui, icons, toast, api, utils } = window.BaluHost;
 *   const { Button, Card, Modal } = ui;
 *   const { Disc, Download, Flame } = icons;
 */

import React, {
  useState,
  useEffect,
  useCallback,
  useMemo,
  useRef,
  useContext,
  createContext,
  memo,
  forwardRef,
} from 'react';
import * as LucideIcons from 'lucide-react';
import toast from 'react-hot-toast';
import { apiClient } from './api';
import { formatNumber } from './formatters';

// Import UI components
import {
  Button,
  Card,
  CardHeader,
  CardContent,
  CardFooter,
  Badge,
  Modal,
  Input,
  Textarea,
  Select,
  ProgressBar,
  Spinner,
  LoadingOverlay,
  EmptyState,
  Tabs,
  TabPanel,
} from '../components/ui';

// Utility functions
function formatBytes(bytes: number | null | undefined): string {
  if (!bytes || bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  const value = bytes / Math.pow(k, i);
  return `${value >= 100 ? Math.round(value) : formatNumber(value, value < 10 ? 2 : 1)} ${sizes[i]}`;
}

function formatDate(date: string | Date, options?: Intl.DateTimeFormatOptions): string {
  const d = typeof date === 'string' ? new Date(date) : date;
  return d.toLocaleString(undefined, options);
}

function formatDuration(seconds: number | null | undefined): string {
  if (!seconds) return '';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

function formatUptime(seconds: number | null | undefined): string {
  if (!seconds) return '-';
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
  return `${Math.floor(seconds / 86400)}d ${Math.floor((seconds % 86400) / 3600)}h`;
}

// Simple className merger (like clsx/tailwind-merge)
function cn(...classes: (string | undefined | null | false)[]): string {
  return classes.filter(Boolean).join(' ');
}

// API wrapper with simplified interface
const pluginApi = {
  get: async <T = any>(url: string): Promise<T> => {
    const response = await apiClient.get(url);
    return response.data;
  },
  post: async <T = any>(url: string, data?: any): Promise<T> => {
    const response = await apiClient.post(url, data);
    return response.data;
  },
  put: async <T = any>(url: string, data?: any): Promise<T> => {
    const response = await apiClient.put(url, data);
    return response.data;
  },
  patch: async <T = any>(url: string, data?: any): Promise<T> => {
    const response = await apiClient.patch(url, data);
    return response.data;
  },
  delete: async <T = any>(url: string): Promise<T> => {
    const response = await apiClient.delete(url);
    return response.data;
  },
};

// Toast wrapper
const pluginToast = {
  success: (message: string, options?: { duration?: number }) =>
    toast.success(message, options),
  error: (message: string, options?: { duration?: number }) =>
    toast.error(message, options),
  loading: (message: string, options?: { duration?: number }) =>
    toast.loading(message, options),
  promise: <T,>(
    promise: Promise<T>,
    msgs: { loading: string; success: string; error: string }
  ) => toast.promise(promise, msgs),
  dismiss: (toastId?: string) => toast.dismiss(toastId),
  custom: toast,
};

// BaluHost SDK interface
export interface BaluHostSDK {
  React: typeof React;
  hooks: {
    useState: typeof useState;
    useEffect: typeof useEffect;
    useCallback: typeof useCallback;
    useMemo: typeof useMemo;
    useRef: typeof useRef;
    useContext: typeof useContext;
    createContext: typeof createContext;
    memo: typeof memo;
    forwardRef: typeof forwardRef;
  };
  ui: {
    Button: typeof Button;
    Card: typeof Card;
    CardHeader: typeof CardHeader;
    CardContent: typeof CardContent;
    CardFooter: typeof CardFooter;
    Badge: typeof Badge;
    Modal: typeof Modal;
    Input: typeof Input;
    Textarea: typeof Textarea;
    Select: typeof Select;
    ProgressBar: typeof ProgressBar;
    Spinner: typeof Spinner;
    LoadingOverlay: typeof LoadingOverlay;
    EmptyState: typeof EmptyState;
    Tabs: typeof Tabs;
    TabPanel: typeof TabPanel;
  };
  icons: typeof LucideIcons;
  toast: typeof pluginToast;
  api: typeof pluginApi;
  utils: {
    formatBytes: typeof formatBytes;
    formatDate: typeof formatDate;
    formatDuration: typeof formatDuration;
    formatUptime: typeof formatUptime;
    cn: typeof cn;
  };
}

// Declare global window extension
declare global {
  interface Window {
    BaluHost: BaluHostSDK;
    BaluHostPlugins: Record<string, any>;
  }
}

/**
 * Initialize the Plugin SDK
 * Call this before rendering the app to make the SDK available to plugins
 */
export function initPluginSDK(): void {
  const sdk: BaluHostSDK = {
    // React core
    React,

    // React hooks
    hooks: {
      useState,
      useEffect,
      useCallback,
      useMemo,
      useRef,
      useContext,
      createContext,
      memo,
      forwardRef,
    },

    // UI Components
    ui: {
      Button,
      Card,
      CardHeader,
      CardContent,
      CardFooter,
      Badge,
      Modal,
      Input,
      Textarea,
      Select,
      ProgressBar,
      Spinner,
      LoadingOverlay,
      EmptyState,
      Tabs,
      TabPanel,
    },

    // Lucide React Icons (all of them)
    icons: LucideIcons,

    // Toast notifications
    toast: pluginToast,

    // API client
    api: pluginApi,

    // Utility functions
    utils: {
      formatBytes,
      formatDate,
      formatDuration,
      formatUptime,
      cn,
    },
  };

  // Expose on window
  window.BaluHost = sdk;

  // Also keep React on window.React for backwards compatibility
  (window as any).React = React;

  // Initialize plugins registry if not exists
  if (!window.BaluHostPlugins) {
    window.BaluHostPlugins = {};
  }

  console.log('[BaluHost SDK] Initialized successfully');
}

export default initPluginSDK;
