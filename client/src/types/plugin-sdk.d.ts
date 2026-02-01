/**
 * TypeScript definitions for BaluHost Plugin SDK
 *
 * These types are available to plugin developers for type-checking their plugins.
 * The SDK is exposed on window.BaluHost after the main app initializes.
 */

import type React from 'react';
import type { LucideIcon, LucideProps } from 'lucide-react';

// UI Component Props
export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'danger' | 'success' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
  loading?: boolean;
  icon?: React.ReactNode;
}

export interface CardProps {
  children: React.ReactNode;
  className?: string;
  hover?: boolean;
}

export interface CardHeaderProps {
  children: React.ReactNode;
  className?: string;
}

export interface CardContentProps {
  children: React.ReactNode;
  className?: string;
}

export interface CardFooterProps {
  children: React.ReactNode;
  className?: string;
}

export interface BadgeProps {
  children: React.ReactNode;
  variant?: 'default' | 'success' | 'warning' | 'danger' | 'info';
  pulse?: boolean;
  className?: string;
}

export interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
  size?: 'sm' | 'md' | 'lg' | 'xl';
}

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
}

export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
  helperText?: string;
}

export interface SelectOption {
  value: string | number;
  label: string;
}

export interface SelectProps extends Omit<React.SelectHTMLAttributes<HTMLSelectElement>, 'children'> {
  label?: string;
  error?: string;
  helperText?: string;
  options: SelectOption[];
  placeholder?: string;
}

export interface ProgressBarProps {
  progress: number;
  variant?: 'default' | 'success' | 'warning' | 'danger';
  showLabel?: boolean;
  animated?: boolean;
  className?: string;
  size?: 'sm' | 'md' | 'lg';
}

export interface SpinnerProps {
  size?: 'sm' | 'md' | 'lg' | 'xl';
  className?: string;
  label?: string;
}

export interface LoadingOverlayProps {
  label?: string;
}

export interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}

export interface Tab {
  id: string;
  label: string;
  icon?: LucideIcon;
  count?: number;
}

export interface TabsProps {
  tabs: Tab[];
  activeTab: string;
  onChange: (tabId: string) => void;
  className?: string;
}

export interface TabPanelProps {
  children: React.ReactNode;
  id: string;
  activeTab: string;
  className?: string;
}

// Toast types
export interface ToastOptions {
  duration?: number;
}

export interface PluginToast {
  success: (message: string, options?: ToastOptions) => string;
  error: (message: string, options?: ToastOptions) => string;
  loading: (message: string, options?: ToastOptions) => string;
  promise: <T>(
    promise: Promise<T>,
    msgs: { loading: string; success: string; error: string }
  ) => Promise<T>;
  dismiss: (toastId?: string) => void;
  custom: typeof import('react-hot-toast').default;
}

// API types
export interface PluginApi {
  get: <T = any>(url: string) => Promise<T>;
  post: <T = any>(url: string, data?: any) => Promise<T>;
  put: <T = any>(url: string, data?: any) => Promise<T>;
  patch: <T = any>(url: string, data?: any) => Promise<T>;
  delete: <T = any>(url: string) => Promise<T>;
}

// Utility types
export interface PluginUtils {
  formatBytes: (bytes: number | null | undefined) => string;
  formatDate: (date: string | Date, options?: Intl.DateTimeFormatOptions) => string;
  formatDuration: (seconds: number | null | undefined) => string;
  formatUptime: (seconds: number | null | undefined) => string;
  cn: (...classes: (string | undefined | null | false)[]) => string;
}

// UI Components interface
export interface PluginUI {
  Button: React.FC<ButtonProps>;
  Card: React.FC<CardProps>;
  CardHeader: React.FC<CardHeaderProps>;
  CardContent: React.FC<CardContentProps>;
  CardFooter: React.FC<CardFooterProps>;
  Badge: React.FC<BadgeProps>;
  Modal: React.FC<ModalProps>;
  Input: React.FC<InputProps>;
  Textarea: React.FC<TextareaProps>;
  Select: React.FC<SelectProps>;
  ProgressBar: React.FC<ProgressBarProps>;
  Spinner: React.FC<SpinnerProps>;
  LoadingOverlay: React.FC<LoadingOverlayProps>;
  EmptyState: React.FC<EmptyStateProps>;
  Tabs: React.FC<TabsProps>;
  TabPanel: React.FC<TabPanelProps>;
}

// React hooks interface
export interface PluginHooks {
  useState: typeof React.useState;
  useEffect: typeof React.useEffect;
  useCallback: typeof React.useCallback;
  useMemo: typeof React.useMemo;
  useRef: typeof React.useRef;
  useContext: typeof React.useContext;
  createContext: typeof React.createContext;
  memo: typeof React.memo;
  forwardRef: typeof React.forwardRef;
}

// Main SDK interface
export interface BaluHostSDK {
  React: typeof React;
  hooks: PluginHooks;
  ui: PluginUI;
  icons: typeof import('lucide-react');
  toast: PluginToast;
  api: PluginApi;
  utils: PluginUtils;
}

// Plugin registration interface
export interface PluginRoutes {
  [routeName: string]: React.ComponentType<any>;
}

export interface PluginWidgets {
  [widgetName: string]: React.ComponentType<any>;
}

export interface PluginRegistration {
  routes?: PluginRoutes;
  widgets?: PluginWidgets;
}

export interface BaluHostPlugins {
  [pluginName: string]: PluginRegistration;
}

// Global window extension
declare global {
  interface Window {
    /**
     * BaluHost Plugin SDK
     * Provides React, UI components, icons, toast, API, and utilities for plugins
     */
    BaluHost: BaluHostSDK;

    /**
     * Registry for plugin components
     * Plugins register their routes and widgets here
     */
    BaluHostPlugins: BaluHostPlugins;

    /**
     * React is also available directly on window for backwards compatibility
     */
    React: typeof React;
  }
}

export {};
