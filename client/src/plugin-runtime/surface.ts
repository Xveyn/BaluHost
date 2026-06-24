// client/src/plugin-runtime/surface.ts
// The non-proxy half of window.BaluHost, bundled INTO the runtime and run
// inside the sandbox iframe (minus the tokened api/toast, which are postMessage proxies in index.ts).
import React, {
  useState, useEffect, useCallback, useMemo, useRef,
  useContext, createContext, memo, forwardRef,
} from 'react';
import * as LucideIcons from 'lucide-react';
import {
  Button, Card, CardHeader, CardContent, CardFooter, Badge, Modal, Input,
  Textarea, Select, ProgressBar, Spinner, LoadingOverlay, EmptyState,
  Tabs, TabPanel, ByteSizeInput,
} from '../components/ui';
import { formatBytes as _formatBytes } from '../lib/formatters';

function formatBytes(bytes: number | null | undefined): string {
  if (!bytes || bytes === 0) return '0 B';
  return _formatBytes(bytes);
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
function cn(...classes: (string | undefined | null | false)[]): string {
  return classes.filter(Boolean).join(' ');
}

export function buildSurface() {
  return {
    React,
    hooks: { useState, useEffect, useCallback, useMemo, useRef, useContext, createContext, memo, forwardRef },
    ui: {
      Button, Card, CardHeader, CardContent, CardFooter, Badge, Modal, Input,
      Textarea, Select, ProgressBar, Spinner, LoadingOverlay, EmptyState,
      Tabs, TabPanel, ByteSizeInput,
    },
    icons: LucideIcons,
    utils: { formatBytes, formatDate, formatDuration, formatUptime, cn },
  };
}
