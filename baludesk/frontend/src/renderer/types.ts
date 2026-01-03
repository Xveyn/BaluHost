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

// User Types
export interface User {
  username: string;
  serverUrl?: string;
}
