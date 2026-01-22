// Electron API Types
export interface ElectronAPI {
  sendBackendCommand: (command: BackendCommand) => Promise<BackendResponse>;
  onBackendMessage: (callback: (message: BackendMessage) => void) => void;
  getAppVersion: () => Promise<string>;
  removeBackendListener: () => void;
}

// Backend Communication Types
export interface BackendCommand {
  type: string;
  data?: any;
}

export interface BackendResponse {
  success: boolean;
  data?: any;
  error?: string;
}

export interface BackendMessage {
  type: string;
  data: any;
}

// Sync Types
export interface SyncFolder {
  id: string;
  localPath: string;
  remotePath: string;
  status: 'idle' | 'syncing' | 'paused' | 'error';
  enabled: boolean;
  createdAt: string;
  lastSync: string;
}

export interface SyncStats {
  status: string;
  uploadSpeed: number;
  downloadSpeed: number;
  pendingUploads: number;
  pendingDownloads: number;
  lastSync: string;
}

export interface FileEvent {
  type: 'created' | 'modified' | 'deleted';
  path: string;
  timestamp: number;
}

// Conflict Resolution Types
export interface FileConflict {
  id: string;
  path: string;
  localVersion: FileVersion;
  remoteVersion: FileVersion;
  conflictType: 'modified-modified' | 'modified-deleted' | 'deleted-modified' | 'name-conflict';
}

export interface FileVersion {
  content?: string;
  size: number;
  modifiedAt: string;
  hash: string;
  exists: boolean;
}

export type ConflictResolutionOption = 'keep-local' | 'keep-remote' | 'keep-both' | 'manual';

export interface ConflictResolution {
  conflictId: string;
  resolution: ConflictResolutionOption;
  metadata?: {
    customPath?: string;
    timestamp?: string;
  };
}

// Settings Types
export interface AppSettings {
  // Server Connection
  serverUrl: string;
  serverPort: number;
  username: string;
  rememberPassword: boolean;

  // Sync Behavior
  autoStartSync: boolean;
  autoStartOnBoot: boolean;  // OS-level auto-start
  syncInterval: number;  // seconds
  maxConcurrentTransfers: number;
  bandwidthLimitMbps: number;  // 0 = unlimited
  conflictResolution: 'ask' | 'local' | 'remote' | 'newer';

  // Network Settings
  networkTimeoutSeconds: number;
  retryAttempts: number;

  // Smart Sync
  smartSyncEnabled: boolean;
  smartSyncBatteryThreshold: number;  // percentage (0-100)
  smartSyncCpuThreshold: number;  // percentage (0-100)

  // Sync Filters
  ignorePatterns: string[];  // e.g., [".git", "node_modules", "*.tmp"]
  maxFileSizeMb: number;  // 0 = unlimited

  // UI Preferences
  theme: 'dark' | 'light' | 'system';
  language: string;  // 'en' | 'de'
  startMinimized: boolean;
  showNotifications: boolean;
  notifyOnSyncComplete: boolean;
  notifyOnErrors: boolean;

  // Advanced
  enableDebugLogging: boolean;
  chunkSizeMb: number;
}

export interface SettingsResponse {
  success: boolean;
  data?: Partial<AppSettings>;
  error?: string;
}

// User Types
export interface User {
  username: string;
  serverUrl?: string;
}
